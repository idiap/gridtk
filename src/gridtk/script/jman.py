# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""A logging Idiap/SGE job manager."""

from __future__ import annotations

__epilog__ = """ For a list of available commands:
  >>> %(prog)s --help

  For a list of options for a particular command:
  >>> %(prog)s <command> --help
"""

import argparse
import logging
import os
import string
import sys

from .. import local, sge
from ..models import Status

logger = logging.getLogger("gridtk")

GPU_QUEUES = ["gpu", "lgpu", "sgpu", "gpum", "vsgpu"]
QUEUES = ["all.q", "q1d", "q1w", "q1m", "q1dm", "q1wm"] + GPU_QUEUES


def appropriate_for_gpu(args, kwargs):
    # don't set these for GPU processing or the maximum virtual memory will be
    # set on ulimit
    kwargs.pop("memfree", None)
    kwargs.pop("hvmem", None)

    if args.memory is None:
        return

    # if this is a GPU queue and args.memory is provided, we set gpumem flag
    # remove 'G' last character from the args.memory string
    if args.memory.isdigit():
        kwargs["gpumem"] = args.memory  # assign directly
    elif args.memory.endswith("G"):
        kwargs["gpumem"] = args.memory[:-1]  # remove G at the end


def setup(args):
    """Returns the JobManager and sets up the basic infrastructure."""
    kwargs = {
        "wrapper_script": args.wrapper_script,
        "debug": args.verbose == 3,
        "database": args.database,
    }

    if args.local:
        jm = local.JobManagerLocal(**kwargs)
    else:
        jm = sge.JobManagerSGE(**kwargs)

    # set-up logging
    if args.verbose not in range(0, 4):
        raise ValueError(
            "The verbosity level %d does not exist. Please reduce the number of '--verbose' parameters in your call to maximum 3"
            % args.verbose
        )

    # set up the verbosity level of the logging system
    log_level = {
        0: logging.ERROR,
        1: logging.WARNING,
        2: logging.INFO,
        3: logging.DEBUG,
    }[args.verbose]

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(log_level)

    return jm


def get_array(array):
    if array is None:
        return None
    start = array.find("-")
    if start == -1:
        a = 1
        b = int(array)
        c = 1
    else:
        a = int(array[0:start])
        step = array.find(":")
        if step == -1:
            b = int(array[start + 1 :])
            c = 1
        else:
            b = int(array[start + 1 : step])
            c = int(array[step + 1 :])

    return (a, b, c)


def get_ids(jobs):
    if jobs is None:
        return None
    indexes = []
    for job in jobs:
        if "-" not in job and "+" not in job:
            index = int(job)
            indexes.append(index)
        # check if a range is specified
        elif "-" in job and "+" not in job:
            first, last = job.split("-", 1)
            indexes.extend(range(int(first), int(last) + 1))
        # check if a plus sign is specified
        elif "+" in job and "-" not in job:
            first, add = job.split("+", 1)
            first, add = int(first), int(add)
            indexes.extend(range(first, first + add + 1))
    return indexes


def get_memfree(memory, parallel):
    """Computes the memory required for the memfree field."""
    number = int(memory.rstrip(string.ascii_letters))
    memtype = memory.lstrip(string.digits)
    if not memtype:
        memtype = "G"
    return "%d%s" % (number * parallel, memtype)


