<!--
SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## Unreleased


### Features

* `gridtk list` shows a compact overview by default: local and slurm ids, state (followed by the exit code only for jobs that failed, e.g. `FAILED (3)`), name (with the task ids of array jobs, e.g. `train[0-3]`), nodes (or, in parentheses, why a pending job waits) and elapsed time; columns empty for all jobs are hidden. The output file, dependencies and command, always shown so far, now need `-v` or `-o`. On a terminal, long values are truncated so the table fits its width (log paths keep their end, where the slurm id is), states are coloured (unless `NO_COLOR` is set) and a summary line follows (`5 jobs: 3 completed, 2 failed`); when piped, values are never truncated and there is no colour or summary. Headers are now short and upper-case (`ID`, `SLURM`, `STATE`, ...): scripts should use `--json` or `-q` rather than parse the table
* `gridtk list -v` adds the dependencies, exit code and output file, `-vv` the start time, array tasks, git guard and command; `-o`/`--columns` selects columns exactly (`-o id,state,name`) or relative to the default ones (`-o +output,-nodes`), `--truncate`/`--no-truncate` (`-t`/`-T`) force or disable truncation, `--summary`/`--no-summary` the summary line, `--no-header` omits the header and `-q`/`--quiet` prints only job ids, e.g. `gridtk resubmit -j $(gridtk list -s F -q | paste -sd,)`
* `gridtk list --json` keeps its keys and adds `outputs` (the log files of all array tasks), `reason`, `elapsed_seconds`, `start`, `finished`, `array_task_ids` and `git_guard`, with `null` for missing values; `-o` selects keys (`gridtk list --json -o id,state,exit_code`), and the output is compact when piped. The elapsed and start times and the pending reason are read from slurm on each call (they are not stored, so job databases need no migration) and are `null` when the database is read-only
* `gridtk report --tail N` (`-n N`) shows only the last N lines of each log (with `--json`, logs also report `total_lines` and `truncated`), reading logs as a stream so large ones are never held in memory; lines redrawn by progress bars (e.g. tqdm) now only show their last update, which reduces logs of thousands of progress updates to a few lines (`--raw` shows logs as they are)
* gridtk no longer depends on tabulate


* `gridtk submit --dependency` accepts slurm ids of jobs submitted outside gridtk, prefixed with `slurm:` (e.g. `--dependency afterok:1:slurm:3793602`); they are passed to sbatch as they are and are not listed as dependencies by `gridtk list`


### Deprecations

* `gridtk list -w`/`--wrap` is deprecated and will be removed in a future version: it now prints a warning and shows full values, as `--no-truncate` does; tables are no longer wrapped. `-t`/`--truncate` remains, as the override of the new automatic truncation


### Bug Fixes

* `gridtk submit --dependency` with ids that are not in the job database (e.g. slurm ids given as local ones) fails with a message naming them, e.g. `job(s) 3793602 not found in jobs.sql3 (--dependency takes local ids; ...)`, instead of a `ValueError` traceback; `gridtk resubmit` of a job whose dependency was deleted fails the same way before cancelling any job, instead of cancelling the jobs and then failing
* commands that fail (e.g. `gridtk submit` with an unknown dependency) no longer leave an empty job database and logs directory behind
* array jobs are matched to their `squeue` entries (`<id>_<task>` or `<id>_[<tasks>]`): they were only read from sacct, which lacks the live state of pending and running jobs

## [4.0.0](https://github.com/idiap/gridtk/compare/v3.2.1...v4.0.0) (2026-10-06)


### ⚠ BREAKING CHANGES

