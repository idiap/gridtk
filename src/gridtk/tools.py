# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Functions that replace shell-based utilities for grid submission and
probing."""

from __future__ import annotations

import logging
import math
import os
import re
import shlex

logger = logging.getLogger(__name__)

# Constant regular expressions
QSTAT_FIELD_SEPARATOR = re.compile(":\\s+")

# Name of the user configuration file at $XDG_CONFIG_HOME
USER_CONFIGURATION = "gridtk.toml"


def str_(v: str | bytes) -> str:
    """Always returns the string representation of the given ``name``.

    If it is a bytes object, it will be converted into str.

    If it is a str object, it will simply be resurned.


    Parameters:

        v: a bytes or str object


    Returns:

        A str object
    """
    return v if not isinstance(v, bytes) else v.decode()


def qsub(
    command,
    queue=None,
    cwd=True,
    name=None,
    deps=[],
    stdout="",
    stderr="",
    env=[],
    array=None,
    context="grid",
    hostname=None,
    memfree=None,
    hvmem=None,
    gpumem=None,
    pe_opt=None,
    io_big=False,
    sge_extra_args="",
):
    """Submits a shell job to a given grid queue.

    Keyword parameters:

    command
      The command to be submitted to the grid

    queue
      A valid queue name or None, to use the default queue

    cwd
      If the job should change to the current working directory before starting

    name
      An optional name to set for the job. If not given, defaults to the script
      name being launched.

    deps
      Job ids to which this job will be dependent on

    stdout
      The standard output directory. If not given, defaults to what qsub has as a
      default.

    stderr
      The standard error directory (if not given, defaults to the stdout
      directory).

    env
      This is a list of extra variables that will be set on the environment
      running the command of your choice.

    array
      If set should be either:

      1. a string in the form m[-n[:s]] which indicates the starting range 'm',
         the closing range 'n' and the step 's'.
      2. an integer value indicating the total number of jobs to be submitted.
         This is equivalent ot set the parameter to a string "1-k:1" where "k" is
         the passed integer value
      3. a tuple that contains either 1, 2 or 3 elements indicating the start,
         end and step arguments ("m", "n", "s").

      The minimum value for "m" is 1. Giving "0" is an error.

      If submitted with this option, the job to be created will be an SGE
      parametric job. In this mode SGE does not allow individual control of each
      job. The environment variable SGE_TASK_ID will be set on the executing
      process automatically by SGE and indicates the unique identifier in the
      range for which the current job instance is for.

    context
      The setshell context in which we should try a 'qsub'. Normally you don't
      need to change the default. This variable can also be set to a context
      dictionary in which case we just setup using that context instead of
      probing for a new one, what can be fast.

    memfree
      If set, it asks the queue for a node with a minimum amount of memory
      Used only if mem is not set
      (cf. qsub -l mem_free=<...>)

    hvmem
      If set, it asks the queue for a node with a minimum amount of memory
      Used only if mem is not set
      (cf. qsub -l h_vmem=<...>)

    gpumem
      Applicable only for GPU-based queues. If set, it asks for the GPU queue
      with a minimum amount of memory. The amount should not be more than 24.
      (cf. qsub -l gpumem=<...>)

    hostname
      If set, it asks the queue to use only a subset of the available nodes
      Symbols: | for OR, & for AND, ! for NOT, etc.
      (cf. qsub -l hostname=<...>)

    pe_opt
      If set, add a -pe option when launching a job (for instance pe_exclusive* 1-)

    io_big
      If set to true, the io_big flag will be set.
      Use this flag if your process will need a lot of Input/Output operations.

    sge_extra_args
      This is used to send extra argument to SGE. Note that all its arguments are directly
      used in `qsub` command. For example, `jman submit -e "-P project_name -l pytorch=true" -- ...` will
      be translated to `qsub -P project_name -l pytorch=true -- ...`


    Returns the job id assigned to this job (integer)
    """
    from clapper.rc import UserDefaults

    scmd = ["qsub"]

    defaults = UserDefaults(USER_CONFIGURATION)

    prepend = defaults.get("sge-extra-args-prepend", "")
    sge_extra_args = f"{prepend} {sge_extra_args or ''}"
    scmd += shlex.split(sge_extra_args)

    if isinstance(queue, (str, bytes)) and queue not in (
        "all.q",
        "default",
    ):
        scmd += ["-l", queue]

    if memfree:
        scmd += ["-l", "mem_free=%s" % memfree]
    if hvmem:
        scmd += ["-l", "h_vmem=%s" % hvmem]

    if gpumem:
        scmd += ["-l", "gpumem=%s" % gpumem]

    if io_big:
        scmd += ["-l", "io_big"]

    if hostname:
        scmd += ["-l", "hostname=%s" % hostname]

    if pe_opt:
        scmd += ["-pe"] + pe_opt.split()

    if cwd:
        scmd += ["-cwd"]

    if name:
        scmd += ["-N", name]

    if deps:
        scmd += ["-hold_jid", ",".join(["%d" % k for k in deps])]

    if stdout:
        if not cwd:
            # pivot, temporarily, to home directory
            curdir = os.path.realpath(os.curdir)
            os.chdir(os.environ["HOME"])

        if not os.path.exists(stdout):
            os.makedirs(stdout, exist_ok=True)

        if not cwd:
            # go back
            os.chdir(os.path.realpath(curdir))

        scmd += ["-o", stdout]

    if stderr:
        os.makedirs(stderr, exist_ok=True)
        scmd += ["-e", stderr]
    elif stdout:  # just re-use the stdout settings
        scmd += ["-e", stdout]

    scmd += [
        "-terse"
    ]  # simplified job identifiers returned by the command line

    for k in env:
        scmd += ["-v", k]

    if array is not None:
        scmd.append("-t")
        if isinstance(array, (str, bytes)):
            try:
                i = int(array)
                scmd.append("1-%d:1" % i)
            except ValueError:
                # must be complete...
                scmd.append("%s" % array)
        if isinstance(array, int):
            scmd.append("1-%d:1" % array)
        if isinstance(array, (tuple, list)):
            if len(array) < 1 or len(array) > 3:
                raise RuntimeError(
                    "Array tuple should have length between 1 and 3"
                )
            elif len(array) == 1:
                scmd.append("%s" % array[0])
            elif len(array) == 2:
                scmd.append(f"{array[0]}-{array[1]}")
            elif len(array) == 3:
                scmd.append(f"{array[0]}-{array[1]}:{array[2]}")

    if not isinstance(command, (list, tuple)):
        command = [command]
    scmd += command

    logger.debug("Qsub command '%s'", " ".join(scmd))

    from .setshell import sexec

    jobid = str_(sexec(context, scmd))
    return int(jobid.split("\n")[-1].split(".", 1)[0])


def make_shell(shell, command):
    """Returns a single command given a shell and a command to be qsub'ed.

    Keyword parameters:

    shell
    The path to the shell to use when submitting the job.

    command
    The script path to be submitted

    Returns the command parameters to be supplied to qsub()
    """
    return ("-S", shell) + tuple(command)


def qstat(jobid, context="grid"):
    """Queries status of a given job.

    Keyword parameters:

    jobid
    The job identifier as returned by qsub()

    context
    The setshell context in which we should try a 'qsub'. Normally you
    don't
    need to change the default. This variable can also be set to a
    context
    dictionary in which case we just setup using that context instead of
    probing for a new one, what can be fast.

    Returns a dictionary with the specific job properties
    """
    scmd = ["qstat", "-j", "%d" % jobid, "-f"]

    logger.debug("Qstat command '%s'", " ".join(scmd))

    from .setshell import sexec

    data = str_(sexec(context, scmd, error_on_nonzero=False))

    # some parsing:
    retval = {}
    for line in data.split("\n"):
        s = line.strip()
        if s.lower().find("do not exist") != -1:
            return {}
        if not s or s.find(10 * "=") != -1:
            continue
        kv = QSTAT_FIELD_SEPARATOR.split(s, 1)
        if len(kv) == 2:
            retval[kv[0]] = kv[1]

    return retval


def qdel(jobid: int, context: str = "grid") -> None:
    """Halts a given job.

    Parameters:

        jobid: The job identifier as returned by :py:func:`qsub`

        context: The setshell context in which we should try a 'qsub'. Normally
            you do not need to change the default. This variable can also be
            set to a context dictionary in which case we just setup using that
            context instead of probing for a new one, what can be fast.
    """
    scmd = ["qdel", f"{jobid}"]

    logger.debug(f"qdel command '{' '.join(scmd)}'")

    from .setshell import sexec

    sexec(context, scmd, error_on_nonzero=False)


def get_array_job_slice(total_length: int) -> slice:
    """A helper function that let's you chunk a list in an SGE array job.

    Use this function like ``a = a[get_array_job_slice(len(a))]`` to only
    process a chunk of ``a``.


    Parameters:

        total_length: The length of the list that you are trying to slice


    Returns:

        A slice to be used.


    Raises:

        NotImplementedError: If "SGE_TASK_FIRST" and "SGE_TASK_STEPSIZE" are
            not 1.
    """
    sge_task_id = os.environ.get("SGE_TASK_ID")

    if sge_task_id is None:
        return slice(None)

    try:
        sge_task_int = int(sge_task_id)
    except Exception:
        return slice(None)

    if (
        os.environ["SGE_TASK_FIRST"] != "1"
        or os.environ["SGE_TASK_STEPSIZE"] != "1"
    ):
        raise NotImplementedError(
            "Values other than 1 for SGE_TASK_FIRST and SGE_TASK_STEPSIZE is not supported!"
        )

    job_id = sge_task_int - 1

    number_of_parallel_jobs = int(os.environ["SGE_TASK_LAST"])
    number_of_objects_per_job = int(
        math.ceil(total_length / number_of_parallel_jobs)
    )

    start = min(job_id * number_of_objects_per_job, total_length)
    end = min((job_id + 1) * number_of_objects_per_job, total_length)

    return slice(start, end)
