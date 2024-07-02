# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Implements a Slurm job manager. Jobs are kept track of in an SQL database
and logs are written to a default logs folder.

There is no need to create bash wrapper script to pass sbatch option.
Implements wrappers for sbatch, scancel, squeue, sacct, and sinfo

Useful commands:
    - See all your jobs:
        squeue --me
    - Cancel ALL your jobs:
        scancel --me
    - View current QOS policies:
        sacctmgr show qos format=Name%20,Priority,Flags%30,MaxWall,MaxTRESPU%20,MaxJobsPU,MaxSubmitPU,MaxTRESPA%25
"""

import json
import os
import pydoc
import re
import shlex
import shutil
import subprocess
import tempfile

from collections import defaultdict
from pathlib import Path
from sqlite3 import Connection as SQLite3Connection
from typing import Iterable, Optional

import click
import sqlalchemy

from clapper.click import AliasedGroup
from loguru import logger
from sqlalchemy import Column, ForeignKey, Integer, String, Table, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    registry,
    relationship,
)
from sqlalchemy.types import TypeDecorator
from tabulate import tabulate


# enable foreign key support in sqlite3
# https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def update_job_statuses(grid_ids: Iterable[int]) -> dict[int, dict]:
    status = dict()
    output = subprocess.check_output(
        ["sacct", "-j", ",".join([str(x) for x in grid_ids]), "--json"],
        text=True,
    )
    for job in json.loads(output)["jobs"]:
        status[job["job_id"]] = job
    return status


JOB_STATES_MAPPING = {
    "BF": "BOOT_FAIL",
    "CA": "CANCELLED",
    "CD": "COMPLETED",
    "CF": "CONFIGURING",
    "CG": "COMPLETING",
    "DL": "DEADLINE",
    "F": "FAILED",
    "NF": "NODE_FAIL",
    "OOM": "OUT_OF_MEMORY",
    "PD": "PENDING",
    "PR": "PREEMPTED",
    "RD": "RESV_DEL_HOLD",
    "RF": "REQUEUE_FED",
    "RH": "REQUEUE_HOLD",
    "RQ": "REQUEUED",
    "R": "RUNNING",
    "RS": "RESIZING",
    "RV": "REVOKED",
    "SE": "SPECIAL_EXIT",
    "SI": "SIGNALING",
    "SO": "STAGE_OUT",
    "S": "SUSPENDED",
    "ST": "STOPPED",
    "TO": "TIMEOUT",
    "UN": "UNKNOWN",
}
"""Some of these states are only shown when using scontrol or squeue but these
commands do not provide info for finished commands.