def submit(args):
    """Submission command."""
    # set full path to command
    if args.job[0] == "--":
        del args.job[0]
    if not os.path.isabs(args.job[0]):
        args.job[0] = os.path.abspath(args.job[0])

    jm = setup(args)
    kwargs = {
        "queue": args.qname,
        "cwd": True,
        "verbosity": args.verbose,
        "name": args.name,
        "env": args.env,
        "memfree": args.memory,
        "io_big": args.io_big,
        "sge_extra_args": args.sge_extra_args,
    }

    if args.array is not None:
        kwargs["array"] = get_array(args.array)
    if args.exec_dir is not None:
        kwargs["exec_dir"] = args.exec_dir
    if args.log_dir is not None:
        kwargs["log_dir"] = args.log_dir
    if args.dependencies is not None:
        kwargs["dependencies"] = args.dependencies
    if args.qname != "all.q":
        kwargs["hvmem"] = args.memory
    if args.qname in GPU_QUEUES:
        appropriate_for_gpu(args, kwargs)
    if args.parallel is not None:
        kwargs["pe_opt"] = "pe_mth %d" % args.parallel
        if args.memory is not None:
            kwargs["memfree"] = get_memfree(args.memory, args.parallel)
    kwargs["dry_run"] = args.dry_run
    kwargs["stop_on_failure"] = args.stop_on_failure

    # submit the job(s)
    for _ in range(args.repeat):
        job_id = jm.submit(args.job, **kwargs)
        dependencies = kwargs.get("dependencies", [])
        dependencies.append(job_id)
        kwargs["dependencies"] = dependencies

    if args.print_id:
        print(job_id, end="")


def resubmit(args):
    """Re-submits the jobs with the given ids."""
    jm = setup(args)

    kwargs = {"cwd": True, "verbosity": args.verbose}
    if args.qname is not None:
        kwargs["queue"] = args.qname
    if args.memory is not None:
        kwargs["memfree"] = args.memory
        if args.qname not in (None, "all.q"):
            kwargs["hvmem"] = args.memory
        if args.qname in GPU_QUEUES:
            appropriate_for_gpu(args, kwargs)
    if args.parallel is not None:
        kwargs["pe_opt"] = "pe_mth %d" % args.parallel
        kwargs["memfree"] = get_memfree(args.memory, args.parallel)
    if args.io_big:
        kwargs["io_big"] = True
    if args.no_io_big:
        kwargs["io_big"] = False

    jm.resubmit(
        get_ids(args.job_ids),
        args.also_success,
        args.running_jobs,
        args.overwrite_command,
        keep_logs=args.keep_logs,
        **kwargs,
    )


def run_scheduler(args):
    """Runs the scheduler on the local machine.

    To stop it, please use Ctrl-C.
    """
    if not args.local:
        raise ValueError(
            "The execute command can only be used with the '--local' command line option"
        )
    jm = setup(args)
    jm.run_scheduler(
        parallel_jobs=args.parallel,
        job_ids=get_ids(args.job_ids),
        sleep_time=args.sleep_time,
        die_when_finished=args.die_when_finished,
        no_log=args.no_log_files,
        nice=args.nice,
        verbosity=args.verbose,
    )


def list(args):
    """Lists the jobs in the given database."""
    jm = setup(args)

    if not args.local:
        # update the status of jobs from SGE before listing them.
        jm.communicate(job_ids=get_ids(args.job_ids))

    jm.list(
        job_ids=get_ids(args.job_ids),
        print_array_jobs=args.print_array_jobs,
        print_dependencies=args.print_dependencies,
        status=args.status,
        long=args.long,
        print_times=args.print_times,
        ids_only=args.ids_only,
        names=args.names,
    )


def communicate(args):
    """Uses qstat to get the status of the requested jobs."""
    if args.local:
        raise ValueError(
            "The communicate command can only be used without the '--local' command line option"
        )
    jm = setup(args)
    jm.communicate(job_ids=get_ids(args.job_ids))


def report(args):
    """Reports the results of the finished (and unfinished) jobs."""
    jm = setup(args)
    jm.report(
        job_ids=get_ids(args.job_ids),
        array_ids=get_ids(args.array_ids),
        output=not args.errors_only,
        error=not args.output_only,
        status=args.status,
        name=args.name,
    )


def stop(args):
    """Stops (qdel's) the jobs with the given ids."""
    if args.local:
        raise ValueError(
            "Stopping commands locally is not supported (please kill them yourself)"
        )
    jm = setup(args)
    jm.stop_jobs(get_ids(args.job_ids))


