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
import time

from collections import defaultdict
from pathlib import Path
from sqlite3 import Connection as SQLite3Connection
from typing import Optional

import click
import sqlalchemy

from clapper.click import AliasedGroup
from loguru import logger
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
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


def update_job_statuses(grid_ids: list[int]) -> dict[int, dict]:
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


def has_array_options(command):
    return "-a" in command or any(v.startswith("--array") for v in command)


def eagerload_prox(loader, prox):
    # given eagerload_prox(joinedload, User.keywords)

    # User.user_keyword_associations
    first_attribute = getattr(prox.owning_class, prox.target_collection)

    # joinedload(User.keywords)
    step1 = loader(first_attribute)

    # UserKeywordAssociation
    middle_class = first_attribute.property.mapper.class_

    # UserKeywordAssociation.keyword
    second_attribute = getattr(middle_class, prox.value_attr)

    # joinedload().joinedload
    eagerload_callable = getattr(step1, loader.__name__)

    # joinedload().joinedload(UserKeywordAssociation.keyword)
    step2 = eagerload_callable(second_attribute)

    return step2


mapper_registry = registry()


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


class Base(DeclarativeBase):
    pass


job_dependencies = Table(
    "job_dependencies",
    Base.metadata,
    Column("job_id", Integer, ForeignKey("jobs.id"), primary_key=True),
    Column("waited_for_job_id", Integer, ForeignKey("jobs.id"), primary_key=True),
    Column("dep_type", String(30), default="afterany:"),
)


class JobDependency:
    """job_dependencies represents a single dependency relationship between two
    jobs.

    It links a job_id (the dependent job) to a waited_for_job_id (the
    job that must finish first).
    """

    def __repr__(self):
        return (
            f"<JobDependency {self.job_id} -> {self.dep_type}{self.waited_for_job_id}>"
        )


# Mapping the class to the table
mapper_registry.map_imperatively(JobDependency, job_dependencies)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    command: Mapped[list] = mapped_column(ObjectValue)
    output: Mapped[Path] = mapped_column(ObjectValue)  # path to the stdout file
    error: Mapped[Path] = mapped_column(ObjectValue)  # path to the stderr file
    grid_id: Mapped[Optional[int]]
    state: Mapped[Optional[str]] = mapped_column(String(30), default="UNKNOWN")
    exit_code: Mapped[Optional[str]]
    nodes: Mapped[Optional[str]]  # list of node names
    is_array_job: Mapped[bool] = mapped_column(Boolean)
    array_task_ids: Mapped[Optional[list[int]]] = mapped_column(ObjectValue)
    dependents: Mapped[list["Job"]] = relationship(
        "Job",
        secondary=job_dependencies,
        primaryjoin=id == job_dependencies.c.waited_for_job_id,
        secondaryjoin=id == job_dependencies.c.job_id,
        # back_populates="dependencies",
        viewonly=True,
    )
    # dependencies: Mapped[list["Job"]] = relationship(
    #     "Job",
    #     secondary=job_dependencies,
    #     primaryjoin=id == job_dependencies.c.job_id,
    #     secondaryjoin=id == job_dependencies.c.waited_for_job_id,
    #     back_populates="dependents",
    # )
    dep_objects: Mapped[list[JobDependency]] = relationship(
        JobDependency,
        primaryjoin=id == JobDependency.job_id,
        viewonly=True,
    )
    dep_types: AssociationProxy[list[str]] = association_proxy(
        "dep_objects", "dep_type"
    )
    dependencies: Mapped[list[int]] = association_proxy(
        "dep_objects", "waited_for_job_id"
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
            f"output={self.output}, "
            f"error={self.error}, "
            f"nodes={self.nodes}, "
            f"is_array_job={self.is_array_job}, "
            f"array_task_ids={self.array_task_ids}, "
            # f"dependents={self.dependents}, "
            # f"dependencies={self.dependencies}, "
            f")"
        )

    @property
    def command_in_bash(self) -> str:
        if "---" not in self.command:
            return ""
        content = "#!/bin/bash\n"
        split_idx = self.command.index("---")
        content += shlex.join(self.command[split_idx + 1 :]) + "\n"
        return content

    def submitted_command(self, fh, dependencies):
        command = list(self.command)
        if dependencies:
            dep_options = []
            # add dependency jobs with their grid id to command
            for dep_type, dep_job_list in dependencies.items():
                dep_option = ",".join(
                    f"{dep_type}{dep_job.grid_id}" for dep_job in dep_job_list
                )
                dep_options.append(dep_option)
            command.insert(0, "--dependency=" + ",".join(dep_options))

        if "---" in command:
            if any(arg.startswith("--wrap") for arg in command):
                raise RuntimeError("Cannot use --wrap and --- together.")
            split_idx = command.index("---")
            fh.write(self.command_in_bash)
            command = command[:split_idx] + [fh.name]

        fh.flush()
        fh.close()  # close now to flush the file
        return [
            "sbatch",
            "--job-name",
            self.name,
            "--output",
            str(self.output),
            "--error",
            str(self.error),
        ] + command

    def submit(self, dependencies: dict[str, list["Job"]] = None):
        with tempfile.NamedTemporaryFile(
            mode="w+t", suffix=".sh", delete_on_close=False
        ) as fh:
            command = self.submitted_command(fh=fh, dependencies=dependencies)
            output = subprocess.check_output(
                command,
                text=True,
            )
        # find job ID from output
        # output is like b'Submitted batch job 123456789\n'
        self.grid_id = int(re.search("[0-9]+", output).group())
        # right after job submission find the output and error paths
        time.sleep(3)
        output = subprocess.check_output(
            ["scontrol", "show", "job", str(self.grid_id), "--json"],
            text=True,
        )
        output = json.loads(output)
        self.output = Path(output["jobs"][0]["standard_output"])
        self.error = Path(output["jobs"][0]["standard_error"])
        self.is_array_job = output["jobs"][0]["array_job_id"]["number"] > 0
        if self.is_array_job:
            # there is no reliable way of finding the number of tasks, so we have to do it manually
            if "-a" in command:
                array_option = command[command.index("-a") + 1]
            else:
                is_array_option = [v.startswith("--array") for v in command]
                array_option = command[is_array_option.index(True)]
                if "=" not in array_option:
                    array_option = command[is_array_option.index(True) + 1]
                array_option = array_option.replace("--array=", "")
            array_task_ids = parse_job_ids(array_option)
            self.array_task_ids = sorted(array_task_ids)
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

    def _path_for_array_task_id(self, path, array_task_id):
        stem = path.stem
        # we assume all log files for array files end with -%a.suffix
        try:
            stem_job, _ = stem.rsplit("-", 1)
            return path.with_stem(f"{stem_job}-{array_task_id}")
        except ValueError as e:
            logger.warning(f"Could not parse array task id from {stem}, error was {e}")
            return path

    @property
    def output_files(self):
        if not self.is_array_job:
            return [self.output]
        else:
            files = []
            for array_task_id in self.array_task_ids:
                files.append(self._path_for_array_task_id(self.output, array_task_id))
            return files

    @property
    def error_files(self):
        if not self.is_array_job:
            return [self.error]
        else:
            files = []
            for array_task_id in self.array_task_ids:
                files.append(self._path_for_array_task_id(self.error, array_task_id))
            return files