sacct only retuns these states https://slurm.schedmd.com/sacct.html#lbAG
"""


class ObjectValue(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value)
            elif isinstance(value, Path):
                value = str(value.absolute())
            else:
                raise TypeError(
                    "ObjectValue must be a dict, list, tuple or Path but got %r"
                    % type(value)
                )
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if value.startswith("/"):
                value = Path(value)
            else:
                value = json.loads(value)
        return value


mapper_registry = registry()


class Base(DeclarativeBase):
    pass


job_dependencies = Table(
    "job_dependencies",
    Base.metadata,
    Column("job_id", Integer, ForeignKey("jobs.id"), primary_key=True),
    Column("waited_for_job_id", Integer, ForeignKey("jobs.id"), primary_key=True),
)


class JobDependency:
    """job_dependencies represents a single dependency relationship between two
    jobs.

    It links a job_id (the dependent job) to a waited_for_job_id (the
    job that must finish first).
    """

    def __repr__(self):
        return f"<JobDependency {self.job_id} -> {self.waited_for_job_id}>"


# Mapping the class to the table
mapper_registry.map_imperatively(JobDependency, job_dependencies)


def parse_array_indexes(indexes_str: str) -> list[int]:
    def parse_range(range_str):
        if ":" in range_str:
            range_part, step = range_str.split(":")
            start, end = map(int, range_part.split("-"))
            step = int(step)
            return list(range(start, end + 1, step))
        else:
            start, end = map(int, range_str.split("-"))
            return list(range(start, end + 1))

    def parse_segment(segment):
        if "-" in segment:
            return parse_range(segment)
        else:
            return [int(segment)]

    # Remove any limit on simultaneous running tasks
    if "%" in indexes_str:
        indexes_str = indexes_str.split("%")[0]

    segments = indexes_str.split(",")
    result = []
    for segment in segments:
        result.extend(parse_segment(segment))

    return result


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    command: Mapped[list] = mapped_column(ObjectValue)
    logs_dir: Mapped[Path] = mapped_column(ObjectValue)
    is_array_job: Mapped[bool]
    dependencies_str: Mapped[Optional[str]] = mapped_column(String(2048))
    grid_id: Mapped[Optional[int]]
    state: Mapped[Optional[str]] = mapped_column(String(30), default="UNKNOWN")
    exit_code: Mapped[Optional[str]]
    nodes: Mapped[Optional[str]]  # list of node names
    array_task_ids: Mapped[Optional[list[int]]] = mapped_column(ObjectValue)
    dependencies_jobdependency: Mapped[list[JobDependency]] = relationship(
        JobDependency,
        primaryjoin=id == JobDependency.job_id,  # type: ignore[attr-defined]
        viewonly=True,
        order_by=JobDependency.waited_for_job_id,  # type: ignore[attr-defined]
    )
    dependencies_ids: Mapped[list[int]] = association_proxy(
        "dependencies_jobdependency", "waited_for_job_id"
    )
    dependents: Mapped[list["Job"]] = relationship(
        "Job",
        secondary=job_dependencies,
        primaryjoin=id == job_dependencies.c.waited_for_job_id,
        secondaryjoin=id == job_dependencies.c.job_id,
        viewonly=True,
    )

    def __repr__(self) -> str:
        return (
            f"Job("
            f"id={self.id!r}, "
            f"name={self.name!r}, "
            f"command={self.command!r}, "
            f"grid_id={self.grid_id}, "
            f"state={self.state}, "
            f"exit_code={self.exit_code}, "
            f"logs_dir={self.logs_dir}, "
            f"nodes={self.nodes}, "
            f"is_array_job={self.is_array_job}, "
            f"array_task_ids={self.array_task_ids}, "
            f"dependencies={self.dependencies_str}, "
            f")"
        )

    @property
    def output_options(self):
        # check if it is an array job
        if self.is_array_job:
            output = error = self.logs_dir / f"{self.name}.%A-%a.out"
        else:
            output = error = self.logs_dir / f"{self.name}.%j.out"
        return output, error

    @property
    def command_in_bash(self) -> str:
        if "---" not in self.command:
            return ""
        content = "#!/bin/bash\n"
        split_idx = self.command.index("---")
        content += shlex.join(self.command[split_idx + 1 :]) + "\n"
        return content

    def get_dependencies_jobs(self, session):
        return (
            session.query(Job)
            .filter(Job.id.in_(job_ids_from_dep_str(self.dependencies_str)))
            .all()
        )

    def submitted_command(self, fh, session):
        command = list(self.command)
        if self.dependencies_str:
            dep_jobs = self.get_dependencies_jobs(session)
            dep_option = replace_job_ids_in_dep_str(
                self.dependencies_str, [job.grid_id for job in dep_jobs]
            )
            command.insert(0, "--dependency")
            command.insert(1, dep_option)

        if "---" in command:
            if any(arg.startswith("--wrap") for arg in command):
                raise RuntimeError("Cannot use --wrap and --- together.")
            split_idx = command.index("---")
            fh.write(self.command_in_bash)
            command = command[:split_idx] + [fh.name]

        fh.flush()
        fh.close()  # close now to flush the file
        output, error = self.output_options
        return [
            "sbatch",
            "--job-name",
            self.name,
            "--output",
            str(output),
            "--error",
            str(error),
        ] + command

    def submit(self, session: Session = None):
        with tempfile.NamedTemporaryFile(
            mode="w+t", suffix=".sh", delete_on_close=False
        ) as fh:
            command = self.submitted_command(fh=fh, session=session)
            output = subprocess.check_output(
                command,
                text=True,
            )
        # find job ID from output
        # output is like b'Submitted batch job 123456789\n'
        self.grid_id = int(re.search("[0-9]+", output).group())
        return self.grid_id

    def cancel(self, delete_logs: bool = False):
        subprocess.check_output(["scancel"] + [str(self.grid_id)])
        if delete_logs:
            for path in self.output_files + self.error_files:
                if path.exists():
                    path.unlink()

    def update(self, job_status_dict: dict):
        if not job_status_dict:
            logger.warning(f"Could not update the job state for {self}")
            return
        self.state = job_status_dict["state"]["current"][0].upper()
        self.exit_code = job_status_dict["derived_exit_code"]["return_code"]["number"]
        self.nodes = job_status_dict["nodes"]
        if self.nodes == "None assigned":
            # TODO: sometimes only the state_reason from squeue contains the reason
            self.nodes = job_status_dict["state"]["reason"]
        assert (
            self.state in JOB_STATES_MAPPING.values()
        ), f"Unknown job state {self.state}, read from {job_status_dict}"
        return

    @property
    def output_files(self):
        output, _ = map(str, self.output_options)
        if not self.is_array_job:
            return [Path(output.replace("%j", str(self.grid_id)))]
        else:
            files = []
            for array_task_id in self.array_task_ids:
                files.append(
                    output.replace("%A", str(self.grid_id)).replace(
                        "%a", str(array_task_id)
                    )
                )
            return list(map(Path, files))

    @property
    def error_files(self):
        # as of now error files are the same as output files but this could change.
        return self.output_files


def job_ids_from_dep_str(dependency_string: str | None) -> list[int]:
    if not dependency_string:
        return []
    # Regular expression to match job IDs with optional +time
    dep_job_id_pattern = re.compile(r"(\d+)(?:\+\d+)?")

    # Find all matches in the dependency string
    job_ids = dep_job_id_pattern.findall(dependency_string)

    return list(map(int, job_ids))


def replace_job_ids_in_dep_str(dependency_string, replacements):
    if not dependency_string:
        return dependency_string
    # Regular expression to match job IDs with optional +time
    job_id_pattern = re.compile(r"(\d+)(\+\d+)?")

    # Function to replace matched job ID with corresponding replacement from the list
    def replacement_func(match):
        time_part = match.group(2) if match.group(2) else ""
        if replacements:
            new_job_id = replacements.pop(0)
            return f"{new_job_id}{time_part}"
        else:
            raise ValueError("Not enough replacements")

    # Substitute all job IDs in the dependency string
    result_string = job_id_pattern.sub(replacement_func, dependency_string)

    return result_string


class JobManager:
    def __init__(self, database: Path, logs_dir: Path) -> None:
        self.database = Path(database)
        self.engine = create_engine(f"sqlite:///{self.database}", echo=False)
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)

    def __enter__(self):
        # opens a new session and returns it
        Base.metadata.create_all(self.engine)
        self._session = Session(self.engine)
        self._session.begin()
        return self._session

    def __exit__(self, exc_type, exc_value, traceback):
        # closes the session and rollbacks in case of an exception
        if exc_type is not None:
            self._session.rollback()
        self._session.close()
        return False

    @property
    def session(self) -> Session:
        return self._session

    def submit_job(self, name, command, array, dependencies):
        array_task_ids = None
        if array:
            command = ("--array", array) + tuple(command)
            array_task_ids = parse_array_indexes(array)
        job = Job(
            name=name,
            command=command,
            logs_dir=self.logs_dir,
            is_array_job=bool(array),
            array_task_ids=array_task_ids,
            dependencies_str=dependencies,
        )
        try:
            job.submit(session=self.session)
            self.session.add(job)
            self.session.flush()
            self.session.refresh(job)

            if dependencies:
                # add dependency relationships
                dep_job_ids = job_ids_from_dep_str(dependencies)
                self.session.add_all(
                    [
                        JobDependency(
                            job_id=job.id,
                            waited_for_job_id=dep_id,
                        )
                        for dep_id in dep_job_ids
                    ]
                )
        except sqlalchemy.exc.SQLAlchemyError as e:
            raise RuntimeError(
                f"""Failed to submit job with
