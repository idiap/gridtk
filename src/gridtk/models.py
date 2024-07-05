# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

from datetime import datetime
from pickle import dumps, loads

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

logger = logging.getLogger(__name__)


class Base:
    __allow_unmapped__ = True


Base = declarative_base(cls=Base)  # type: ignore

Status = ("submitted", "queued", "waiting", "executing", "success", "failure")


class ArrayJob(Base):
    """This class defines one element of an array job."""

    __tablename__ = "ArrayJob"

    unique = Column(Integer, primary_key=True)
    id = Column(Integer)
    job_id = Column(Integer, ForeignKey("Job.unique"))
    status = Column(Enum(*Status))
    result = Column(Integer)
    machine_name = Column(String(10))

    submit_time = Column(DateTime)
    start_time = Column(DateTime)
    finish_time = Column(DateTime)

    job = relationship("Job", backref="array", order_by=id)

    def __init__(self, id, job_id):
        self.id = id
        self.job_id = job_id
        self.status = Status[0]
        self.result = None
        self.machine_name = None  # will be set later, by the Job class

        self.submit_time = datetime.now()
        self.start_time = None
        self.finish_time = None

    def std_out_file(self):
        return (
            self.job.std_out_file() + "." + str(self.id)
            if self.job.log_dir
            else None
        )

    def std_err_file(self):
        return (
            self.job.std_err_file() + "." + str(self.id)
            if self.job.log_dir
            else None
        )

    def __str__(self):
        n = "<ArrayJob %d> of <Job %d>" % (self.id, self.job.id)
        if self.result is not None:
            r = "%s (%d)" % (self.status, self.result)
        else:
            r = "%s" % self.status
        return f"{n} : {r}"

    def format(self, format):
        """Formats the current job into a nicer string to fit into a table."""
        job_id = "%d - %d" % (self.job.id, self.id)
        queue = (
            self.job.queue_name
            if self.machine_name is None
            else self.machine_name
        )
        status = "%s" % self.status + (
            " (%d)" % self.result if self.result is not None else ""
        )

        return format.format("", job_id, queue, status)


