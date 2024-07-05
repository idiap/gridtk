# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Defines the job manager which can help you managing submitted grid jobs."""

from __future__ import annotations

import logging
import os
import re
import sys

from .manager import JobManager
from .models import Job, add_job
from .setshell import environ
from .tools import make_shell, qdel, qstat, qsub

logger = logging.getLogger(__name__)


class JobManagerSGE(JobManager):
    """The JobManager will submit and control the status of submitted jobs."""

    def __init__(self, context="grid", **kwargs):
        """Initializes this object with a state file and a method for
        qsub'bing.

        Keyword parameters:

        statefile
        The file containing a valid status database for the manager. If
        the file
        does not exist it is initialized. If it exists, it is loaded.

        context
        The context to provide when setting up the environment to call
        the SGE
        utilities such as qsub, qstat and qdel (normally 'grid', which
        also
        happens to be default)
        """
        self.context = environ(context)
        JobManager.__init__(self, **kwargs)

    def _queue(self, kwargs):
        """The hard resource_list comes like this: '<qname>=TRUE,mem=128M'.

        To process it we have to split it twice (',' and then on '='),
        create a dictionary and extract just the qname
        """
        if "hard resource_list" not in kwargs:
            return "all.q"
        d = dict(
            [k.split("=") for k in kwargs["hard resource_list"].split(",")]
        )
        for k in d:
            if k[0] == "q" and d[k] == "TRUE":
                return k
        return "all.q"

    def _submit_to_grid(
        self, job, name, array, dependencies, log_dir, verbosity, **kwargs
    ):
        # ... what we will actually submit to the grid is a wrapper script that will call the desired command...
        # get the name of the file that was called originally
        jman = self.wrapper_script
        python = sys.executable

        # get the grid id's for the dependencies and remove duplicates
        dependent_jobs = self.get_jobs(dependencies)
        deps = sorted(list({j.id for j in dependent_jobs}))

        # make sure log directory is created and is a directory
        os.makedirs(job.log_dir, exist_ok=True)
        assert os.path.isdir(
            job.log_dir
        ), "Please make sure --log-dir `{}' either does not exist or is a directory.".format(
            job.log_dir
        )

        # generate call to the wrapper script
        command = make_shell(
            python,
            [jman, "-%sd" % ("v" * verbosity), self._database, "run-job"],
        )
        q_array = "%d-%d:%d" % array if array else None
        grid_id = qsub(
            command,
            context=self.context,
            name=name,
            deps=deps,
            array=q_array,
            stdout=log_dir,
            stderr=log_dir,
            **kwargs,
        )

        # get the result of qstat
        status = qstat(grid_id, context=self.context)

        # set the grid id of the job
        job.queue(
            new_job_id=int(status["job_number"]),
            new_job_name=status["job_name"],
            queue_name=self._queue(status),
        )

        logger.info(
            "Submitted job '%s' with dependencies '%s' to the SGE grid."
            % (job, str(deps))
        )

        if (
            "io_big" in kwargs
            and kwargs["io_big"]
            and ("queue" not in kwargs or kwargs["queue"] == "all.q")
        ):
            logger.warn(
                "This job will never be executed since the 'io_big' flag is not available for the 'all.q'."
            )
        if "pe_opt" in kwargs and (
            "queue" not in kwargs
            or kwargs["queue"]
            not in ("q1dm", "q_1day_mth", "q1wm", "q_1week_mth")
        ):
            logger.warn(
                "This job will never be executed since the queue '%s' does not support multi-threading (pe_mth) -- use 'q1dm' or 'q1wm' instead."
                % kwargs["queue"]
                if "queue" in kwargs
                else "all.q"
            )
        if (
            "gpumem" in kwargs
            and "queue" in kwargs
            and kwargs["queue"] in ("gpu", "lgpu", "sgpu", "vsgpu")
            and int(re.sub("\\D", "", kwargs["gpumem"])) > 24
        ):
            logger.warn(
                "This job will never be executed since the GPU queue '%s' cannot have more than 24GB of memory."
                % kwargs["queue"]
            )

        assert job.id == grid_id
        return job.unique

    def submit(
        self,
        command_line,
        name=None,
        array=None,
        dependencies=[],
        exec_dir=None,
        log_dir="logs",
        dry_run=False,
        verbosity=0,
        stop_on_failure=False,
        **kwargs,
    ):
        """Submits a job that will be executed in the grid."""
        # add job to database
        self.lock()
        job = add_job(
            self.session,
            command_line,
            name,
            dependencies,
            array,
            exec_dir=exec_dir,
            log_dir=log_dir,
            stop_on_failure=stop_on_failure,
            context=self.context,
            **kwargs,
        )
        logger.info("Added job '%s' to the database." % job)
        if dry_run:
            print("Would have added the Job")
            print(job)
            print(
                "to the database to be executed in the grid with options:",
                str(kwargs),
            )
            self.session.delete(job)
            logger.info(
                "Deleted job '%s' from the database due to dry-run option" % job
            )
            job_id = None

        else:
            job_id = self._submit_to_grid(
                job, name, array, dependencies, log_dir, verbosity, **kwargs
            )

        self.session.commit()
        self.unlock()

        return job_id

    def communicate(self, job_ids=None):
        """Communicates with the SGE grid (using qstat) to see if jobs are
        still running."""
        self.lock()
        # iterate over all jobs
        jobs = self.get_jobs(job_ids)
        for job in jobs:
            job.refresh()
            if (
                job.status in ("queued", "executing", "waiting")
                and job.queue_name != "local"
            ):
                status = qstat(job.id, context=self.context)
                if len(status) == 0:
                    job.status = "failure"
                    job.result = 70  # ASCII: 'F'
                    logger.warn(
                        "The job '%s' was not executed successfully (maybe a time-out happened). Please check the log files."
                        % job
                    )
                    for array_job in job.array:
                        if array_job.status in ("queued", "executing"):
                            array_job.status = "failure"
                            array_job.result = 70  # ASCII: 'F'

        self.session.commit()
        self.unlock()

    def resubmit(
        self,
        job_ids=None,
        also_success=False,
        running_jobs=False,
        new_command=None,
        verbosity=0,
        keep_logs=False,
        **kwargs,
    ):
        """Re-submit jobs automatically."""
        self.lock()
        # iterate over all jobs
        jobs = self.get_jobs(job_ids)
        if new_command is not None:
            if len(jobs) == 1:
                jobs[0].set_command_line(new_command)
            else:
                logger.warn(
                    "Ignoring new command since no single job id was specified"
                )
        accepted_old_status = (
            ("submitted", "success", "failure")
            if also_success
            else (
                "submitted",
                "failure",
            )
        )
        for job in jobs:
            # check if this job needs re-submission
            if running_jobs or job.status in accepted_old_status:
                grid_status = qstat(job.id, context=self.context)
                if len(grid_status) != 0:
                    logger.warn(
                        "Deleting job '%d' since it was still running in the grid."
                        % job.unique
                    )
                    qdel(job.id, context=self.context)
                # re-submit job to the grid
                arguments = job.get_arguments()
                arguments.update(**kwargs)
                if "queue" not in arguments or arguments["queue"] == "all.q":
                    for arg in ("hvmem", "pe_opt", "io_big"):
                        if arg in arguments:
                            del arguments[arg]
                job.set_arguments(kwargs=arguments)
                # delete old status and result of the job
                if not keep_logs:
                    self.delete_logs(job)
                job.submit()
                if job.queue_name == "local" and "queue" not in arguments:
                    logger.warn(
                        "Re-submitting job '%s' locally (since no queue name is specified)."
                        % job
                    )
                else:
                    deps = [dep.unique for dep in job.get_jobs_we_wait_for()]
                    logger.debug(
                        "Re-submitting job '%s' with dependencies '%s' to the grid."
                        % (job, deps)
                    )
                    self._submit_to_grid(
                        job,
                        job.name,
                        job.get_array(),
                        deps,
                        job.log_dir,
                        verbosity,
                        **arguments,
                    )

                # commit after each job to avoid failures of not finding the job during execution in the grid
                self.session.commit()
        self.unlock()

    def run_job(self, job_id, array_id=None):
        """Overwrites the run-job command from the manager to extract the
        correct job id before calling base class implementation."""
        # get the unique job id from the given grid id
        self.lock()
        jobs = list(self.session.query(Job).filter(Job.id == job_id))
        if len(jobs) != 1:
            self.unlock()
            raise ValueError(
                "Could not find job id '%d' in the database'" % job_id
            )
        job_id = jobs[0].unique
        self.unlock()
        # call base class implementation with the corrected job id
        return JobManager.run_job(self, job_id, array_id)

    def stop_jobs(self, job_ids):
        """Stops the jobs in the grid."""
        self.lock()

        jobs = self.get_jobs(job_ids)
        for job in jobs:
            if job.status in ("executing", "queued", "waiting"):
                qdel(job.id, context=self.context)
                logger.info("Stopped job '%s' in the SGE grid." % job)
            job.submit()

            self.session.commit()
        self.unlock()
