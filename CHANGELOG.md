<!--
SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

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