name: {name}
command: {command}
array: {array}
dependencies: {dependencies}"""
            ) from e
        return job

    def update_jobs(self) -> None:
        """Update the status of all jobs."""
        jobs_by_grid_id: dict[int, Job] = dict()
        query = self.session.query(Job)
        for job in query.all():
            jobs_by_grid_id[job.grid_id] = job
        if not jobs_by_grid_id:
            return
        job_statuses = update_job_statuses(jobs_by_grid_id.keys())
        for grid_id, job in jobs_by_grid_id.items():
            if grid_id in job_statuses:
                job.update(job_statuses[grid_id])

    def list_jobs(
        self, *, job_ids=None, states=None, names=None, update_jobs=True
    ) -> list[Job]:
        if update_jobs:
            self.update_jobs()
        jobs = []
        query = self.session.query(Job)
        if job_ids:
            query = query.filter(Job.id.in_(job_ids))
        if names:
            query = query.filter(Job.name.in_(names))
        if states:
            query = query.filter(Job.state.in_(states))
        for job in query.all():
            jobs.append(job)

        return jobs

    def stop_jobs(self, delete=False, **kwargs):
        """Stop all jobs that match the given criteria."""
        jobs = self.list_jobs(**kwargs)
        all_jobs = []
        for job in jobs:
            job.cancel(delete_logs=delete)
            all_jobs.append(job)
            # also stop dependent jobs
            for dependent_job in job.dependents:
                dependent_job.cancel(delete_logs=delete)
                all_jobs.append(dependent_job)
        if delete:
            with self.session.no_autoflush:
                for job in all_jobs:
                    self.session.delete(job)
                # also delete job dependencies
                ids = [job.id for job in all_jobs]
                self.session.query(JobDependency).filter(
                    JobDependency.job_id.in_(ids)
                    | JobDependency.waited_for_job_id.in_(ids)
                ).delete()
        return all_jobs

    def delete_jobs(self, **kwargs):
        return self.stop_jobs(delete=True, **kwargs)

    def resubmit_jobs(self, **kwargs):
        jobs = self.list_jobs(**kwargs)
        all_jobs = []
        for job in jobs:
            job.cancel(delete_logs=True)
            job.submit(session=self.session)
            self.session.add(job)
            all_jobs.append(job)
            for dependent_job in job.dependents:
                dependent_job.cancel(delete_logs=True)
                dependent_job.submit(session=self.session)
                self.session.add(dependent_job)
                all_jobs.append(dependent_job)
        return all_jobs

    def __del__(self):
        # if there are no jobs in the database, delete the database file and the logs directory (if empty)
        with self:
            if (
                os.path.exists(self.database)
                and len(self.list_jobs(update_jobs=False)) == 0
            ):
                os.remove(self.database)
            if self.logs_dir.exists() and len(os.listdir(self.logs_dir)) == 0:
                shutil.rmtree(self.logs_dir)


class CustomGroup(AliasedGroup):
    def list_commands(self, ctx: click.Context) -> list[str]:
        # do not sort the commands
        return self.commands

    def get_command(self, ctx, cmd_name):
        cmd_name = {
            "sbatch": "submit",
            "scancel": "stop",
            # "squeue": "list",
            # "sacct": "report",
            "ls": "list",
            "rm": "delete",
            "remove": "delete",
        }.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)


@click.group(
    cls=CustomGroup,
    context_settings={
        "show_default": True,
        "help_option_names": ["--help", "-h"],
    },
)
@click.option(
    "-d",
    "--database",
    help="Path to the database file.",
    default=Path("jobs.sql3"),
    type=click.Path(path_type=Path, file_okay=True, dir_okay=False, writable=True),
)
@click.option(
    "-l",
    "--logs-dir",
    help="Path to the logs directory.",
    default=Path("logs"),
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, writable=True),
)
@click.pass_context
def cli(ctx, database, logs_dir):
    """GridTK command line interface."""
    ctx.meta["job_manager"] = JobManager(database=database, logs_dir=logs_dir)


@cli.command(
    epilog="""Example:
