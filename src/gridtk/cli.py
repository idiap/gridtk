# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
import pydoc
import shutil
import sys
import tempfile

from pathlib import Path

import click

from . import guard
from .listing import column_keys
from .tools import UnknownJobIdsError, add_default_dep_type

COLUMN_KEYS = column_keys()


class CustomGroup(click.Group):
    """Custom command group that does not sort commands."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        # do not sort the commands
        return list(self.commands)

    def get_command(self, ctx, cmd_name):
        """get_command with prefix aliasing and name aliases."""
        cmd_name = {
            "sbatch": "submit",
            "ls": "list",
            "rm": "delete",
            "remove": "delete",
        }.get(cmd_name, cmd_name)
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx) if x.startswith(cmd_name)]
        if not matches:
            return None

        if len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])

        raise click.UsageError(f"Too many matches: {', '.join(sorted(matches))}", ctx)


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
        if "-" in job_ids:
            start, end_str = job_ids.split("-")
            return list(range(int(start), int(end_str) + 1))
        if "+" in job_ids:
            start, length = job_ids.split("+")
            end = int(start) + int(length)
            return list(range(int(start), end + 1))
        return [int(job_ids)]
    except ValueError as e:
        raise click.BadParameter(f"Invalid job id {job_ids}") from e


def parse_states(states: str) -> list[str]:
    """Normalize a list of comma-separated states to their long name format."""
    from .models import JOB_STATES_MAPPING

    if not states:
        return []
    states = states.upper()
    if states == "ALL":
        return list(JOB_STATES_MAPPING.values())
    final_states = []
    for state in states.split(","):
        state = JOB_STATES_MAPPING.get(state, state)
        if state not in JOB_STATES_MAPPING.values():
            raise click.BadParameter(
                f"Invalid state: {state}\nValid values are: ALL {' '.join(list(JOB_STATES_MAPPING.keys()) + list(JOB_STATES_MAPPING.values()))} or a comma (,) separated list of them."
            )
        final_states.append(state)
    return final_states


def unknown_job_ids_message(error: UnknownJobIdsError, database: Path) -> str:
    """Explain that dependencies refer to jobs gridtk does not know."""
    ids = ", ".join(map(str, error.job_ids))
    if error.dependent is not None:
        return (
            f"job {error.dependent} depends on job(s) {ids}, which are no longer "
            f"in {database}"
        )
    return (
        f"job(s) {ids} not found in {database} (--dependency takes local ids; "
        f"write slurm ids as slurm:<id>, e.g. afterok:slurm:{error.job_ids[0]})"
    )


def job_ids_callback(ctx, param, value):
    """Implement a callback for the job ids option."""
    return parse_job_ids(value)


def states_callback(ctx, param, value):
    """Implement a callback for the states option."""
    return parse_states(value)


def no_jobs_message(
    action: str,
    *,
    default_states: bool = False,
) -> str:
    """Build a helpful message when no jobs match the given filters."""
    msg = f"No jobs were {action}."
    if default_states:
        msg += (
            " Note: the default state filter is active."
            " Use --state all to include all jobs."
        )
    return msg


def job_filters(f_py=None, default_states=None):
    """Filter jobs based on the provided function and default states."""
    assert callable(f_py) or f_py is None
    from .models import JOB_STATES_MAPPING

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
            help=(
                "Selects only these job ids, separated by comma. A range can also be "
                "specified in the form 'start-end' ('-j 3-5' is equivalent to "
                "'-j 3,4,5') or in the form 'start+length' ('-j 4+3' is equivalent to "
                "'-j 4,5,6,7')."
            ),
            callback=job_ids_callback,
        )(function)
        function = click.option(
            "--dependents/--no-dependents",
            default=False,
            help="Select dependents jobs (jobs that depend on selected jobs) as well.",
        )(function)
        return function  # noqa: RET504

    return _job_filters_decorator(f_py) if callable(f_py) else _job_filters_decorator


@click.group(
    cls=CustomGroup,
    context_settings={
        "show_default": True,
        "help_option_names": ["--help", "-h"],
        "auto_envvar_prefix": "GRIDTK",
    },
)
@click.option(
    "-d",
    "--database",
    help="Path to the database file.",
    default=Path("jobs.sql3"),
    type=click.Path(path_type=Path, file_okay=True, dir_okay=False),
)
@click.option(
    "-l",
    "--logs-dir",
    help="Path to the logs directory.",
    default=Path("logs"),
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
)
@click.pass_context
def cli(ctx, database, logs_dir):
    """GridTK command line interface."""
    from .manager import JobManager

    job_manager = JobManager(database=database, logs_dir=logs_dir)
    try:
        job_manager.check_schema()
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    ctx.meta["job_manager"] = job_manager
    # also when the command fails (e.g. submit with an unknown dependency), so
    # it leaves no empty database behind
    ctx.call_on_close(job_manager.cleanup_empty_database)


@cli.command(
    epilog="""\b
