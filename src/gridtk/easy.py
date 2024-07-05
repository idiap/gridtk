# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Common arguments to grid jobs."""

import os
import sys

from . import manager, tools


def add_arguments(parser):
    """Adds stock arguments to argparse parsers from scripts that submit grid
    jobs."""

    default_log_path = os.path.realpath("logs")

    parser.add_argument(
        "--log-dir",
        metavar="LOG",
        type=str,
        dest="logdir",
        default=default_log_path,
        help='Base directory used for logging (defaults to "%(default)s")',
    )

    q_choices = (
        "default",
        "all.q",
        "q_1day",
        "q1d",
        "q_1week",
        "q1w",
        "q_1month",
        "q1m",
        "q_1day_mth",
        "q1dm",
        "q_1week_mth",
        "q1wm",
        "q_gpu",
        "gpu",
        "q_long_gpu",
        "lgpu",
        "q_short_gpu",
        "sgpu",
        "vsgpu",
    )

    parser.add_argument(
        "--queue-name",
        metavar="QUEUE",
        type=str,
        dest="queue",
        default=q_choices[0],
        choices=q_choices,
        help="Queue for submission - one of "
        + "|".join(q_choices)
        + ' (defaults to "%(default)s")',
    )

    parser.add_argument(
        "--hostname",
        metavar="HOSTNAME",
        type=str,
        dest="hostname",
        default=None,
        help="If set, it asks the queue to use only a subset of the available nodes",
    )
    parser.add_argument(
        "--memfree",
        metavar="MEMFREE",
        type=str,
        dest="memfree",
        default=None,
        help="Adds the '-l mem_free' argument to qsub",
    )
    parser.add_argument(
        "--hvmem",
        metavar="HVMEM",
        type=str,
        dest="hvmem",
        default=None,
        help="Adds the '-l h_vmem' argument to qsub",
    )
    parser.add_argument(
        "--pe-opt",
        metavar="PE_OPT",
        type=str,
        dest="pe_opt",
        default=None,
        help="Adds the '--pe ' argument to qsub",
    )

    parser.add_argument(
        "--no-cwd",
        default=True,
        action="store_false",
        dest="cwd",
        help="Do not change to the current directory when starting the grid job",
    )

    parser.add_argument(
        "--dry-run",
        default=False,
        action="store_true",
        dest="dryrun",
        help="Does not really submit anything, just print what would do instead",
    )

    parser.add_argument(
        "--job-database",
        default=None,
        dest="statefile",
        help="The path to the state file that will be created with the submissions (defaults to the parent directory of your logs directory)",
    )

    return parser


def create_manager(arguments):
    """A simple wrapper to JobManager() that places the statefile on the
    correct path by default."""

    if arguments.statefile is None:
        arguments.statefile = os.path.join(
            os.path.dirname(arguments.logdir), "submitted.db"
        )

    arguments.statefile = os.path.realpath(arguments.statefile)

    return manager.JobManager(statefile=arguments.statefile)


class DryRunJob:
    """A simple wrapper for dry-run jobs that behaves like a normal job."""

    # distributed as jobs are "submitted"
    current_id = 0

    def __init__(
        self,
        cmd,
        cwd,
        queue,
        hostname,
        memfree,
        hvmem,
        gpumem,
        pe_opt,
        stdout,
        stderr,
        name,
        array,
        deps,
    ):
        self.myid = DryRunJob.current_id
        DryRunJob.current_id += 1

        self.cmd = cmd
        self.cwd = cwd
        self.queue = queue
        self.hostname = hostname
        self.memfree = memfree
        self.hvmem = hvmem
        self.gpumem = gpumem
        self.pe_opt = pe_opt
        self.stdout = stdout
        self.stderr = stderr
        self.name = name
        self.array = array
        self.deps = deps

    def __str__(self):
        return """
  id       : %d
  command  : %s
  cwd      : %s
  queue    : %s
  hostname : %s
  memfree  : %s
  hvmem    : %s
  gpumem   : %s
  pe_opt   : %s
  stdout   : %s
  stderr   : %s
  name     : %s
  array    : %s
  depends  : %s""" % (
            self.myid,
            self.cmd,
            self.cwd,
            self.queue,
            self.hostname,
            self.memfree,
            self.hvmem,
            self.gpumem,
            self.pe_opt,
            self.stdout,
            self.stderr,
            self.name,
            self.array,
            self.deps,
        )

    def id(self):
        return self.myid


def submit(jman, command, arguments, deps=[], array=None):
    """An easy submission option for grid-enabled scripts.

    Create the log directories using random hash codes. Use the
    arguments as parsed by the main script.
    """
    logdir = os.path.join(
        os.path.realpath(arguments.logdir), tools.random_logdir()
    )

    jobname = os.path.splitext(os.path.basename(command[0]))[0]
    cmd = tools.make_shell(sys.executable, command)

    if arguments.dryrun:
        return DryRunJob(
            cmd,
            cwd=arguments.cwd,
            queue=arguments.queue,
            hostname=arguments.hostname,
            memfree=arguments.memfree,
            hvmem=arguments.hvmem,
            gpumem=arguments.gpumem,
            pe_opt=arguments.pe_opt,
            stdout=logdir,
            stderr=logdir,
            name=jobname,
            deps=deps,
            array=array,
        )

    # really submit
    return jman.submit(
        cmd,
        cwd=arguments.cwd,
        queue=arguments.queue,
        hostname=arguments.hostname,
        memfree=arguments.memfree,
        hvmem=arguments.hvmem,
        gpumem=arguments.gpumem,
        pe_opt=arguments.pe_opt,
        stdout=logdir,
        stderr=logdir,
        name=jobname,
        deps=deps,
        array=array,
    )