gridtk submit my_script.sh
gridtk submit --- python my_code.py
""",
    context_settings=dict(
        ignore_unknown_options=True,
        # allow_extra_args=True,
        allow_interspersed_args=False,
    ),
)
@click.option(
    "-J",
    "--job-name",
    default="gridtk",
    help="Specify a name for the job allocation. The specified name will appear along with the job id number when querying running jobs on the system.",
)
@click.option(
    "-a",
    "--array",
    help='Submit a job array, multiple jobs to be executed with identical parameters. The indexes specification identifies what array index values should be used. Multiple values may be specified using a comma separated list and/or a range of values with a "-" separator. For example, "--array=0-15" or "--array=0,6,16-32". A step function can also be specified with a suffix containing a colon and number. For example, "--array=0-15:4" is equivalent to "--array=0,4,8,12". A maximum number of simultaneously running tasks from the job array may be specified using a "%" separator. For example "--array=0-15%4" will limit the number of simultaneously running tasks from this job array to 4. The minimum index value is 0. the maximum value is one less than the configuration parameter MaxArraySize. NOTE: Currently, federated job arrays only run on the local cluster.',
)
@click.option(
    "-d",
    "--dependency",
    "dependencies",
    help="Depend on other jobs that are already in the list of gridtk.",
)
@click.option(
    "--repeat",
    default=1,
    type=click.INT,
    help="Submits the job N times. Each job will depend on the job before.",
)
# sbatch options
@click.option("-A", "--account", hidden=True)
@click.option("--acctg-freq", hidden=True)
@click.option("--batch", hidden=True)
@click.option("--bb", hidden=True)
@click.option("--bbf", hidden=True)
@click.option("-b", "--begin", hidden=True)
@click.option("-D", "--chdir", hidden=True)
@click.option("--cluster-constraint", hidden=True)
@click.option("-M", "--clusters", hidden=True)
@click.option("--comment", hidden=True)
@click.option("-C", "--constraint", hidden=True)
@click.option("--container", hidden=True)
@click.option("--container-id", hidden=True)
@click.option("--contiguous", is_flag=True, hidden=True)
@click.option("-S", "--core-spec", hidden=True)
@click.option("--cores-per-socket", hidden=True)
@click.option("--cpu-freq", hidden=True)
@click.option("--cpus-per-gpu", hidden=True)
@click.option("-c", "--cpus-per-task", hidden=True)
@click.option("--deadline", hidden=True)
@click.option("--delay-boot", hidden=True)
@click.option("-m", "--distribution", hidden=True)
@click.option("-e", "--error", hidden=True)
@click.option("-x", "--exclude", hidden=True)
@click.option("--exclusive", hidden=True)
@click.option("--export", hidden=True)
@click.option("--export-file", hidden=True)
@click.option("--extra", hidden=True)
@click.option("-B", "--extra-node-info", hidden=True)
@click.option("--get-user-env", hidden=True)
@click.option("--gid", hidden=True)
@click.option("--gpu-bind", hidden=True)
@click.option("--gpu-freq", hidden=True)
@click.option("-G", "--gpus", hidden=True)
@click.option("--gpus-per-node", hidden=True)
@click.option("--gpus-per-socket", hidden=True)
@click.option("--gpus-per-task", hidden=True)
@click.option("--gres", hidden=True)
@click.option("--gres-flags", hidden=True)
@click.option("--hint", hidden=True)
@click.option("-H", "--hold", is_flag=True, hidden=True)
@click.option("--ignore-pbs", is_flag=True, hidden=True)
@click.option("-i", "--input", hidden=True)
@click.option("--kill-on-invalid-dep", hidden=True)
@click.option("-L", "--licenses", hidden=True)
@click.option("--mail-type", hidden=True)
@click.option("--mail-user", hidden=True)
@click.option("--mcs-label", hidden=True)
@click.option("--mem", hidden=True)
@click.option("--mem-bind", hidden=True)
@click.option("--mem-per-cpu", hidden=True)
@click.option("--mem-per-gpu", hidden=True)
@click.option("--mincpus", hidden=True)
@click.option("--network", hidden=True)
@click.option("--nice", hidden=True)
@click.option("-k", "--no-kill", is_flag=True, hidden=True)
@click.option("--no-requeue", is_flag=True, hidden=True)
@click.option("-F", "--nodefile", hidden=True)
@click.option("-w", "--nodelist", hidden=True)
@click.option("-N", "--nodes", hidden=True)
@click.option("-n", "--ntasks", hidden=True)
@click.option("--ntasks-per-core", hidden=True)
@click.option("--ntasks-per-gpu", hidden=True)
@click.option("--ntasks-per-node", hidden=True)
@click.option("--ntasks-per-socket", hidden=True)
@click.option("--open-mode", hidden=True)
@click.option("-o", "--output", hidden=True)
@click.option("-O", "--overcommit", is_flag=True, hidden=True)
@click.option("-s", "--oversubscribe", is_flag=True, hidden=True)
@click.option("--parsable", is_flag=True, hidden=True)
@click.option("-p", "--partition", hidden=True)
@click.option("--prefer", hidden=True)
@click.option("--priority", hidden=True)
@click.option("--profile", hidden=True)
@click.option("--propagate", hidden=True)
@click.option("-q", "--qos", hidden=True)
@click.option("-Q", "--quiet", is_flag=True, hidden=True)
@click.option("--reboot", is_flag=True, hidden=True)
@click.option("--requeue", is_flag=True, hidden=True)
@click.option("--reservation", hidden=True)
@click.option("--resv-ports", hidden=True)
@click.option("--segment", hidden=True)
@click.option("--signal", hidden=True)
@click.option("--sockets-per-node", hidden=True)
@click.option("--spread-job", is_flag=True, hidden=True)
@click.option("--stepmgr", is_flag=True, hidden=True)
@click.option("--switches", hidden=True)
@click.option("--test-only", is_flag=True, hidden=True)
@click.option("--thread-spec", hidden=True)
@click.option("--threads-per-core", hidden=True)
@click.option("-t", "--time", hidden=True)
@click.option("--time-min", hidden=True)
@click.option("--tmp", hidden=True)
@click.option("--tres-bind", hidden=True)
@click.option("--tres-per-task", hidden=True)
@click.option("--uid", hidden=True)
@click.option("--usage", is_flag=True, hidden=True)
@click.option("--use-min-nodes", is_flag=True, hidden=True)
@click.option("-v", "--verbose", is_flag=True, multiple=True, hidden=True)
@click.option("-V", "--version", is_flag=True, hidden=True)
@click.option("-W", "--wait", is_flag=True, hidden=True)
@click.option("--wait-all-nodes", hidden=True)
@click.option("--wckey", hidden=True)
@click.option("--wrap", hidden=True)
@click.argument("script", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def submit(
    ctx: click.Context,
    job_name: str,
    array: str,
    dependencies: str,
    repeat: int,
    script: str,
    **kwargs,
):
    """Submit a job to the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    # reconstruct the command with kwargs, script, and args
    command = []
    for k, v in kwargs.items():
        if v in (None, False):
            # option was not provided
            continue
        if k in ("output", "error"):
            # we ignore output and error options
            continue
        k = k.replace("_", "-")
        if isinstance(v, str):
            command.extend([f"--{k}", f"{v}"])
        elif isinstance(v, bool):
            command.append(f"--{k}")

    command.extend(script)

    with job_manager as session:
        if repeat > 1:
            if dependencies is not None and (
                "," in dependencies or "?" in dependencies
            ):
                raise click.UsageError(
                    f"Repeated jobs can only have one dependency type (no `,` or `?` in --dependency) but got {dependencies}"
                )
        for _ in range(repeat):
            job = job_manager.submit_job(
                name=job_name,
                command=command,
                array=array,
                dependencies=dependencies,
            )
            click.echo(job.id)
            deps = (dependencies or "").split(",")
            deps[-1] = f"{deps[-1]}:{job.id}" if deps[-1] else str(job.id)
            dependencies = ",".join(deps)
        session.commit()