def delete(args):
    """Deletes the jobs from the job manager.

    If the jobs are still running in the grid, they are stopped.
    """
    jm = setup(args)

    # first, stop the jobs if they are running in the grid
    if not args.local and "executing" in args.status:
        stop(args)

    # then, delete them from the database
    jm.delete(
        job_ids=get_ids(args.job_ids),
        array_ids=get_ids(args.array_ids),
        delete_logs=not args.keep_logs,
        delete_log_dir=not args.keep_log_dir,
        status=args.status,
    )


def run_job(args):
    """Starts the wrapper script to execute a job, interpreting the JOB_ID and
    SGE_TASK_ID keywords that are set by the grid or by us."""
    jm = setup(args)
    job_id = int(os.environ["JOB_ID"])
    array_id = (
        int(os.environ["SGE_TASK_ID"])
        if os.environ["SGE_TASK_ID"] != "undefined"
        else None
    )
    jm.run_job(job_id, array_id)


class AliasedSubParsersAction(argparse._SubParsersAction):
    """Hack taken from https://gist.github.com/471779 to allow aliases in
    argparse for python 2.x (this has been implemented on python 3.2)"""

    class _AliasedPseudoAction(argparse.Action):
        def __init__(self, name, aliases, help):
            dest = name
            if aliases:
                dest += " (%s)" % ",".join(aliases)
            sup = super()
            sup.__init__(option_strings=[], dest=dest, help=help)

    def add_parser(self, name, **kwargs):
        if "aliases" in kwargs:
            aliases = kwargs["aliases"]
            del kwargs["aliases"]
        else:
            aliases = []

        parser = super().add_parser(name, **kwargs)

        # Make the aliases work.
        for alias in aliases:
            self._name_parser_map[alias] = parser
        # Make the help text reflect them, first removing old help entry.
        if "help" in kwargs:
            help = kwargs.pop("help")
            self._choices_actions.pop()
            pseudo_action = self._AliasedPseudoAction(name, aliases, help)
            self._choices_actions.append(pseudo_action)

        return parser


