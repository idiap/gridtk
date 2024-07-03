<!--
SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![latest-docs](https://img.shields.io/badge/docs-latest-orange.svg)](https://gridtk.readthedocs.io/en/latest/)
[![build](https://gitlab.idiap.ch/software/gridtk/badges/main/pipeline.svg)](https://gitlab.idiap.ch/software/gridtk/commits/main)
[![coverage](https://gitlab.idiap.ch/software/gridtk/badges/main/coverage.svg)](https://www.idiap.ch/software/biosignal/docs/software/gridtk/main/coverage/index.html)
[![repository](https://img.shields.io/badge/gitlab-project-0000c0.svg)](https://gitlab.idiap.ch/software/gridtk)

# GridTK: SLURM Job Managetment for Humans

## Introduction

GridTK is a powerful command-line tool designed to simplify the management of
SLURM jobs. At its core, GridTK provides a drop-in replacement for `sbatch`,
`gridtk submit`, which allows you to get started quickly. This
tutorial will guide you through the process of using the `gridtk` script to
efficiently manage your SLURM workloads. We will cover the basics of
installation, submission, monitoring, and various commands provided by GridTK.

## Prerequisites

Before diving into GridTK, ensure you have the following prerequisites:

1. A working SLURM setup.
2. [Pixi](https://pixi.sh) installed.
3. GridTK installed (instructions provided below).

## Installation

To install GridTK, open your terminal and run the following command:

```bash
$ pixi global install pipx
$ pixi global install python=3.12
$ pipx install --force --python python3.12 'git+https://gitlab.idiap.ch/software/gridtk.git'
```
It is **not recommennded** to install GridTK using `pip install gridtk` in the
same environment as your expeirments. GirdTK does not need to be installed in
the same environment as your experiments and its depencencies may conflict with
your experiments.

## Basic Usage

In this section, we will cover the basic commands and usage of the GridTK
script. The primary goal is to help you get familiar with submitting,
monitoring, and managing your SLURM jobs using GridTK.

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
where `1` is the the local job id (not the slurm job id) for your job. The job
numbers always start with 1 which is easier to remember than the slurm job id.

`gridtk submit` is a drop-in replacement for `sbatch` and accepts the same options while adding its own.
Run `gridtk submit --help` to see the list of `gridtk submit` specific options and run `sbatch --help` to see the full list of options for `sbatch`.

Note that your slurm cluster may require you to specify a partition, an account,
or anoher option. You can do so by adding them to `gridtk submit --accoount=myaccount --partition=mypartition job.sh`
or setting default values using enviroment variables such as
`SBATCH_ACCOUNT` and `SBATCH_PARTITION`.

### Monitoring Jobs

Use the `gridtk list` command to view the status of your jobs:
```bash
$ gridtk list
  job-id    grid-id  nodes    state        job-name    output                  dependencies    command
--------  ---------  -------  -----------  ----------  ----------------------  --------------  --------------------
       1     136132  None     PENDING (0)  gridtk      logs/gridtk.136132.out                  gridtk submit job.sh
```
`gridtk list` will only show jobs that are submitted using `gridtk submit` **in the current folder**.
You can see the submitted job got a local job id of `1` and a slurm job id of
`136132`.
It is in the `PENDING` state and its name is `gridtk` by default (it is
recommended to give a meaningful name using the `gridtk submit --job-name`
option).
The output files are written to the `logs/` directory by default (you may change
the directory with the `gridtk --logs-dir` option).
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
Stopped job 1 wiht slurm id 136132
```

Stopped jobs will be still avaliable in the job list:
```bash
$ gridtk list
  job-id    slurm-id  nodes    state          job-name    output                  dependencies    command
--------  ----------  -------  -------------  ----------  ----------------------  --------------  --------------------
       1      136137  None     CANCELLED (0)  gridtk      logs/gridtk.136137.out                  gridtk submit job.sh
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
Stopped job 1 wiht slurm id 136139

$ gridtk resubmit -j 1
Resubmitted job 1

$ gridtk list
  job-id    slurm-id  nodes    state        job-name    output                  dependencies    command
--------  ----------  -------  -----------  ----------  ----------------------  --------------  --------------------
       1      136140  None     PENDING (0)  gridtk      logs/gridtk.136140.out                  gridtk submit job.sh
```
Notice how the resubmitted job got a new slurm job id of `136140`.

## Advanced Usage

GridTK provides several advanced commands to help with more complex job
management tasks. These include job dependencies, array jobs, and resource
management.

### Job Submission wihtout a Script
Since GridTK keeps track of both the sbatch options and the command to run, you
can skip creating a script and submit a job directly from the command line.
This is done by using `---` (3 dashes) to separate the sbatch options from the command to
run:
```bash
$ gridtk submit --job-name=gridtk-no-script --- echo 'Hello, GridTK!'
2
```
This syntax is unique to `girdtk submit` and is not supported by `sbatch`.
```bash
$ gridtk list
  job-id    slurm-id  nodes    state        job-name          output                            dependencies    command
--------  ----------  -------  -----------  ----------------  --------------------------------  --------------  ------------------------------------
       1      136140  None     PENDING (0)  gridtk            logs/gridtk.136140.out                            gridtk submit job.sh
       2      136142  None     PENDING (0)  gridtk-no-script  logs/gridtk-no-script.136142.out                  gridtk submit --- echo Hello, GridTK!
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
This is a fast, convenient, and **recomended** way to submit a job without having to create a
script and since everthing is tracked by GridTK, you still benefit from the same
reproducibility gurantees.

### Job Dependencies

To submit a job that depends on another job, use the `--dependency` flag:

```bash
$ gridtk submit --dependency=<job_id> job.sh
```
The `--dependency` flag takes the same values as in `sbatch` except that you
need to specify local job ids instead of slurm job ids.

### Repeat Jobs

You can submit the same script N times using the `--repeat` flag:
```bash
$ gridtk submit --repeat=3 job.sh
```
This will submit 3 jobs with the same script and the same options where each job
will depeend on the previous one. This is useful if your script can resume from
a checkpoint and you want to run it effectively for a longer time than allowed
by polciy.

### Monitoring Jobs

While `gridtk list` and `gridtk report` are useful for checking the status of jobs,
you might get more information about your jobs using `squeue`, `scontrol`, and `sacct`.
Here are some usefull commands:

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