def parse_job_ids(job_ids: str) -> list[int]:
    """Parse the job ids."""
    if not job_ids:
        return []
    try:
        if "," in job_ids:
            final_job_ids = []
            for job_id in job_ids.split(","):
                final_job_ids.extend(parse_job_ids(job_id))
            return final_job_ids
        elif "-" in job_ids:
            start, end_str = job_ids.split("-")
            return list(range(int(start), int(end_str) + 1))
        elif "+" in job_ids:
            start, length = job_ids.split("+")
            end = int(start) + int(length)
            return list(range(int(start), end + 1))
        else:
            return [int(job_ids)]
    except ValueError as e:
        raise click.BadParameter(f"Invalid job id {job_ids}") from e


def parse_states(states: str) -> list[str]:
    """Normalizes a list of comma separated states to their long name
    format."""
    if not states:
        return []
    states = states.upper()
    if states == "ALL":
        return list(JOB_STATES_MAPPING.values())
    states_split = states.split(",")
    final_states = []
    for state in states_split:
        state = JOB_STATES_MAPPING.get(state, state)
        if state not in JOB_STATES_MAPPING.values():
            raise click.BadParameter(f"Invalid state: {state}")
        final_states.append(state)
    return final_states


def job_ids_callback(ctx, param, value):
    """Callback for the job ids option."""
    return parse_job_ids(value)