class Job(Base):
    """This class defines one Job that was submitted to the Job Manager."""

    __tablename__ = "Job"

    unique = Column(
        Integer, primary_key=True
    )  # The unique ID of the job (not corresponding to the grid ID)
    command_line = Column(
        String(255)
    )  # The command line to execute, converted to one string
    name = Column(String(20))  # A hand-chosen name for the task
    queue_name = Column(String(20))  # The name of the queue
    machine_name = Column(
        String(10)
    )  # The name of the machine in which the job is run
    grid_arguments = Column(
        String(255)
    )  # The kwargs arguments for the job submission (e.g. in the grid)
    id = Column(Integer)  # The ID of the job as given from the grid
    exec_dir = Column(
        String(255)
    )  # The directory in which the command should be executed
    log_dir = Column(
        String(255)
    )  # The directory where the log files will be put to
    array_string = Column(
        String(255)
    )  # The array string (only needed for re-submission)
    stop_on_failure = Column(
        Boolean
    )  # An indicator whether to stop depending jobs when this job finishes with an error

    submit_time = Column(DateTime)
    start_time = Column(DateTime)
    finish_time = Column(DateTime)

    status = Column(Enum(*Status))
    result = Column(Integer)

    def __init__(
        self,
        command_line,
        name=None,
        exec_dir=None,
        log_dir=None,
        array_string=None,
        queue_name="local",
        machine_name=None,
        stop_on_failure=False,
        **kwargs,
    ):
        """Constructs a Job object without an ID (needs to be set later)."""
        self.command_line = dumps(command_line)
        self.name = name
        self.queue_name = (
            queue_name  # will be set during the queue command later
        )
        self.machine_name = (
            machine_name  # will be set during the execute command later
        )
        self.grid_arguments = dumps(kwargs)
        self.exec_dir = exec_dir
        self.log_dir = log_dir
        self.stop_on_failure = stop_on_failure
        self.array_string = dumps(array_string)
        self.submit()

    def submit(self, new_queue=None):
        """Sets the status of this job to 'submitted'."""
        self.status = "submitted"
        self.result = None
        self.machine_name = None
        if new_queue is not None:
            self.queue_name = new_queue
        for array_job in self.array:
            array_job.status = "submitted"
            array_job.result = None
            array_job.machine_name = None
        self.submit_time = datetime.now()
        self.start_time = None
        self.finish_time = None

    def queue(self, new_job_id=None, new_job_name=None, queue_name=None):
        """Sets the status of this job to 'queued' or 'waiting'."""
        # update the job id (i.e., when the job is executed in the grid)
        if new_job_id is not None:
            self.id = new_job_id

        if new_job_name is not None:
            self.name = new_job_name

        if queue_name is not None:
            self.queue_name = queue_name

        new_status = "queued"
        self.result = None
        # check if we have to wait for another job to finish
        for job in self.get_jobs_we_wait_for():
            if job.status not in ("success", "failure"):
                new_status = "waiting"
            elif self.stop_on_failure and job.status == "failure":
                new_status = "failure"

        # reset the queued jobs that depend on us to waiting status
        for job in self.get_jobs_waiting_for_us():
            if job.status == "queued":
                job.status = "failure" if new_status == "failure" else "waiting"

        self.status = new_status
        for array_job in self.array:
            if array_job.status not in ("success", "failure"):
                array_job.status = new_status

    def execute(self, array_id=None, machine_name=None):
        """Sets the status of this job to 'executing'."""
        self.status = "executing"
        if array_id is not None:
            for array_job in self.array:
                if array_job.id == array_id:
                    array_job.status = "executing"
                    if machine_name is not None:
                        array_job.machine_name = machine_name
                        array_job.start_time = datetime.now()
        elif machine_name is not None:
            self.machine_name = machine_name
        if self.start_time is None:
            self.start_time = datetime.now()

        # sometimes, the 'finish' command did not work for array jobs,
        # so check if any old job still has the 'executing' flag set
        for job in self.get_jobs_we_wait_for():
            if job.array and job.status == "executing":
                job.finish(0, -1)

    def finish(self, result, array_id=None):
        """Sets the status of this job to 'success' or 'failure'."""
        # check if there is any array job still running
        new_status = "success" if result == 0 else "failure"
        new_result = result
        finished = True
        if array_id is not None:
            for array_job in self.array:
                if array_job.id == array_id:
                    array_job.status = new_status
                    array_job.result = result
                    array_job.finish_time = datetime.now()
                if array_job.status not in ("success", "failure"):
                    finished = False
                elif new_result == 0:
                    new_result = array_job.result

        if finished:
            # There was no array job, or all array jobs finished
            self.status = "success" if new_result == 0 else "failure"
            self.result = new_result
            self.finish_time = datetime.now()

            # update all waiting jobs
            for job in self.get_jobs_waiting_for_us():
                if job.status == "waiting":
                    job.queue()

    def refresh(self):
        """Refreshes the status information."""
        if self.status == "executing" and self.array:
            new_result = 0
            for array_job in self.array:
                if array_job.status == "failure" and new_result is not None:
                    new_result = array_job.result
                elif array_job.status not in ("success", "failure"):
                    new_result = None
            if new_result is not None:
                self.status = "success" if new_result == 0 else "failure"
                self.result = new_result

    def get_command_line(self):
        """Returns the command line for the job."""
        # In python 2, the command line is unicode, which needs to be converted to string before pickling;
        # In python 3, the command line is bytes, which can be pickled directly
        return (
            loads(self.command_line)
            if isinstance(self.command_line, bytes)
            else loads(self.command_line.encode())
        )

    def set_command_line(self, command_line):
        """Sets / overwrites the command line for the job."""
        self.command_line = dumps(command_line)

    def get_exec_dir(self):
        """Returns the command line for the job."""
        # In python 2, the command line is unicode, which needs to be converted to string before pickling;
        # In python 3, the command line is bytes, which can be pickled directly
        return (
            str(os.path.realpath(self.exec_dir))
            if self.exec_dir is not None
            else None
        )

    def get_array(self):
        """Returns the array arguments for the job; usually a string."""
        # In python 2, the command line is unicode, which needs to be converted to string before pickling;
        # In python 3, the command line is bytes, which can be pickled directly
        return (
            loads(self.array_string)
            if isinstance(self.array_string, bytes)
            else loads(self.array_string.encode())
        )

    def get_arguments(self):
        """Returns the additional options for the grid (such as the queue,
        memory requirements, ...)."""
        # In python 2, the command line is unicode, which needs to be converted to string before pickling;
        # In python 3, the command line is bytes, which can be pickled directly
        args = (
            loads(self.grid_arguments)["kwargs"]
            if isinstance(self.grid_arguments, bytes)
            else loads(self.grid_arguments.encode())["kwargs"]
        )
        # in any case, the commands have to be converted to str
        retval = {}
        if "pe_opt" in args:
            retval["pe_opt"] = args["pe_opt"]
        if "memfree" in args and args["memfree"] is not None:
            retval["memfree"] = args["memfree"]
        if "hvmem" in args and args["hvmem"] is not None:
            retval["hvmem"] = args["hvmem"]
        if "gpumem" in args and args["gpumem"] is not None:
            retval["gpumem"] = args["gpumem"]
        if "env" in args and len(args["env"]) > 0:
            retval["env"] = args["env"]
        if "io_big" in args and args["io_big"]:
            retval["io_big"] = True
        if "sge_extra_args" in args:
            retval["sge_extra_args"] = args["sge_extra_args"]

        # also add the queue
        if self.queue_name is not None:
            retval["queue"] = str(self.queue_name)

        return retval

    def set_arguments(self, **kwargs):
        self.grid_arguments = dumps(kwargs)

    def get_jobs_we_wait_for(self):
        return [
            j.waited_for_job
            for j in self.jobs_we_have_to_wait_for
            if j.waited_for_job is not None
        ]

    def get_jobs_waiting_for_us(self):
        return [
            j.waiting_job
            for j in self.jobs_that_wait_for_us
            if j.waiting_job is not None
        ]

    def std_out_file(self, array_id=None):
        return (
            os.path.join(
                self.log_dir,
                (self.name if self.name else "job") + ".o" + str(self.id),
            )
            if self.log_dir
            else None
        )

    def std_err_file(self, array_id=None):
        return (
            os.path.join(
                self.log_dir,
                (self.name if self.name else "job") + ".e" + str(self.id),
            )
            if self.log_dir
            else None
        )

    def _cmdline(self):
        cmdline = self.get_command_line()
        c = ""
        for cmd in cmdline:
            if cmd[0] == "-":
                c += "%s " % cmd
            else:
                c += "'%s' " % cmd
        return c

    def __str__(self):
        id = "%d (%d)" % (self.unique, self.id)
        if self.machine_name:
            m = f"{self.queue_name} - {self.machine_name}"
        else:
            m = self.queue_name
        if self.array:
            a = "[%d-%d:%d]" % self.get_array()
        else:
            a = ""
        if self.name is not None:
            n = f"<Job: {id} {a} - '{self.name}'>"
        else:
            n = "<Job: %s>" % id
        if self.result is not None:
            r = "%s (%d)" % (self.status, self.result)
        else:
            r = "%s" % self.status
        return f"{n} | {m} : {r} -- {self._cmdline()}"

    def format(self, format, dependencies=0, limit_command_line=None):
        """Formats the current job into a nicer string to fit into a table."""
        command_line = self._cmdline()
        if (
            limit_command_line is not None
            and len(command_line) > limit_command_line
        ):
            command_line = command_line[: limit_command_line - 3] + "..."

        job_id = "%d" % self.id + (
            " [%d-%d:%d]" % self.get_array() if self.array else ""
        )
        status = "%s" % self.status + (
            " (%d)" % self.result if self.result is not None else ""
        )
        queue = (
            self.queue_name if self.machine_name is None else self.machine_name
        )
        if limit_command_line is None:
            grid_opt = self.get_arguments()
            if grid_opt:
                # add additional information about the job at the end
                command_line = (
                    "<"
                    + ",".join(
                        [f"{key}={value}" for key, value in grid_opt.items()]
                    )
                    + ">: "
                    + command_line
                )
            if self.exec_dir is not None:
                command_line += (
                    "; [Executed in directory: '%s']" % self.exec_dir
                )

        if dependencies:
            deps = str(
                sorted(
                    list({dep.unique for dep in self.get_jobs_we_wait_for()})
                )
            )
            if dependencies < len(deps):
                deps = deps[: dependencies - 3] + "..."
            return format.format(
                self.unique,
                job_id,
                queue[:12],
                status,
                str(self.name),
                deps,
                command_line,
            )
        else:
            return format.format(
                self.unique,
                job_id,
                queue[:12],
                status,
                str(self.name),
                command_line,
            )


