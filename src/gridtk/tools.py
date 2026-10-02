# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from collections.abc import Mapping


def parse_array_indexes(indexes_str: str) -> list[int]:
    """Pares a string of array indexes to a list of integers."""

    def parse_range(range_str):
        if ":" in range_str:
            range_part, step = range_str.split(":")
            start, end = map(int, range_part.split("-"))
            step = int(step)
            return list(range(start, end + 1, step))

        start, end = map(int, range_str.split("-"))
        return list(range(start, end + 1))

    def parse_segment(segment):
        if "-" in segment:
            return parse_range(segment)

        return [int(segment)]

    # Remove any limit on simultaneous running tasks
    if "%" in indexes_str:
        indexes_str = indexes_str.split("%")[0]

    segments = indexes_str.split(",")
    result = []
    for segment in segments:
        result.extend(parse_segment(segment))

    return result


def job_ids_from_dep_str(dependency_string: str | None) -> list[int]:
    """Extract job IDs from a dependency string."""
    if not dependency_string:
        return []
    # Regular expression to match job IDs with optional +time
    dep_job_id_pattern = re.compile(r"(\d+)(?:\+\d+)?")

    # Find all matches in the dependency string
    job_ids = dep_job_id_pattern.findall(dependency_string)

    return list(map(int, job_ids))


def add_default_dep_type(dependency_string: str | None) -> str | None:
    """Prefix ``afterany:`` to dependencies that start with a job id.

    sbatch reads a bare job id (``5``) as ``afterany:5`` but rejects a bare list of
    them (``5:6``), which ``--repeat`` builds by appending job ids.  Making the type
    explicit gives both the meaning sbatch gives a single id.
    """
    if not dependency_string:
        return dependency_string
    # keep the "," (all of) and "?" (any of) separators
    specs = re.split(r"([,?])", dependency_string)
    return "".join(f"afterany:{spec}" if spec[:1].isdigit() else spec for spec in specs)


def replace_job_ids_in_dep_str(
    dependency_string: str | None, replacements: Mapping[int, int]
) -> str | None:
    """Replace each job ID in a dependency string with its ID in ``replacements``."""
    if not dependency_string:
        return dependency_string
    # Regular expression to match job IDs with optional +time
    job_id_pattern = re.compile(r"(\d+)(\+\d+)?")

    def replacement_func(match):
        job_id = int(match.group(1))
        if job_id not in replacements:
            raise ValueError(f"No replacement for job id {job_id}")
        return f"{replacements[job_id]}{match.group(2) or ''}"

    # Substitute all job IDs in the dependency string
    return job_id_pattern.sub(replacement_func, dependency_string)