def main(command_line_options=None):
    from importlib.metadata import version

    from clapper.rc import UserDefaults

    from ..tools import USER_CONFIGURATION

    defaults = UserDefaults(USER_CONFIGURATION)

    formatter = argparse.ArgumentDefaultsHelpFormatter
    parser = argparse.ArgumentParser(
        description=__doc__, epilog=__epilog__, formatter_class=formatter
    )
    # part of the hack to support aliases in subparsers
    parser.register("action", "parsers", AliasedSubParsersAction)

    # general options
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase the verbosity level from 0 (only error messages) to 1 (warnings), 2 (log messages), 3 (debug information) by adding the --verbose option as often as desired (e.g. '-vvv' for debug).",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="gridtk version %s" % version(__name__.split(".", 1)[0]),
    )
    parser.add_argument(
        "-d",
        "--database",
        "--db",
        metavar="DATABASE",
        default="submitted.sql3",
        help='replace the default database "submitted.sql3" by one provided by you.',
    )

    parser.add_argument(
        "-l",
        "--local",
        action="store_true",
        help="Uses the local job manager instead of the SGE one.",
    )
    cmdparser = parser.add_subparsers(
        title="commands", help="commands accepted by %(prog)s"
    )

    # subcommand 'submit'
    submit_parser = cmdparser.add_parser(
        "submit",
        aliases=["sub"],
        formatter_class=formatter,
        help="Submits jobs to the SGE/Local job scheduler and logs them in a database.",
    )
    submit_parser.add_argument(
        "-q",
        "--queue",
        metavar="QNAME",
        dest="qname",
        default="all.q",
        choices=QUEUES,
        help="the name of the SGE queue to submit the job to",
    )
    submit_parser.add_argument(
        "-e",
        "--sge-extra-args",
        default=defaults.get("sge-extra-args-default", ""),
        type=str,
        help="Passes extra arguments to qsub. See the documentation of the package for usage and ways of overriding default behavior.",
    )
    submit_parser.add_argument(
        "-m",
        "--memory",
        help="Sets both the h_vmem and the mem_free parameters when submitting "
        "the job to a non-GPU queue, e.g., 8G to set the memory "
        "requirements to 8 gigabytes. Sets gpumem parameter when "
        "submitting the job to a GPU-based queue.",
    )
    submit_parser.add_argument(
        "-p",
        "--parallel",
        "--pe_mth",
        type=int,
        help="Sets the number of slots per job (-pe pe_mth) and multiplies the mem_free parameter. E.g. to get 16 G of memory, use -m 8G -p 2.",
    )
    submit_parser.add_argument(
        "-n", "--name", dest="name", help="Gives the job a name"
    )
    submit_parser.add_argument(
        "-x",
        "--dependencies",
        type=int,
        default=[],
        metavar="ID",
        nargs="*",
        help="Set job dependencies to the list of job identifiers separated by spaces",
    )
    submit_parser.add_argument(
        "-k",
        "--stop-on-failure",
        action="store_true",
        help="Stop depending jobs when this job finished with an error.",
    )
    submit_parser.add_argument(
        "-d",
        "--exec-dir",
        metavar="DIR",
        help="Sets the executing directory, where the script should be executed. If not given, jobs will be executed in the current directory",
    )
    submit_parser.add_argument(
        "-l",
        "--log-dir",
        default="logs",
        metavar="DIR",
        help="Sets the log directory.",
    )
    submit_parser.add_argument(
        "-s",
        "--environment",
        metavar="KEY=VALUE",
        dest="env",
        nargs="*",
        default=[],
        help="Passes specific environment variables to the job.",
    )
    submit_parser.add_argument(
        "-t",
        "--array",
        "--parametric",
        metavar="(first-)last(:step)",
        help="Creates a parametric (array) job. You must specify the 'last' value, but 'first' (default=1) and 'step' (default=1) can be specified as well (when specifying 'step', 'first' has to be given, too).",
    )
    submit_parser.add_argument(
        "-z",
        "--dry-run",
        action="store_true",
        help="Do not really submit anything, just print out what would submit in this case",
    )
    submit_parser.add_argument(
        "-i",
        "--io-big",
        action="store_true",
        help='Sets "io_big" on the submitted jobs so it limits the machines in which the job is submitted to those that can do high-throughput.',
    )
    submit_parser.add_argument(
        "-r",
        "--repeat",
        type=int,
        metavar="N",
        default=1,
        help="Submits the job N times. Each job will depend on the job before.",
    )
    submit_parser.add_argument(
        "-o",
        "--print-id",
        action="store_true",
        help="Prints the new job id (so that they can be parsed by automatic scripts).",
    )
    submit_parser.add_argument(
        "job",
        metavar="command",
        nargs=argparse.REMAINDER,
        help="The job that should be executed. Sometimes a -- is required to separate the job from other command line options.",
    )
    submit_parser.set_defaults(func=submit)

    # subcommand 're-submit'
    resubmit_parser = cmdparser.add_parser(
        "resubmit",
        aliases=["reset", "requeue", "re"],
        formatter_class=formatter,
        help="Re-submits a list of jobs.",
    )
    resubmit_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Re-submit only the jobs with the given ids (by default, all finished jobs are re-submitted).",
    )
    resubmit_parser.add_argument(
        "-q",
        "--queue",
        metavar="QNAME",
        dest="qname",
        choices=QUEUES,
        help="Reset the SGE queue to submit the job to",
    )
    resubmit_parser.add_argument(
        "-m",
        "--memory",
        help="Resets both the h_vmem and the mem_free parameters when "
        "submitting the job to a non-GPU queue, e.g., 8G "
        "to set the memory requirements to 8 gigabytes. Resets gpumem "
        "parameter when submitting the job to a GPU-based queue.",
    )
    resubmit_parser.add_argument(
        "-p",
        "--parallel",
        "--pe_mth",
        type=int,
        help="Resets the number of slots per job (-pe pe_mth) and multiplies the mem_free parameter. E.g. to get 16 G of memory, use -m 8G -p 2.",
    )
    resubmit_parser.add_argument(
        "-i",
        "--io-big",
        action="store_true",
        help='Resubmits the job to the "io_big" queue.',
    )
    resubmit_parser.add_argument(
        "-I",
        "--no-io-big",
        action="store_true",
        help='Resubmits the job NOT to the "io_big" queue.',
    )
    resubmit_parser.add_argument(
        "-k",
        "--keep-logs",
        action="store_true",
        help="Do not clean the log files of the old job before re-submitting.",
    )
    resubmit_parser.add_argument(
        "-s",
        "--also-success",
        action="store_true",
        help="Re-submit also jobs that have finished successfully.",
    )
    resubmit_parser.add_argument(
        "-a",
        "--running-jobs",
        action="store_true",
        help="Re-submit even jobs that are running or waiting (use this flag with care).",
    )
    resubmit_parser.add_argument(
        "-o",
        "--overwrite-command",
        nargs=argparse.REMAINDER,
        help="Overwrite the command line (of a single job) that should be executed (useful to keep job dependencies).",
    )
    resubmit_parser.set_defaults(func=resubmit)

    # subcommand 'stop'
    stop_parser = cmdparser.add_parser(
        "stop",
        formatter_class=formatter,
        help="Stops the execution of jobs in the grid.",
    )
    stop_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Stop only the jobs with the given ids (by default, all jobs are stopped).",
    )
    stop_parser.set_defaults(func=stop)

    # subcommand 'list'
    list_parser = cmdparser.add_parser(
        "list",
        aliases=["ls"],
        formatter_class=formatter,
        help="Lists jobs stored in the database. Use the -vv option to get a long listing.",
    )
    list_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="List only the jobs with the given ids (by default, all jobs are listed)",
    )
    list_parser.add_argument(
        "-n",
        "--names",
        metavar="NAME",
        nargs="+",
        help="List only the jobs with the given names (by default, all jobs are listed)",
    )
    list_parser.add_argument(
        "-a",
        "--print-array-jobs",
        action="store_true",
        help="Also list the array ids.",
    )
    list_parser.add_argument(
        "-l",
        "--long",
        action="store_true",
        help="Prints additional information about the submitted job.",
    )
    list_parser.add_argument(
        "-t",
        "--print-times",
        action="store_true",
        help="Prints timing information on when jobs were submited, executed and finished",
    )
    list_parser.add_argument(
        "-x",
        "--print-dependencies",
        action="store_true",
        help="Print the dependencies of the jobs as well.",
    )
    list_parser.add_argument(
        "-o",
        "--ids-only",
        action="store_true",
        help="Prints ONLY the job ids (so that they can be parsed by automatic scripts).",
    )
    list_parser.add_argument(
        "-s",
        "--status",
        nargs="+",
        choices=Status,
        default=Status,
        help="Delete only jobs that have the given statuses; by default all jobs are deleted.",
    )
    list_parser.set_defaults(func=list)

    # subcommand 'communicate'
    stop_parser = cmdparser.add_parser(
        "communicate",
        aliases=["com"],
        formatter_class=formatter,
        help="Communicates with the grid to see if there were unexpected errors (e.g. a timeout) during the job execution.",
    )
    stop_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Check only the jobs with the given ids (by default, all jobs are checked)",
    )
    stop_parser.set_defaults(func=communicate)

    # subcommand 'report'
    report_parser = cmdparser.add_parser(
        "report",
        aliases=["rep", "r", "explain", "why"],
        formatter_class=formatter,
        help="Iterates through the result and error log files and prints out the logs.",
    )
    report_parser.add_argument(
        "-e",
        "--errors-only",
        action="store_true",
        help="Only report the error logs (by default, both logs are reported).",
    )
    report_parser.add_argument(
        "-o",
        "--output-only",
        action="store_true",
        help="Only report the output logs  (by default, both logs are reported).",
    )
    report_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Report only the jobs with the given ids (by default, all finished jobs are reported)",
    )
    report_parser.add_argument(
        "-a",
        "--array-ids",
        metavar="ID",
        nargs="+",
        help="Report only the jobs with the given array ids. If specified, a single job-id must be given as well.",
    )
    report_parser.add_argument(
        "-n",
        "--name",
        help="Report only the jobs with the given name; by default all jobs are reported.",
    )
    report_parser.add_argument(
        "-s",
        "--status",
        nargs="+",
        choices=Status,
        default=Status,
        help="Report only jobs that have the given statuses; by default all jobs are reported.",
    )
    report_parser.set_defaults(func=report)

    # subcommand 'delete'
    delete_parser = cmdparser.add_parser(
        "delete",
        aliases=["del", "rm", "remove"],
        formatter_class=formatter,
        help="Removes jobs from the database; if jobs are running or are still scheduled in SGE, the jobs are also removed from the SGE queue.",
    )
    delete_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Delete only the jobs with the given ids (by default, all jobs are deleted).",
    )
    delete_parser.add_argument(
        "-a",
        "--array-ids",
        metavar="ID",
        nargs="+",
        help="Delete only the jobs with the given array ids. If specified, a single job-id must be given as well. Note that the whole job including all array jobs will be removed from the SGE queue.",
    )
    delete_parser.add_argument(
        "-r",
        "--keep-logs",
        action="store_true",
        help="If set, the log files will NOT be removed.",
    )
    delete_parser.add_argument(
        "-R",
        "--keep-log-dir",
        action="store_true",
        help="When removing the logs, keep the log directory.",
    )
    delete_parser.add_argument(
        "-s",
        "--status",
        nargs="+",
        choices=Status,
        default=Status,
        help="Delete only jobs that have the given statuses; by default all jobs are deleted.",
    )
    delete_parser.set_defaults(func=delete)

    # subcommand 'run_scheduler'
    scheduler_parser = cmdparser.add_parser(
        "run-scheduler",
        aliases=["sched", "x"],
        formatter_class=formatter,
        help="Runs the scheduler on the local machine. To stop the scheduler safely, please use Ctrl-C; only valid in combination with the '--local' option.",
    )
    scheduler_parser.add_argument(
        "-p",
        "--parallel",
        type=int,
        default=1,
        help="Select the number of parallel jobs that you want to execute locally",
    )
    scheduler_parser.add_argument(
        "-j",
        "--job-ids",
        metavar="ID",
        nargs="+",
        help="Select the job ids that should be run (be default, all submitted and queued jobs are run).",
    )
    scheduler_parser.add_argument(
        "-s",
        "--sleep-time",
        type=float,
        default=0.1,
        help="Set the sleep time between for the scheduler in seconds.",
    )
    scheduler_parser.add_argument(
        "-x",
        "--die-when-finished",
        action="store_true",
        help="Let the job manager die when it has finished all jobs of the database.",
    )
    scheduler_parser.add_argument(
        "-l",
        "--no-log-files",
        action="store_true",
        help="Overwrites the log file setup to print the results to the console.",
    )
    scheduler_parser.add_argument(
        "-n",
        "--nice",
        type=int,
        help="Jobs will be run with the given priority (can only be positive, i.e., to have lower priority",
    )
    scheduler_parser.set_defaults(func=run_scheduler)

    # subcommand 'run-job'; this should not be seen on the command line since it is actually a wrapper script
    run_parser = cmdparser.add_parser("run-job", help=argparse.SUPPRESS)
    run_parser.set_defaults(func=run_job)

    if command_line_options:
        args = parser.parse_args(command_line_options[1:])
        args.wrapper_script = command_line_options[0]
    else:
        args = parser.parse_args()
        args.wrapper_script = sys.argv[0]

    if not hasattr(args, "func"):
        return parser.print_help(sys.stderr)

    args.func(args)

    return 0