class JobDependence(Base):
    """This table defines a many-to-many relationship between Jobs."""

    __tablename__ = "JobDependence"
    id = Column(Integer, primary_key=True)
    waiting_job_id = Column(
        Integer, ForeignKey("Job.unique")
    )  # The ID of the waiting job
    waited_for_job_id = Column(
        Integer, ForeignKey("Job.unique")
    )  # The ID of the job to wait for

    # This is twisted: The 'jobs_we_have_to_wait_for' field in the Job class needs to be joined with the waiting job id, so that jobs_we_have_to_wait_for.waiting_job is correct
    # Honestly, I am lost but it seems to work...
    waiting_job = relationship(
        "Job",
        backref="jobs_we_have_to_wait_for",
        primaryjoin=(Job.unique == waiting_job_id),
        order_by=id,
    )  # The job that is waited for
    waited_for_job = relationship(
        "Job",
        backref="jobs_that_wait_for_us",
        primaryjoin=(Job.unique == waited_for_job_id),
        order_by=id,
    )  # The job that waits

    def __init__(self, waiting_job_id, waited_for_job_id):
        self.waiting_job_id = waiting_job_id
        self.waited_for_job_id = waited_for_job_id


def add_job(
    session,
    command_line,
    name="job",
    dependencies=[],
    array=None,
    exec_dir=None,
    log_dir=None,
    stop_on_failure=False,
    **kwargs,
):
    """Helper function to create a job, add the dependencies and the array
    jobs."""
    job = Job(
        command_line=command_line,
        name=name,
        exec_dir=exec_dir,
        log_dir=log_dir,
        array_string=array,
        stop_on_failure=stop_on_failure,
        kwargs=kwargs,
    )

    session.add(job)
    session.flush()
    session.refresh(job)

    # by default id and unique id are identical, but the id might be overwritten later on
    job.id = job.unique

    for d in dependencies:
        if d == job.unique:
            logger.warn("Adding self-dependency of job %d is not allowed" % d)
            continue
        depending = list(session.query(Job).filter(Job.unique == d))
        if len(depending):
            session.add(JobDependence(job.unique, depending[0].unique))
        else:
            logger.warn(
                "Could not find dependent job with id %d in database" % d
            )

    if array:
        (start, stop, step) = array
        # add array jobs
        for i in range(start, stop + 1, step):
            session.add(ArrayJob(i, job.unique))

    session.commit()

    return job


def times(job):
    """Returns a string containing timing information for teh given job, which
    might be a :py:class:`Job` or an :py:class:`ArrayJob`."""
    timing = "Submitted: %s" % job.submit_time.ctime()
    if job.start_time is not None:
        timing += "\nStarted  : {} \t Job waited  : {}".format(
            job.start_time.ctime(),
            job.start_time - job.submit_time,
        )
    if job.finish_time is not None:
        timing += "\nFinished : {} \t Job executed: {}".format(
            job.finish_time.ctime(),
            job.finish_time - job.start_time,
        )
    return timing
