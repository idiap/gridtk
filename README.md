<!--
SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>

SPDX-License-Identifier: GPL-3.0-or-later
-->

[![latest-docs](https://img.shields.io/badge/docs-latest-orange.svg)](https://gridtk.readthedocs.io/en/latest/)
[![build](https://gitlab.idiap.ch/software/gridtk/badges/main/pipeline.svg)](https://gitlab.idiap.ch/software/gridtk/commits/main)
[![coverage](https://gitlab.idiap.ch/software/gridtk/badges/main/coverage.svg)](https://www.idiap.ch/software/biosignal/docs/software/gridtk/main/coverage/index.html)
[![repository](https://img.shields.io/badge/gitlab-project-0000c0.svg)](https://gitlab.idiap.ch/software/gridtk)


# Grid-enabled job submitter and execution monitor for Idiap

This package provides a set of python wrappers around SGE utilities like
`qsub`, `qstat` and `qdel`, and simplify job submission and management. It
interacts with these tools to submit and manage grid jobs.  It is hardcoded to
work with the SGE grid at Idiap.

For installation and usage instructions, check-out our documentation.