* drop support for Python 3.9 and 3.10: the minimum supported version is now 3.11, matching the `python_min` of conda-forge (CFEP-25); continuous integration tests Python 3.11, 3.12, 3.13 and 3.14 ([#41](https://github.com/idiap/gridtk/issues/41)) ([a01f8c9..f870845](https://github.com/idiap/gridtk/compare/a01f8c9..f870845))

### Features

* add `--git-guard [DIR]` to `gridtk submit`: records the HEAD commit and hashes of the tracked changes and status (untracked files included) of the git repository containing `DIR` (default: the current directory; `--no-git-guard` overrides a `GRIDTK_SUBMIT_GIT_GUARD` default), and makes the generated script abort with exit code 75 when they differ at job start; `gridtk report` shows the recorded state (also with `--json`), `gridtk resubmit` pins the job to the repository as it is at resubmission time, and `GRIDTK_GIT_GUARD=0` in the job environment skips the check ([#41](https://github.com/idiap/gridtk/issues/41)) ([1258d7d](https://github.com/idiap/gridtk/commit/1258d7d5e93479c930c2d22044ba0279caff7942))
* opening a job database written by an older gridtk version (missing the `jobs.git_guard` column) now fails with a message asking to let its jobs finish with that version or to delete it, instead of a database error ([#41](https://github.com/idiap/gridtk/issues/41)) ([ae4545b](https://github.com/idiap/gridtk/commit/ae4545b7c433828374d477b218fe1ed8fe2b20e5))
* Unpin tabulate and click so installations can match more options ([#41](https://github.com/idiap/gridtk/issues/41))([e70db45](https://github.com/idiap/gridtk/commit/e70db456b5ea4a3cc885014631f000fb89384d9c))
* development QA moves from pre-commit and mypy to prek and ty (`pixi run qa`); the `dev` extra now installs `gridtk[doc,test,qa]` ([#41](https://github.com/idiap/gridtk/issues/41)) ([7bf6d3e](https://github.com/idiap/gridtk/commit/7bf6d3e796e22bfbf100e4aa7053c14310f9643a))


### Bug Fixes

* `gridtk submit --dependency` reads job ids given without a type (`5`, `5:6`) as `afterany`, as sbatch does for a single id: `--repeat N`, with or without `--dependency <id>`, used to pass lists such as `--dependency <id1>:<id2>` without a type, which sbatch rejects
 ([#43](https://github.com/idiap/gridtk/issues/43)) ([2f3dfba](https://github.com/idiap/gridtk/commit/2f3dfba20c00ba01bb4b336461969f538ec853f3))
* `gridtk list`, `report` and `wait` show the exit code of the batch script (sacct's `exit_code`) instead of the derived exit code of the job steps, which is 0 for jobs without `srun`, so failed jobs no longer show as `FAILED (0)`; jobs killed by a signal show `<code>:<signal>` as in sacct, and jobs that squeue still lists after they finished are read from sacct, since squeue reports no exit code
 ([#42](https://github.com/idiap/gridtk/issues/42)) ([26a6dd8](https://github.com/idiap/gridtk/commit/26a6dd82a2d7055f4c30e04dfb3e7363eec173d0))
* `gridtk submit --dependency` with several dependency types (`afterok:5,afterany:3`) gives each job id its own slurm id: the ids were replaced in database order, so jobs could swap dependency types; a job id given in more than one type (`afterok:3,afterany:3`) no longer fails
 ([#44](https://github.com/idiap/gridtk/issues/44)) ([3a9a987](https://github.com/idiap/gridtk/commit/3a9a98732040841fda042efa20c684e42e8e9dc4))

## [3.2.1](https://github.com/idiap/gridtk/compare/v3.2.0...v3.2.1) (2026-08-17)


### Bug Fixes

* fix the documentation building process at Read The Docs ([#37](https://github.com/idiap/gridtk/issues/37)) ([7de360e](https://github.com/idiap/gridtk/commit/7de360e1bd3c0a3acc34bb7df222446ff3995640))
* recommend uv for installation in README ([#33](https://github.com/idiap/gridtk/issues/33)) ([f468ecc](https://github.com/idiap/gridtk/commit/f468ecc3e841af078d46cf56b4fed10d5ae80460))

## [3.2.0](https://github.com/idiap/gridtk/compare/v3.1.0...v3.2.0) (2026-03-17)


### Features

* add --json output flag to submit, list, and report commands ([#29](https://github.com/idiap/gridtk/issues/29)) ([3d3d6bd](https://github.com/idiap/gridtk/commit/3d3d6bd3c058429dd5f18c7f6ea174c865166de6))
* add wait command with non-zero exit on failure ([#28](https://github.com/idiap/gridtk/issues/28)) ([a97666f](https://github.com/idiap/gridtk/commit/a97666f9a5f15be4a56ad23156302558fb739228))


### Bug Fixes

* show feedback when commands match no jobs ([#27](https://github.com/idiap/gridtk/issues/27)) ([ffd9e13](https://github.com/idiap/gridtk/commit/ffd9e13313ed1de5aa29944baefa7c8a38e3971f))

## [3.1.0](https://github.com/idiap/gridtk/compare/v3.0.1...v3.1.0) (2026-03-16)


### Features

* CLI options can be supplied using env vars ([7834627](https://github.com/idiap/gridtk/commit/7834627c404e6e942f9bba350a50bbb825f99666))
* options to adjust gridtk list output to fit terminal width ([#15](https://github.com/idiap/gridtk/issues/15)) ([f324491](https://github.com/idiap/gridtk/commit/f3244913b5a96346cd441663c9f2170dd66b0fb8)), closes [#13](https://github.com/idiap/gridtk/issues/13)


### Bug Fixes

* explicitly speficy the sphinx.configuration key in Read the Docs setup ([ae6b0ae](https://github.com/idiap/gridtk/commit/ae6b0ae42930dd58e420db524d4fdbd47c247c40))
* show feedback when gridtk resubmit finds no matching jobs ([#24](https://github.com/idiap/gridtk/issues/24)) ([a5801d7](https://github.com/idiap/gridtk/commit/a5801d754309852b40627179f897a326b37036c9)), closes [#14](https://github.com/idiap/gridtk/issues/14)
* use squeue as primary job status source over sacct ([#25](https://github.com/idiap/gridtk/issues/25)) ([e3a91ef](https://github.com/idiap/gridtk/commit/e3a91ef9cdc0829f2b5fddbaead809199c4923c2)), closes [#17](https://github.com/idiap/gridtk/issues/17)

## [3.0.1](https://github.com/idiap/gridtk/compare/v3.0.0...v3.0.1) (2024-07-23)


### Bug Fixes

* Always point to the stable documentaiton ([1a584b5](https://github.com/idiap/gridtk/commit/1a584b54013d249ded08e120aafd2ae30f808c26))
* **cli:** add range specs to --jobs' help message. ([c013c41](https://github.com/idiap/gridtk/commit/c013c411350d3af7f314bd182b9ae80772c4cedd))
* do not delete the logs folder when the database is not empty ([069a939](https://github.com/idiap/gridtk/commit/069a939d2fded96eb27337b699742b8accbf03e7))
* do not recommend installing with pixi ([cf50221](https://github.com/idiap/gridtk/commit/cf5022174f67f4ce9d3f242f6058194676228610))
* handle sacct failures ([ea53ede](https://github.com/idiap/gridtk/commit/ea53ede1bc64289661610dbedf298b5971bc21b1))
* more error handling ([2816346](https://github.com/idiap/gridtk/commit/28163462a03c34c60a68cdf00367ce2a471f8043))
* print path of logs file relative to cwd ([ec7a9f5](https://github.com/idiap/gridtk/commit/ec7a9f5315052596b6937c7cbcfbd6a38313d196))
* remove typos in code and tests. ([9f7acd0](https://github.com/idiap/gridtk/commit/9f7acd03430781c47432255dae0b8278d20624f3))
* retrieve job status from scontrol when sacct is not available ([3e2fc62](https://github.com/idiap/gridtk/commit/3e2fc62b945adb837ee94dfaeab30eeeb65d0aa5))
* when the database is read-only ([f3c3893](https://github.com/idiap/gridtk/commit/f3c3893dbfc20f6e749ad98aca26c58fb7f07fd0))

## [3.0.0](https://github.com/idiap/gridtk/compare/v2.1.0...v3.0.0) (2024-07-09)


### ⚠ BREAKING CHANGES

* GridTK has been completely rewritten from scratch to work with Slurm instead of SGE.
* See the [README.md](README.md) to learn how to use the new GridTK.
* Development has been moved to [GitHub](https://github.com/idiap/gridtk).
---
