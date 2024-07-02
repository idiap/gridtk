# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pydoc
import tempfile

from collections import defaultdict
from pathlib import Path

import click

from clapper.click import AliasedGroup


class CustomGroup(AliasedGroup):
    def list_commands(self, ctx: click.Context) -> list[str]:
        # do not sort the commands
        return self.commands

    def get_command(self, ctx, cmd_name):
        cmd_name = {
            "sbatch": "submit",
            "scancel": "stop",
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
    from .manager import JobManager

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
    from .manager import JobManager

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
    from .models import JOB_STATES_MAPPING

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
    from .manager import JobManager

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
    from .manager import JobManager

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
    from tabulate import tabulate

    from .manager import JobManager

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
    from .manager import JobManager

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
    from .manager import JobManager

    job_manager: JobManager = ctx.meta["job_manager"]
    with job_manager as session:
        jobs = job_manager.delete_jobs(job_ids=job_ids, states=states, names=names)
        for job in jobs:
            click.echo(f"Deleted job {job.id} with grid ID {job.grid_id}")
        session.commit()


if __name__ == "__main__":
    cli()
