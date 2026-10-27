# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path


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


_DEP_JOB_ID = re.compile(r"(slurm:)?(\d+)(\+\d+)?")
"""A job id in a dependency string: a local id, or a slurm id prefixed with
``slurm:``, optionally followed by ``+<time>`` (for ``after``)."""


class UnknownJobIdsError(ValueError):
    """Some local job ids of a dependency string are not in the job database."""

    def __init__(self, job_ids: Iterable[int]) -> None:
        self.job_ids = list(job_ids)
        """The unknown job ids, in order of appearance."""
        self.dependent: int | None = None
        """The local id of the job that depends on them, if it is in the database."""
        super().__init__(
            f"job(s) {', '.join(map(str, self.job_ids))} not found in the job database"
        )


def job_ids_from_dep_str(dependency_string: str | None) -> list[int]:
    """Extract the local job IDs from a dependency string (not ``slurm:<id>``)."""
    if not dependency_string:
        return []
    return [
        int(match.group(2))
        for match in _DEP_JOB_ID.finditer(dependency_string)
        if not match.group(1)
    ]


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
    return "".join(
        f"afterany:{spec}" if spec[:1].isdigit() or spec.startswith("slurm:") else spec
        for spec in specs
    )


def replace_job_ids_in_dep_str(
    dependency_string: str | None, replacements: Mapping[int, int]
) -> str | None:
    """Replace each local job ID in a dependency string with its ID in
    ``replacements``, and each ``slurm:<id>`` with ``<id>``.

    Raises
    ------
    UnknownJobIdsError
        If local job ids are not in ``replacements``.
    """
    if not dependency_string:
        return dependency_string
    missing = [
        job_id
        for job_id in dict.fromkeys(job_ids_from_dep_str(dependency_string))
        if job_id not in replacements
    ]
    if missing:
        raise UnknownJobIdsError(missing)

    def replacement_func(match):
        job_id = int(match.group(2))
        if not match.group(1):
            job_id = replacements[job_id]
        return f"{job_id}{match.group(3) or ''}"

    return _DEP_JOB_ID.sub(replacement_func, dependency_string)


def parse_slurm_duration(duration: str | None) -> int | None:
    """Return the seconds in a Slurm duration (``[D-][[HH:]MM:]SS``), or ``None``.

    This is the format of ``squeue -o %M`` and of ``RunTime`` in ``scontrol show
    job``.  Values Slurm uses for "no time" (``N/A``, ``INVALID``, ``UNLIMITED``,
    ...) give ``None``.
    """
    if not duration:
        return None
    days, _, clock = duration.strip().rpartition("-")
    try:
        parts = [int(x) for x in clock.split(":")]
        if len(parts) > 3:
            return None
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds + int(days or 0) * 86400
    except ValueError:
        return None


def format_duration(seconds: int | None) -> str:
    """Format seconds as Slurm does (``[D-]HH:MM:SS``, or ``MM:SS`` under an hour)."""
    if seconds is None:
        return ""
    days, seconds = divmod(int(seconds), 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}-{hours:02d}:{minutes:02d}:{seconds:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def compact_ranges(indexes: Iterable[int]) -> str:
    """Write integers as ranges, e.g. ``[0, 1, 2, 5, 7, 8]`` -> ``"0-2,5,7-8"``."""
    ranges: list[list[int]] = []
    for index in sorted(set(indexes)):
        if ranges and index == ranges[-1][1] + 1:
            ranges[-1][1] = index
        else:
            ranges.append([index, index])
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)


def _log_lines(path: Path, collapse_cr: bool) -> Iterator[str]:
    """Yield the lines of a log, without their line ending.

    Progress bars (e.g. tqdm) redraw a line with carriage returns, so a single
    physical line may hold thousands of updates: if ``collapse_cr`` is set, only
    the last non-empty update of each line is kept.
    """
    with path.open("rb") as f:
        for raw in f:
            line = raw.decode(errors="replace").rstrip("\n")
            if collapse_cr:
                segments = [s for s in line.rstrip("\r").split("\r") if s]
                line = segments[-1] if segments else ""
            yield line


def read_log(
    path: Path, tail: int | None = None, collapse_cr: bool = True
) -> tuple[str, int]:
    """Read a log file, returning its text and its number of lines.

    Parameters
    ----------
    path
        The log file.
    tail
        If set, return only the last ``tail`` lines.  The file is streamed, so
        large logs are never held in memory.
    collapse_cr
        Keep only the last update of lines redrawn with carriage returns (see
        :func:`_log_lines`).
    """
    total = 0
    kept: deque[str] = deque(maxlen=tail)
    for line in _log_lines(path, collapse_cr):
        total += 1
        kept.append(line)
    return "".join(f"{line}\n" for line in kept), total