class JobManager:
    def __init__(self, database: Path, logs_dir: Path) -> None:
        self.database = Path(database)
        self.engine = create_engine(f"sqlite:///{self.database}", echo=False)
        Base.metadata.create_all(self.engine)
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(exist_ok=True)
        self._session = Session(self.engine)

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Session(self.engine)
        return self._session

    def submit_job(
        self, name, command, output, error, dependencies: dict[str, list[int]]
    ):
        output = output or error
        error = error or output
        if output is None:
            # check if it is an array job
            if has_array_options(command):
                output = error = self.logs_dir / f"{name}.%A-%a.out"
            else:
                output = error = self.logs_dir / f"{name}.%j.out"
        else:
            output = self.logs_dir / output
            error = self.logs_dir / error
        # find dependencies
        obj_dependencies = defaultdict(list)
        for k, v in dependencies.items():
            obj_dependencies[k].extend(self.session.query(Job).filter(Job.id.in_(v)))
        job = Job(
            name=name,
            command=command,
            output=output,
            error=error,
        )
        try:
            job.submit(dependencies=obj_dependencies)
            self.session.add(job)
            self.session.flush()
            self.session.refresh(job)
            if dependencies:
                self.session.add_all(
                    [
                        JobDependency(
                            job_id=job.id,
                            waited_for_job_id=dep_id,
                            dep_type=dep_type,
                        )
                        for dep_type, dep_ids in dependencies.items()
                        for dep_id in dep_ids
                    ]
                )
        except sqlalchemy.exc.SQLAlchemyError as e:
            raise RuntimeError(
                f"""Failed to submit job with
name: {job.name}
command: {job.command}
output: {job.output}
error: {job.error}
dependencies: {dict(dependencies)}"""
            ) from e
        return job

    def update_jobs(self):
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

    def list_jobs(self, *, job_ids=None, states=None, names=None) -> list[Job]:
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

    def delete_jobs(self, **kwargs):
        jobs = self.list_jobs(**kwargs)
        for job in jobs:
            job.cancel(delete_logs=True)
            self.session.delete(job)
        # also delete job depencencies
        ids = [job.id for job in jobs]
        self.session.query(JobDependency).filter(
            JobDependency.job_id.in_(ids) | JobDependency.waited_for_job_id.in_(ids)
        ).delete()
        return jobs

    def __del__(self):
        # if there are no jobs in the database, delete the database file and the logs directory (if empty)
        if os.path.exists(self.database) and len(self.list_jobs()) == 0:
            os.remove(self.database)
        if self.logs_dir.exists() and len(os.listdir(self.logs_dir)) == 0:
            shutil.rmtree(self.logs_dir)

    def resubmit_jobs(self, **kwargs):
        jobs = self.list_jobs(**kwargs)
        for job in jobs:
            dependencies = defaultdict(list)
            if job.dependencies:
                dep_jobs = self.list_jobs(job_ids=job.dependencies)
                assert len(dep_jobs) == len(
                    job.dependencies
                ), f"{len(dep_jobs)}!= {len(job.dependencies)}"
                for dep_type, dep_job in zip(job.dep_types, dep_jobs):
                    dependencies[dep_type].append(dep_job)
            job.cancel(delete_logs=True)
            job.submit(dependencies=dependencies)
            self.session.add(job)
        return jobs


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