def states_callback(ctx, param, value):
    """Callback for the states option."""
    return parse_states(value)


def job_filters(f_py=None, default_states=None):
    assert callable(f_py) or f_py is None

    def _job_filters_decorator(function):
        function = click.option(
            "--name",
            "names",
            multiple=True,
            help="Selects jobs based on their name. For multiple names, repeat this option.",
        )(function)
        function = click.option(
            "-s",
            "--state",
            "states",
            default=default_states,
            help="Selects jobs based on their states separated by comma. Possible values are "
            + ", ".join([f"{v} ({k})" for k, v in JOB_STATES_MAPPING.items()])
            + " and ALL.",
            callback=states_callback,
        )(function)
        function = click.option(
            "-j",
            "--jobs",
            "job_ids",
            help="Selects only these job ids, separated by comma.",  # TODO: explain range notation
            callback=job_ids_callback,
        )(function)
        return function

    return _job_filters_decorator(f_py) if callable(f_py) else _job_filters_decorator


@cli.command()
@job_filters(default_states="BF,CA,F,NF,OOM,TO")
@click.pass_context
def resubmit(
    ctx: click.Context, job_ids: list[int], states: list[str], names: list[str]
):
    """Resubmit a job to the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.resubmit_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Resubmitted job {job.id}")
        session.commit()


@cli.command()
@job_filters
@click.pass_context
def stop(ctx: click.Context, job_ids: list[int], states: list[str], names: list[str]):
    """Stop a job from running."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.stop_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Stopped {job.id}")
        session.commit()