Example:
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
    help=(
        "Depend on other jobs that are already in the list of gridtk, as in sbatch "
        "but with local job ids; ids given without a type (e.g. 5 or 5:6) mean "
        "afterany. Prefix slurm ids of jobs submitted outside gridtk with slurm: "
        "(e.g. afterok:5:slurm:3793602)."
    ),
)
@click.option(
    "--repeat",
    default=1,
    type=click.INT,
    help=(
        "Submits the job N times. Each job depends on the ones before, with the "
        "dependency type of --dependency (default: afterany, as for job ids given "
        "without a type)."
    ),
)
@click.option(
    "--git-guard",
    "git_guard",
    is_flag=False,
    flag_value=".",
    default=None,
    metavar="[DIR]",
    type=click.Path(path_type=Path),
    help=(
        "Pin the job to the git repository containing DIR (default: the current "
        "directory): its HEAD, tracked changes and untracked files are recorded at "
        "submission and the job aborts with exit code 75 if any of them changed "
        "when it starts (useful for code installed in editable mode). Requires the "
        "--- form."
    ),
)
@click.option(
    "--no-git-guard",
    is_flag=True,
    default=False,
    help="Do not pin the job to a git repository (overrides --git-guard).",
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
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output in JSON format",
)
@click.argument("script", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def submit(
    ctx: click.Context,
    job_name: str,
    array: str,
    dependencies: str | None,
    repeat: int,
    git_guard: Path | None,
    no_git_guard: bool,
    output_json: bool,
    script: str,
    **kwargs,
):
    """Submit a job to the queue."""
    from .manager import JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    git_repo = None
    if git_guard is not None and not no_git_guard:
        if "---" not in script:
            raise click.UsageError(
                "--git-guard requires the command form of submission "
                "(gridtk submit [options] --- command)"
            )
        try:
            git_repo = guard.repository_root(git_guard)
        except RuntimeError as e:
            raise click.UsageError(f"--git-guard: {e}") from e
    # reconstruct the command with kwargs and script
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

    dependencies = add_default_dep_type(dependencies)
    with job_manager as session:
        if repeat > 1:
            if dependencies is not None and (
                "," in dependencies or "?" in dependencies
            ):
                raise click.UsageError(
                    f"Repeated jobs can only have one dependency type (no `,` or `?` in --dependency) but got {dependencies}"
                )
        for _ in range(repeat):
            try:
                job = job_manager.submit_job(
                    name=job_name,
                    command=command,
                    array=array,
                    dependencies=dependencies,
                    git_guard=git_repo,
                )
            except UnknownJobIdsError as e:
                raise click.UsageError(
                    unknown_job_ids_message(e, job_manager.database)
                ) from e
            if output_json:
                click.echo(
                    json.dumps(
                        {
                            "job_id": job.id,
                            "slurm_id": job.grid_id,
                            "name": job.name,
                        }
                    )
                )
            else:
                click.echo(job.id)
            deps: list[str] = str(dependencies or "").split(",")
            deps[-1] = f"{deps[-1]}:{job.id}" if deps[-1] else f"afterany:{job.id}"
            dependencies = ",".join(deps)
        session.commit()


@cli.command()
@job_filters(default_states="BF,CA,F,NF,OOM,TO")
@click.pass_context
def resubmit(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    dependents: bool,
):
    """Resubmit a job to the queue."""
    from .manager import JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        try:
            jobs = job_manager.resubmit_jobs(
                job_ids=job_ids, states=states, names=names, dependents=dependents
            )
        except UnknownJobIdsError as e:
            raise click.ClickException(
                unknown_job_ids_message(e, job_manager.database)
            ) from e
        if not jobs:
            click.echo(
                no_jobs_message(
                    "resubmitted",
                    default_states=True,
                )
            )
        for job in jobs:
            click.echo(f"Resubmitted job {job.id}")
        session.commit()


@cli.command(
    name="list",
    epilog="""\b
Examples:
gridtk list                      # compact overview
gridtk list -vv                  # all the details
gridtk list -o +output,-nodes    # add/remove columns
gridtk list -o id,state,name     # exactly these columns
gridtk list -s F -q              # ids of failed jobs, one per line
gridtk list --json -o id,state,exit_code
""",
)
@job_filters
@click.option(
    "-v",
    "--verbose",
    "verbosity",
    count=True,
    help="Show more columns (repeat for even more).",
)
@click.option(
    "-o",
    "--columns",
    "columns_spec",
    metavar="COLS",
    help=(
        "Comma-separated columns to show, in order.  Prefix them with + or - to "
        "add them to or remove them from the default ones (e.g. '+output,-nodes'). "
        "With --json, selects the keys of each job.  Columns: "
        + ", ".join(COLUMN_KEYS)
        + "."
    ),
)
@click.option(
    "-t/-T",
    "--truncate/--no-truncate",
    default=None,
    help=(
        "Truncate long values so the table fits the terminal.  By default, "
        "values are truncated only when the output is a terminal."
    ),
    show_default=False,
)
@click.option("-w", "--wrap", is_flag=True, default=False, hidden=True)
@click.option(
    "--summary/--no-summary",
    default=None,
    help=(
        "Show a summary line with the number of jobs in each state (by default, "
        "only when the output is a terminal)."
    ),
    show_default=False,
)
@click.option("--no-header", is_flag=True, default=False, help="Omit the header line.")
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Only print the job ids, one per line.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output in JSON format, with all details of each job (see --columns).",
)
@click.pass_context
def list_jobs(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    dependents: bool,
    verbosity: int,
    columns_spec: str | None,
    truncate: bool | None,
    wrap: bool,
    summary: bool | None,
    no_header: bool,
    quiet: bool,
    output_json: bool,
):
    """List jobs in the queue, similar to sacct and squeue."""
    from . import listing
    from .manager import JobManager

    if output_json and (truncate or wrap or no_header or quiet):
        raise click.UsageError(
            "--json is mutually exclusive with --truncate, --no-header and --quiet"
        )
    if wrap:
        click.echo(
            "Warning: --wrap is deprecated and will be removed in a future "
            "version; use --no-truncate to show full values.",
            err=True,
        )
        truncate = False

    try:
        if output_json:
            # JSON carries all details, unless columns are selected
            columns, _ = listing.select_columns(len(listing.COLUMNS), columns_spec)
        else:
            columns, requested = listing.select_columns(verbosity, columns_spec)
    except ValueError as e:
        raise click.BadParameter(str(e), param_hint="'-o' / '--columns'") from e

    tty = sys.stdout.isatty()
    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.list_jobs(
            job_ids=job_ids, states=states, names=names, dependents=dependents
        )

        if output_json:
            click.echo(
                json.dumps(
                    [listing.job_to_dict(job, columns) for job in jobs],
                    indent=2 if tty else None,
                )
            )
        elif quiet:
            for job in jobs:
                click.echo(job.id)
        elif not jobs:
            click.echo(no_jobs_message("found"))
        else:
            utf8 = (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"
            click.echo(
                listing.render_table(
                    jobs,
                    columns,
                    requested=requested,
                    width=(
                        shutil.get_terminal_size().columns
                        if (tty if truncate is None else truncate)
                        else None
                    ),
                    color=tty and "NO_COLOR" not in os.environ,
                    header=not no_header,
                    ellipsis="…" if utf8 else "..",
                )
            )
            if tty if summary is None else summary:
                click.echo(listing.summary_line(jobs))
        session.commit()


@cli.command()
@job_filters
@click.pass_context
def stop(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    dependents: bool,
):
    """Stop a job from running."""
    from .manager import JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.stop_jobs(
            job_ids=job_ids, states=states, names=names, dependents=dependents
        )
        if not jobs:
            click.echo(no_jobs_message("stopped"))
        for job in jobs:
            click.echo(f"Stopped job {job.id} with slurm id {job.grid_id}")
        session.commit()


@cli.command()
@job_filters
@click.pass_context
def delete(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    dependents: bool,
):
    """Delete a job from the queue."""
    from .manager import JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.delete_jobs(
            job_ids=job_ids, states=states, names=names, dependents=dependents
        )
        if not jobs:
            click.echo(no_jobs_message("deleted"))
        for job in jobs:
            click.echo(f"Deleted job {job.id} with slurm id {job.grid_id}")
        session.commit()


@cli.command()
@job_filters
@click.option(
    "--interval",
    default=10,
    type=click.INT,
    help="Polling interval in seconds.",
)
@click.pass_context
def wait(ctx, job_ids, states, names, dependents, interval):
    """Wait for jobs to finish. Exits with code 1 if any job failed."""
    import time

    from .manager import FINISHED_STATES, JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    # Failed states - if any job ends in these, exit code 1
    failed_states = FINISHED_STATES - {"COMPLETED"}

    while True:
        with job_manager as session:
            jobs = job_manager.list_jobs(
                job_ids=job_ids, states=states, names=names, dependents=dependents
            )
            if not jobs:
                click.echo("No jobs found.")
                return

            all_terminal = all(job.state in FINISHED_STATES for job in jobs)
            if all_terminal:
                any_failed = any(job.state in failed_states for job in jobs)
                for job in jobs:
                    click.echo(f"Job {job.id}: {job.state} ({job.exit_code})")
                session.commit()
                if any_failed:
                    raise SystemExit(1)
                return

            # Show progress with state breakdown
            from .listing import state_breakdown

            active = [j for j in jobs if j.state not in FINISHED_STATES]
            click.echo(
                f"Waiting for {len(active)} job(s): {state_breakdown(active)}"
                f" (checking every {interval}s)"
            )
            session.commit()

        time.sleep(interval)


@cli.command()
@job_filters
@click.option(
    "-a",
    "--array",
    "array_idx",
    help="Array index to see the logs for only one item of an array job.",
)
@click.option(
    "-n",
    "--tail",
    type=click.IntRange(min=0),
    metavar="N",
    help="Only show the last N lines of each log.",
)
@click.option(
    "--raw",
    is_flag=True,
    default=False,
    help=(
        "Show logs as they are.  By default, lines redrawn with carriage returns "
        "(e.g. progress bars) only show their last update."
    ),
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output in JSON format",
)
@click.pass_context
def report(
    ctx: click.Context,
    job_ids: list[int],
    states: list[str],
    names: list[str],
    dependents: bool,
    array_idx: str | None,
    tail: int | None,
    raw: bool,
    output_json: bool,
):
    """Report on jobs in the queue."""
    from .manager import JobManager
    from .tools import read_log

    def log_entry(path: Path) -> dict:
        """Read a log, as reported in JSON."""
        if not path.exists():
            return {"path": str(path), "content": None, "total_lines": None}
        content, total_lines = read_log(path, tail=tail, collapse_cr=not raw)
        return {
            "path": str(path),
            "content": content,
            "total_lines": total_lines,
            "truncated": tail is not None and total_lines > tail,
        }

    def log_files(job) -> list[tuple[str, Path]]:
        """Return the output and (if different) error files of a job, with their kind."""
        output_files, error_files = job.output_files, job.error_files
        if array_idx is not None:
            real_array_idx = (job.array_task_ids or []).index(int(array_idx))
            output_files = output_files[real_array_idx : real_array_idx + 1]
            error_files = error_files[real_array_idx : real_array_idx + 1]
        files = []
        for output, error in zip(output_files, error_files):
            files.append(("Output", output))
            if error != output:
                files.append(("Error", error))
        return files

    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.list_jobs(
            job_ids=job_ids, states=states, names=names, dependents=dependents
        )
        if not jobs:
            if output_json:
                click.echo(json.dumps([]))
            else:
                click.echo(no_jobs_message("found"))
            session.commit()
            return

        if output_json:
            report_list = []
            for job in jobs:
                with tempfile.NamedTemporaryFile(mode="w+t", suffix=".sh") as tmpfile:
                    command = job.submitted_command(tmpfile, session=session)
                report_list.append(
                    {
                        "job_id": job.id,
                        "name": job.name,
                        "state": job.state,
                        "exit_code": job.exit_code,
                        "nodes": job.nodes,
                        "command": command,
                        "git_guard": (
                            job.git_guard.to_dict() if job.git_guard else None
                        ),
                        "output_files": [log_entry(f) for _, f in log_files(job)],
                    }
                )
            click.echo(json.dumps(report_list, indent=2))
            session.commit()
            return

        for job in jobs:
            report_text = ""
            report_text += f"Job ID: {job.id}\n"
            report_text += f"Name: {job.name}\n"
            report_text += f"State: {job.state} ({job.exit_code})\n"
            report_text += f"Nodes: {job.nodes}\n"
            if job.git_guard:
                report_text += f"Git guard: {job.git_guard.describe()}\n"
            with tempfile.NamedTemporaryFile(mode="w+t", suffix=".sh") as tmpfile:
                report_text += f"Submitted command: {job.submitted_command(tmpfile, session=session)}\n"
                if job.command_in_bash:
                    report_text += (
                        f"Content of the temporary script:\n{job.command_in_bash}\n"
                    )
            for kind, path in log_files(job):
                report_text += f"{kind} file: {path}\n"
                entry = log_entry(path)
                if entry["content"] is None:
                    continue
                if entry["truncated"]:
                    report_text += f"[last {tail} of {entry['total_lines']} lines]\n"
                report_text += entry["content"] + "\n"
            pydoc.pager(report_text)
        session.commit()


if __name__ == "__main__":
    cli()