@click.group(cls=CustomGroup, context_settings={"show_default": True})
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


def dependency_callback(ctx, param, value) -> dict[str, list[int]]:
    """Callback for the dependency option.

    It replaces all the integer values with job ids from the local sql
    database
    """
    dependency_ids = defaultdict(list)
    if value is None:
        return dependency_ids
    pattern = r"([,?]?[a-z]*:?)(\d+:?\d*)"
    for match in re.finditer(pattern, value):
        job_prefix, job_ids = match.groups()
        job_ids = parse_job_ids(job_ids)
        dependency_ids[job_prefix or "afterany:"].extend(job_ids)
    return dependency_ids


@cli.command(
    epilog="""Example:
gridtk submit -n 10 --time=24:00:00 --wrap="my_script.sh --my-option=value my-arg0 my-arg1"
""",
    context_settings=dict(
        ignore_unknown_options=True,
        # allow_extra_args=True,
        allow_interspersed_args=False,
    ),
)
@click.option("-J", "--job-name", help="Name of the job.", default="gridtk")
@click.option("-o", "--output", help="Output file.", type=click.Path(path_type=Path))
@click.option("-e", "--error", help="Error file.", type=click.Path(path_type=Path))
@click.option(
    "-d",
    "--dependency",
    "dependencies",
    help="Dependency of the job.",
    callback=dependency_callback,
)
@click.option(
    "--repeat",
    default=1,
    type=click.INT,
    help="Submits the job N times. Each job will depend on the job before.",
)
@click.option("--print-id", is_flag=True, help="Print the id of the submitted job.")
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def submit(ctx, job_name, output, error, dependencies, repeat, print_id, command):
    """Submit a job to the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
        for _ in range(repeat):
            job = job_manager.submit_job(
                name=job_name,
                command=command,
                output=output,
                error=error,
                dependencies=dependencies,
            )
            if print_id:
                click.echo(job.id)
            dependencies["afterany:"].append(job.id)
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
            start, end = job_ids.split("-")
            return list(range(int(start), int(end) + 1))
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
    states = states.split(",")
    final_states = []
    for state in states:
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
            + ".",
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
def resubmit(ctx, job_ids, states, names):
    """Resubmit a job to the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
        jobs = job_manager.resubmit_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Resubmitted {job.id}")
        session.commit()


@cli.command()
@job_filters
@click.pass_context
def stop(ctx, job_ids, states, names):
    """Stop a job from running."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
        jobs = job_manager.list_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            job.cancel(delete_logs=False)
            click.echo(f"Stopped {job.id}")
        session.commit()


@cli.command(name="list")
@job_filters
@click.pass_context
def list_jobs(ctx: click.Context, job_ids, states, names):
    """List jobs in the queue, similar to sacct and squeue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
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
                / job.output.resolve().relative_to(job_manager.logs_dir.resolve())
            )
            table["dependencies"].append(
                ",".join([str(dep_job) for dep_job in job.dependencies])
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
def report(ctx, job_ids, states, names, array_idx):
    """Report on jobs in the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
        jobs = job_manager.list_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            report_text = ""
            report_text += f"Job ID: {job.id}\n"
            report_text += f"Name: {job.name}\n"
            report_text += f"State: {job.state} ({job.exit_code})\n"
            report_text += f"Nodes: {job.nodes}\n"
            with tempfile.NamedTemporaryFile(mode="w+t", suffix=".sh") as tmpfile:
                report_text += f"Submitted command: {job.submitted_command(tmpfile, dependencies=None)}\n"
                if job.command_in_bash:
                    report_text += (
                        f"Content of the temporary script:\n{job.command_in_bash}\n"
                    )
            output_files, error_files = job.output_files, job.error_files
            if array_idx is not None:
                array_idx = int(array_idx)
                output_files = output_files[array_idx : array_idx + 1]
                error_files = error_files[array_idx : array_idx + 1]
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
def delete(ctx, job_ids, states, names):
    """Delete a job from the queue."""
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager.session as session:
        jobs = job_manager.delete_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Deleted job {job.id} with grid ID {job.grid_id}")
        session.commit()


if __name__ == "__main__":
    cli()