@cli.command(name="list")
@job_filters
@click.pass_context
def list_jobs(
    ctx: click.Context, job_ids: list[int], states: list[str], names: list[str]
):
    """List jobs in the queue, similar to sacct and squeue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.list_jobs(job_ids=job_ids, states=states, names=names)
        table = defaultdict(list)
        for job in jobs:
            table["job-id"].append(job.id)
            table["grid-id"].append(job.grid_id)
            table["nodes"].append(job.nodes)
            table["state"].append(f"{job.state} ({job.exit_code})")
            table["job-name"].append(job.name)
            table["output"].append(
                job_manager.logs_dir
                / job.output_files[0]
                .resolve()
                .relative_to(job_manager.logs_dir.resolve())
            )
            table["dependencies"].append(
                ",".join([str(dep_job) for dep_job in job.dependencies_ids])
            )
            table["command"].append("gridtk submit " + " ".join(job.command))
        click.echo(tabulate(table, headers="keys"))
        session.commit()


@cli.command()
@job_filters
@click.option(
    "-a",
    "--array",
    "array_idx",
    help="Array index to see the logs for only one item of an array job.",
)
@click.pass_context
def report(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    array_idx: str | None,
):
    """Report on jobs in the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.list_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            report_text = ""
            report_text += f"Job ID: {job.id}\n"
            report_text += f"Name: {job.name}\n"
            report_text += f"State: {job.state} ({job.exit_code})\n"
            report_text += f"Nodes: {job.nodes}\n"
            with tempfile.NamedTemporaryFile(mode="w+t", suffix=".sh") as tmpfile:
                report_text += f"Submitted command: {job.submitted_command(tmpfile, session=session)}\n"
                if job.command_in_bash:
                    report_text += (
                        f"Content of the temporary script:\n{job.command_in_bash}\n"
                    )
            output_files, error_files = job.output_files, job.error_files
            if array_idx is not None:
                real_array_idx = job.array_task_ids.index(int(array_idx))
                output_files = output_files[real_array_idx : real_array_idx + 1]
                error_files = error_files[real_array_idx : real_array_idx + 1]
            for output, error in zip(output_files, error_files):
                report_text += f"Output file: {output}\n"
                if output.exists():
                    report_text += output.open().read() + "\n\n"
                if error != output:
                    report_text += f"Error file: {error}\n"
                    if error.exists():
                        report_text += error.open().read() + "\n\n"
            pydoc.pager(report_text)
        session.commit()


@cli.command()
@job_filters
@click.pass_context
def delete(ctx: click.Context, job_ids: list[int], states: list[str], names: list[str]):
    """Delete a job from the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.delete_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Deleted job {job.id} with grid ID {job.grid_id}")
        session.commit()


if __name__ == "__main__":
    cli()
