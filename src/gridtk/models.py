# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import re
import shlex
import subprocess
import tempfile
import warnings

from pathlib import Path
from sqlite3 import Connection as SQLite3Connection
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String, Table, event
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

from .tools import job_ids_from_dep_str, replace_job_ids_in_dep_str


# enable foreign key support in sqlite3
# https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key support in sqlite3."""
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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

sacct only returns these states https://slurm.schedmd.com/sacct.html#lbAG
"""


class ObjectValue(TypeDecorator):
    """Store JSON-serializable objects in a SQLite3 database."""

    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value)
            elif isinstance(value, Path):
                value = str(value.absolute())
            else:
                raise TypeError(
                    f"ObjectValue must be a dict, list, tuple or Path but got {type(value)}"
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
    """Base class for declarative models."""

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


class Job(Base):
    """Represents a job in the database."""

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
        with tempfile.NamedTemporaryFile(mode="w+t", suffix=".sh", delete=False) as fh:
            try:
                command = self.submitted_command(fh=fh, session=session)
                output = subprocess.check_output(
                    command,
                    text=True,
                )
            finally:
                # remove the temporary file here because we don't want it
                # deleted after fh.close() is called
                Path(fh.name).unlink(missing_ok=True)
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
            warnings.warn(f"Could not update the job state for {self}")
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
