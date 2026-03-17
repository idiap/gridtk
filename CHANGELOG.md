<!--
SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## [3.2.1](https://github.com/idiap/gridtk/compare/v3.2.0...v3.2.1) (2026-03-17)

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
