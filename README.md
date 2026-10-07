<!--
SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![docs](https://img.shields.io/badge/docs-stable-orange.svg)](https://gridtk.readthedocs.io/en/stable/)
[![tests](https://github.com/idiap/gridtk/actions/workflows/tests.yml/badge.svg)](https://github.com/idiap/gridtk/actions/workflows/tests.yml)
[![coverage](https://raw.githubusercontent.com/idiap/gridtk/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)
[![repository](https://img.shields.io/badge/github-project-0000c0.svg)](https://github.com/idiap/gridtk)

# GridTK: Slurm Job Management for Humans

## Introduction

GridTK is a powerful command-line tool designed to simplify the management of
Slurm jobs. At its core, GridTK provides a drop-in replacement for `sbatch`,
`gridtk submit`, which allows you to get started quickly. This
tutorial will guide you through the process of using the `gridtk` script to
efficiently manage your Slurm workloads. We will cover the basics of
installation, submission, monitoring, and various commands provided by GridTK.

## Prerequisites

Before diving into GridTK, ensure you have the following prerequisites:

1. A working Slurm setup.
2. [uv](https://docs.astral.sh/uv/) installed (recommended) or [pipx](https://pipx.pypa.io/stable/).
3. GridTK installed (instructions provided below).

## Installation

The recommended way to install GridTK is using `uv`:

```bash
$ uv tool install gridtk
```

Or run it directly without installing:

```bash
$ uvx gridtk --help
```

Alternatively, you can use `pipx`:

```bash
$ pipx install gridtk
```

It is **not recommended** to install GridTK using `pip install gridtk` in the
same environment as your experiments. GridTK does not need to be installed in
the same environment as your experiments and its dependencies may conflict with
your experiments' dependencies.

## Basic Usage

In this section, we will cover the basic commands and usage of the GridTK
script. The primary goal is to help you get familiar with submitting,
monitoring, and managing your Slurm jobs using GridTK.

### Submitting a Job

To submit a job script, use `gridtk submit`. For example, given the script (`job.sh`) below:

```bash
#!/bin/bash

echo "Hello, GridTK!"
```

Submit the job using `gridtk submit`:

```bash
$ gridtk submit job.sh
1
```
where `1` is the local job id (not the slurm job id) for your job. The job
numbers always start with 1 which is easier to remember than the slurm job id.

`gridtk submit` is a drop-in replacement for `sbatch` and accepts the same options while adding its own.
Run `gridtk submit --help` to see the list of `gridtk submit` specific options and run `sbatch --help` to see the full list of options for `sbatch`.

Note that your slurm cluster may require you to specify a partition, an account,
or another option. You can do so by adding them to `gridtk submit --account=myaccount --partition=mypartition job.sh`
or setting default values using environment variables such as
`SBATCH_ACCOUNT` and `SBATCH_PARTITION`.

### Monitoring Jobs

Use the `gridtk list` command to view the status of your jobs:
```bash
$ gridtk list
ID   SLURM  STATE    NAME    NODES
--  ------  -------  ------  ----------
 1  136132  PENDING  gridtk  (Priority)
1 job: 1 pending
```
`gridtk list` will only show jobs that are submitted using `gridtk submit` **in the current folder**.
You can see the submitted job got a local job id of `1` and a slurm job id of
`136132`.
It is in the `PENDING` state, waiting for its turn (`Priority`), and its name
is `gridtk` by default (it is recommended to give a meaningful name using the
`gridtk submit --job-name` option).
The output files are written to the `logs/` directory by default (you may change
the directory with the `gridtk --logs-dir` option); `gridtk list -v` shows them
(see [Adjusting `gridtk list` Output](#adjusting-gridtk-list-output)).
GridTK manages the log files for you, so you don't have to worry about knowing
where they are stored or cleaning them up.

For detailed information about a specific job, use the `report` command:
```bash
$ gridtk report -j 1
Job ID: 1
Name: gridtk
State: COMPLETED (0)
Nodes: None
Submitted command: ['sbatch', '--job-name', 'gridtk', '--output', 'logs/gridtk.%j.out', '--error', 'logs/gridtk.%j.out', 'job.sh']
Output file: logs/gridtk.136132.out
Hello, GridTK!
```
where you can see the exact sbatch command that was used to submit the job and
the output of the job.

### Stopping and Deleting a Job

To stop a running or pending job, use the `gridtk stop` command:

```bash
$ gridtk stop -j 1
Stopped job 1 with slurm id 136132
```

Stopped jobs will be still available in the job list:
```bash
$ gridtk list
ID   SLURM  STATE      NAME
--  ------  ---------  ------
 1  136137  CANCELLED  gridtk
1 job: 1 cancelled
```
and can be resubmitted using the `gridtk resubmit` command (more details on
resubmit further down) and you can still view their output using the `gridtk report`
command.

To delete a job (and its log file), use the `gridtk delete` command:
```bash
$ gridtk delete -j 1
Deleted job 1 with slurm id 136137
```

### Resubmitting a Job

If a job fails or is stopped, you can resubmit it using the `gridtk resubmit` command:
```bash
$ gridtk submit job.sh
1

$ gridtk stop -j 1
Stopped job 1 with slurm id 136139

$ gridtk resubmit -j 1
Resubmitted job 1

$ gridtk list
ID   SLURM  STATE    NAME    NODES
--  ------  -------  ------  ----------
 1  136140  PENDING  gridtk  (Priority)
1 job: 1 pending
```
Notice how the resubmitted job got a new slurm job id of `136140`.

## Advanced Usage

GridTK provides several advanced commands to help with more complex job
management tasks. These include job dependencies, array jobs, and resource
management.

### Job Submission without a Script

Since GridTK keeps track of both the sbatch options and the command to run, you
can skip creating a script and submit a job directly from the command line.
This is done by using `---` (3 dashes) to separate the sbatch options from the command to
run:
```bash
$ gridtk submit --job-name=gridtk-no-script --- echo 'Hello, GridTK!'
2
```
This syntax is unique to `gridtk submit` and is not supported by `sbatch`.
```bash
$ gridtk list -o id,state,name,command
ID  STATE    NAME              COMMAND
--  -------  ----------------  -------------------------------------
 1  PENDING  gridtk            gridtk submit job.sh
 2  PENDING  gridtk-no-script  gridtk submit --- echo Hello, GridTK!
2 jobs: 2 pending
```
What happens is that `gridtk submit` creates a temporary script with the command to run and
submits it to slurm. The temporary script is deleted after the job is submitted. The content of
this temporary script can be viewed using the `gridtk report` command:
```bash
$ gridtk report -j 2
Job ID: 2
Name: gridtk-no-script
State: PENDING (0)
Nodes: None
Submitted command: ['sbatch', '--job-name', 'gridtk-no-script', '--output', 'logs/gridtk-no-script.%j.out', '--error', 'logs/gridtk-no-script.%j.out', '/tmp/tmpegoy2ma1.sh']
Content of the temporary script:
#!/bin/bash
echo 'Hello, GridTK!'

Output file: logs/gridtk-no-script.136142.out
```
This is a fast, convenient, and **recommended** way to submit a job without having to create a
script and since everything is tracked by GridTK, you still benefit from the same
reproducibility guarantees.

### Environment Variables for CLI Options

While sbatch already allows providing values for some options through `SBATCH_` prefixed environment variables, not all options are supported. GridTK adds support for all CLI options through the `GRIDTK_SUBMIT_` prefix. For example:

```bash
# Set default email notification settings
export GRIDTK_SUBMIT_MAIL_USER=your.email@example.com
export GRIDTK_SUBMIT_MAIL_TYPE=END

# Use debug partition by default
export GRIDTK_SUBMIT_PARTITION=debug

# Now submit a job - it will use these settings automatically
gridtk submit job.sh
```

This is useful when you have a set of options that you always want to use, but don't want to specify them every time you submit a job.

Of course, other gridtk commands such as `gridtk resubmit` options can also be set using environment variables like: `export GRIDTK_RESUBMIT_STATE=ALL`.

### Job Dependencies

To submit a job that depends on another job, use the `--dependency` flag:

```bash
$ gridtk submit --dependency=<job_id> job.sh
```
The `--dependency` flag takes the same values as in `sbatch` except that you
need to specify local job ids instead of slurm job ids. Job ids given without a
dependency type (e.g. `--dependency 1` or `--dependency 1:2`) mean `afterany`, as
a single id does in `sbatch`.

To depend on jobs submitted outside gridtk, prefix their slurm job ids with
`slurm:` (each of them, as in `--dependency afterok:1:slurm:3793602:slurm:3793603`).
Ids that are not in the job database are reported, and nothing is submitted:
```bash
$ gridtk submit --dependency afterok:3793602 job.sh
Error: job(s) 3793602 not found in jobs.sql3 (--dependency takes local ids; write slurm ids as slurm:<id>, e.g. afterok:slurm:3793602)
```

### Repeat Jobs

You can submit the same script N times using the `--repeat` flag:
```bash
$ gridtk submit --repeat=3 job.sh
```
This will submit 3 jobs with the same script and the same options where each job
will depend on the previous ones (`afterany`, so that the chain continues when a
job reaches its time limit; pass e.g. `--dependency afterok:<id>` to choose another
type, or `--dependency <id>` to also wait for an earlier job). This is useful if your
script can resume from a checkpoint and you want to run it effectively for a longer time
than allowed by policy.

### Pinning a Job to the State of a Git Repository

Code installed in *editable* mode (`pip install -e .`, `pixi`/`uv` project environments)
is imported from the working copy when the job **starts**, possibly hours after
submission. Edits, commits or branch switches made in between silently change what a
queued job computes. The `--git-guard [DIR]` option records a fingerprint of the git
repository containing `DIR` (by default, the current directory) at submission time
(the `HEAD` commit, a hash of the tracked changes and a hash of the status including
untracked files) and makes the generated script re-check it when the job starts:

```bash
$ gridtk submit --git-guard --job-name=train --- python train.py
1
$ gridtk report -j 1
Job ID: 1
Name: train
State: PENDING (0)
Nodes: Unassigned
Git guard: /home/user/project @ 6bf37d093285 (clean)
...
```

If anything changed, the job exits with code `75` before running the command and
explains what differs in its log; `gridtk list` shows it as `FAILED (75)`. Fix or
restore the working copy and use `gridtk resubmit`, which pins the job to the
repository as it is at resubmission time. Set `GRIDTK_GIT_GUARD=0` in the job
environment (e.g. `--export=ALL,GRIDTK_GIT_GUARD=0`) to skip the check for a
throwaway run, or `GRIDTK_SUBMIT_GIT_GUARD=.` in your shell to enable the guard by
default (`--no-git-guard` then disables it for one submission).

Pass a directory to pin the job to another repository than the one you submit from,
for example to run the code of a branch checked out in a `git worktree` while keeping
the job database and logs in the main checkout:

```bash
$ gridtk submit --git-guard ../project-feature --job-name=train \
    --- pixi run --manifest-path ../project-feature/pyproject.toml python train.py
```

The guard requires the `---` form of submission (gridtk must generate the script) and
`git` on the compute nodes. Add `jobs.sql3` and the logs directory to `.gitignore` when
they live inside the repository, otherwise every submission makes the tree dirty.

### Monitoring Jobs

While `gridtk list` and `gridtk report` are useful for checking the status of jobs,
you might get more information about your jobs using `squeue`, `scontrol`, and `sacct`.
Here are some useful commands:

* Get information about a specific job: `scontrol show job <slurm_job_id>`
* Get information about a completed or failed job: `sacct -j <slurm_job_id>`.
* See ALL your jobs: `squeue --me`
* Cancel ALL your jobs: `scancel --me`
* View current QOS policies:
  ```bash
  sacctmgr show qos format=Name%20,Priority,Flags%30,MaxWall,MaxTRESPU%20,MaxJobsPU,MaxSubmitPU,MaxTRESPA%25
  ```
* Find out which accounts your username has access to:
  ```bash
  sacctmgr list associations
  # or
  sacctmgr -n -p list assoc where user=$USER | awk '-F|' '{print "   "$2}'
  ```

### Waiting for Jobs

Use `gridtk wait` to block until all jobs finish:
```bash
$ gridtk wait
Waiting for 3 job(s)... (checking every 10s)
Job 1: COMPLETED (0)
Job 2: COMPLETED (0)
Job 3: FAILED (1)
```

`gridtk wait` exits with code 1 if any job failed, making it easy to chain:
```bash
$ gridtk submit job.sh && gridtk wait && echo "All done!"
```

You can filter which jobs to wait for and change the polling interval:
```bash
$ gridtk wait -j 1,2 --interval 30
```

### Tab Completion

GridTK supports tab completion for the `gridtk` command. To enable it, add the following
line to your `~/.bashrc` file:
```bash
eval "$(_GRIDTK_COMPLETE=bash_source gridtk)"
```
or for `zsh` add the following line to your `~/.zshrc` file:
```bash
eval "$(_GRIDTK_COMPLETE=zsh_source gridtk)"
```

### Adjusting `gridtk list` Output

By default, `gridtk list` shows a compact overview of the jobs: their local and
slurm ids, state (with the exit code of failed jobs), name, nodes (or why they
are pending) and elapsed time.  Columns that are empty for all jobs are hidden.
On a terminal, long values are truncated so the table fits its width, states
are coloured (unless `NO_COLOR` is set), and a summary line follows the table.
When the output is piped, values are never truncated.

```bash
$ gridtk list
ID    SLURM  STATE       NAME        NODES   ELAPSED
--  -------  ----------  ----------  ------  -------
 1  3800685  COMPLETED   hello       hcne01     0:00
 2  3800686  COMPLETED   train[0-3]  hcne01     0:20
 3  3800692  FAILED (3)  fails       hcne01     0:00
3 jobs: 2 completed, 1 failed
```

Each `-v` shows more columns: `-v` adds the dependencies, exit code and log
file, and `-vv` the start time, array tasks, git guard and command.  Choose
columns with `-o`/`--columns`, either exactly (`-o id,state,name`) or relative
to the default ones (`-o +output,-nodes`); see `gridtk list --help` for all
columns.  `--truncate`/`--no-truncate` (`-t`/`-T`) force or disable truncation,
`--summary`/`--no-summary` the summary line, and `--no-header` omits the header.

For shell scripts, `-q`/`--quiet` prints only job ids:
```bash
$ gridtk resubmit -j $(gridtk list -s F -q | paste -sd,)
```

For machine-readable output (useful for scripting and AI agents), use `--json`.
It always includes all the details of each job, unless keys are selected with
`-o`:
```bash
$ gridtk list --json -o id,state,exit_code
[{"job_id": 1, "state": "COMPLETED", "exit_code": "0"}, ...]

$ gridtk list --json | jq '.[0]'
{
  "job_id": 1,
  "slurm_id": 3800685,
  "state": "COMPLETED",
  "name": "hello",
  "nodes": "hcne01",
  "elapsed_seconds": 0,
  "dependencies": [],
  "exit_code": "0",
  "output": "logs/hello.3800685.out",
  "start": "2026-10-07T17:19:02",
  "array_task_ids": null,
  "git_guard": null,
  "command": "gridtk submit --- echo hello",
  "reason": null,
  "finished": true,
  "outputs": ["logs/hello.3800685.out"]
}
```
The elapsed and start times and the pending reason are read from Slurm on each
call and are `null` when the job database is read-only.

`gridtk report --tail N` (`-n N`) shows only the last N lines of each log, and
lines redrawn by progress bars (e.g. tqdm) only show their last update, which
keeps reports short (use `--raw` for the logs as they are):
```bash
$ gridtk report -j 4 --tail 2
...
Output file: logs/train.3800691.out
[last 2 of 1532 lines]
epoch 10: 100%|██████████| 500/500 [01:02<00:00, 8.01it/s]
done
```

The `--json` flag is also available on `submit` and `report`:
```bash
$ gridtk submit --json job.sh
{"job_id": 1, "slurm_id": 506994, "name": "gridtk"}

$ gridtk report --json -j 1
[{"job_id": 1, "name": "gridtk", "state": "COMPLETED", ...}]
```
