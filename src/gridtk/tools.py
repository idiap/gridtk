# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
import re


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


def replace_job_ids_in_dep_str(dependency_string, replacements):
    """Replace job IDs in a dependency string with new IDs from a list."""
    if not dependency_string:
        return dependency_string
    # Regular expression to match job IDs with optional +time
    job_id_pattern = re.compile(r"(\d+)(\+\d+)?")

    # Function to replace matched job ID with corresponding replacement from the list
    def replacement_func(match):
        time_part = match.group(2) if match.group(2) else ""
        if replacements:
            new_job_id = replacements.pop(0)
            return f"{new_job_id}{time_part}"
        raise ValueError("Not enough replacements")

    # Substitute all job IDs in the dependency string
    return job_id_pattern.sub(replacement_func, dependency_string)
