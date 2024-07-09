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
import shutil
import subprocess

from collections.abc import Iterable
from pathlib import Path

import sqlalchemy

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .models import Base, Job, JobDependency
from .tools import job_ids_from_dep_str, parse_array_indexes


def update_job_statuses(grid_ids: Iterable[int]) -> dict[int, dict]:
    """Retrieve the status of the jobs in the database."""
    status = dict()
    output = subprocess.check_output(
        ["sacct", "-j", ",".join([str(x) for x in grid_ids]), "--json"],
        text=True,
    )
    for job in json.loads(output)["jobs"]:
        status[job["job_id"]] = job
    return status


def get_dependent_jobs_recursive(jobs: Iterable[Job]) -> list[Job]:
    """Get all the dependent jobs of a job recursively."""
    dependent_jobs = set()
    for job in jobs:
        dependent_jobs.add(job)
        dependent_jobs.update(get_dependent_jobs_recursive(job.dependents))
    return list(sorted(dependent_jobs, key=lambda x: x.id))


class JobManager:
    """Implements a job manager for Slurm."""

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
        self.session.flush()

    def list_jobs(
        self,
        *,
        job_ids=None,
        states=None,
        names=None,
        update_jobs=True,
        dependents=False,
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
        if dependents:
            jobs = get_dependent_jobs_recursive(jobs)

        return jobs

    def stop_jobs(self, delete=False, **kwargs):
        """Stop all jobs that match the given criteria."""
        jobs = self.list_jobs(**kwargs)
        for job in jobs:
            job.cancel(delete_logs=delete)
        if delete:
            with self.session.no_autoflush:
                for job in jobs:
                    self.session.delete(job)
                # also delete job dependencies
                ids = [job.id for job in jobs]
                self.session.query(JobDependency).filter(
                    JobDependency.job_id.in_(ids)
                    | JobDependency.waited_for_job_id.in_(ids)
                ).delete()
        return jobs

    def delete_jobs(self, **kwargs):
        return self.stop_jobs(delete=True, **kwargs)

    def resubmit_jobs(self, **kwargs):
        jobs = self.list_jobs(**kwargs)
        for job in jobs:
            job.cancel(delete_logs=True)
            job.submit(session=self.session)
            self.session.add(job)
        return jobs

    def __del__(self):
        # if there are no jobs in the database, delete the database file and the logs directory (if empty)
        with self:
            if (
                Path(self.database).exists()
                and len(self.list_jobs(update_jobs=False)) == 0
            ):
                Path(self.database).unlink()
            if self.logs_dir.exists() and len(os.listdir(self.logs_dir)) == 0:
                shutil.rmtree(self.logs_dir)
        self.engine.dispose()
