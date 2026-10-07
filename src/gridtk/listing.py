# SPDX-FileCopyrightText: 2026 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Columns and rendering of ``gridtk list``.

Each :class:`Column` knows how to show a job in the table and in JSON, so the
human and machine outputs cannot drift apart.
"""

from __future__ import annotations

import dataclasses

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any

from .tools import compact_ranges, format_duration

if TYPE_CHECKING:  # the models (and sqlalchemy) are slow to import
    from .models import Job


def _name(job: Job) -> str:
    if job.is_array_job and job.array_task_ids:
        return f"{job.name}[{compact_ranges(job.array_task_ids)}]"
    return job.name


def _nodes(job: Job) -> str:
    if job.state != "PENDING":
        return job.nodes or ""
    # pending jobs have no nodes: Job.update() stores why they wait instead
    reason = job.reason or (job.nodes or "").strip("()")
    return "" if reason in ("", "None", "None assigned") else f"({reason})"


def _elapsed(job: Job) -> str:
    return "" if job.state == "PENDING" else format_duration(job.elapsed)


def _output(job: Job) -> str:
    paths = job.output_paths()
    if not paths:
        return ""
    return str(paths[0]) + (f" (+{len(paths) - 1})" if len(paths) > 1 else "")


def _command(job: Job) -> str:
    return "gridtk submit " + " ".join(job.command)


def _git_guard(job: Job) -> str:
    if job.git_guard is None:
        return ""
    return job.git_guard.head[:8] + ("*" if job.git_guard.is_dirty else "")


@dataclasses.dataclass(frozen=True)
class Column:
    """A column of ``gridtk list``."""

    key: str
    """Name of the column in ``--columns``."""

    header: str
    """Header of the column in the table."""

    level: int
    """Verbosity (number of ``-v``) from which the column is shown."""

    text: Callable[[Job], str]
    """The job's value as shown in the table."""

    json_key: str
    """Key of the job's value in JSON."""

    value: Callable[[Job], Any]
    """The job's value in JSON."""

    shrink: int = 0
    """Order in which the column is truncated to fit the terminal (lowest first);
    0 for columns that are never truncated."""

    min_width: int = 0
    """Width under which the column is not truncated."""

    align: str = "left"
    """Alignment of the column in the table."""


COLUMNS: dict[str, Column] = {
    c.key: c
    for c in (
        Column(
            "id", "ID", 0, lambda j: str(j.id), "job_id", lambda j: j.id, align="right"
        ),
        Column(
            "slurm_id",
            "SLURM",
            0,
            lambda j: str(j.grid_id or ""),
            "slurm_id",
            lambda j: j.grid_id,
            align="right",
        ),
        Column(
            "state", "STATE", 0, lambda j: j.state_label, "state", lambda j: j.state
        ),
        Column(
            "name", "NAME", 0, _name, "name", lambda j: j.name, shrink=4, min_width=8
        ),
        Column(
            "nodes",
            "NODES",
            0,
            _nodes,
            "nodes",
            lambda j: j.nodes,
            shrink=3,
            min_width=8,
        ),
        Column(
            "elapsed",
            "ELAPSED",
            0,
            _elapsed,
            "elapsed_seconds",
            lambda j: j.elapsed,
            align="right",
        ),
        Column(
            "deps",
            "DEPS",
            1,
            lambda j: ",".join(str(i) for i in j.dependencies_ids),
            "dependencies",
            lambda j: list(j.dependencies_ids),
        ),
        Column(
            "exit_code",
            "EXIT",
            1,
            lambda j: j.exit_code or "",
            "exit_code",
            lambda j: j.exit_code,
        ),
        Column(
            "output",
            "OUTPUT",
            1,
            _output,
            "output",
            lambda j: str(j.output_paths()[0]) if j.output_paths() else None,
            shrink=2,
            min_width=16,
        ),
        Column(
            "start",
            "START",
            2,
            lambda j: j.start.strftime("%Y-%m-%d %H:%M") if j.start else "",
            "start",
            lambda j: j.start.isoformat() if j.start else None,
        ),
        Column(
            "array",
            "ARRAY",
            2,
            lambda j: compact_ranges(j.array_task_ids or []),
            "array_task_ids",
            lambda j: j.array_task_ids,
            shrink=5,
            min_width=8,
        ),
        Column(
            "git_guard",
            "GUARD",
            2,
            _git_guard,
            "git_guard",
            lambda j: j.git_guard.to_dict() if j.git_guard else None,
        ),
        Column(
            "command",
            "COMMAND",
            2,
            _command,
            "command",
            _command,
            shrink=1,
            min_width=16,
        ),
        # only shown when asked for with --columns (or -vvv)
        Column(
            "reason",
            "REASON",
            3,
            lambda j: j.reason or "",
            "reason",
            lambda j: j.reason,
            shrink=5,
            min_width=8,
        ),
        Column(
            "finished",
            "FINISHED",
            3,
            lambda j: "yes" if j.finished else "no",
            "finished",
            lambda j: j.finished,
        ),
        Column(
            "outputs",
            "OUTPUTS",
            3,
            lambda j: ",".join(str(p) for p in j.output_paths()),
            "outputs",
            lambda j: [str(p) for p in j.output_paths()],
            shrink=2,
            min_width=16,
        ),
    )
}
"""All columns, in the order they are shown."""

_ALIASES = {
    "job_id": "id",
    "jobid": "id",
    "grid_id": "slurm_id",
    "slurm": "slurm_id",
    "job_name": "name",
    "node": "nodes",
    "dependencies": "deps",
    "exit": "exit_code",
    "time": "elapsed",
    "elapsed_seconds": "elapsed",
    "array_task_ids": "array",
    "guard": "git_guard",
}


def column_keys() -> list[str]:
    """Return the names accepted by :func:`select_columns`."""
    return list(COLUMNS)


def _resolve(key: str) -> str:
    key = key.strip().lower().replace("-", "_")
    key = _ALIASES.get(key, key)
    if key not in COLUMNS:
        raise ValueError(
            f"Unknown column {key!r}; valid columns are: {', '.join(COLUMNS)}"
        )
    return key


def select_columns(
    verbosity: int, spec: str | None = None
) -> tuple[list[Column], set[str]]:
    """Return the columns to show, and the keys of those explicitly requested.

    Parameters
    ----------
    verbosity
        The number of ``-v``: columns of this level or lower are shown.
    spec
        Comma-separated column names.  If the first one starts with ``+`` or
        ``-``, columns are added to (``+``, or no prefix) or removed from
        (``-``) those of ``verbosity``.  Otherwise, exactly these columns are
        shown, in this order.

    Raises
    ------
    ValueError
        If a column name is unknown.
    """
    items = [i.strip() for i in (spec or "").split(",") if i.strip()]
    relative = not items or items[0][0] in "+-"
    keys = [c.key for c in COLUMNS.values() if c.level <= verbosity] if relative else []
    requested: set[str] = set()
    for item in items:
        if item[0] == "-":
            key = _resolve(item[1:])
            if key in keys:
                keys.remove(key)
            continue
        key = _resolve(item.lstrip("+"))
        requested.add(key)
        if key not in keys:
            keys.append(key)
    return [COLUMNS[k] for k in keys], requested


def truncate(text: str, width: int, ellipsis: str = "…", keep_end: bool = False) -> str:
    """Shorten ``text`` to ``width`` characters, marking the cut with ``ellipsis``
    at its end or, if ``keep_end``, at its start (to keep the file name of paths,
    which holds the Slurm job id).
    """
    if len(text) <= width:
        return text
    keep = max(width - len(ellipsis), 0)
    if keep_end:
        return ellipsis + text[len(text) - keep :]
    return text[:keep] + ellipsis


_SEPARATOR = 2
"""Spaces between columns in the table."""


def fit_to_width(
    rows: Sequence[Sequence[str]],
    columns: Sequence[Column],
    width: int,
    ellipsis: str = "…",
) -> list[list[str]]:
    """Truncate the cells of ``rows`` so the table is at most ``width`` wide.

    Columns are shrunk in the order of :attr:`Column.shrink`, down to their
    :attr:`Column.min_width` (or the width of their header).  Columns without
    ``shrink`` are never cut, so the table may still be wider than ``width``.
    """
    widths = [
        max([len(c.header)] + [len(row[i]) for row in rows])
        for i, c in enumerate(columns)
    ]
    excess = sum(widths) + _SEPARATOR * (len(columns) - 1) - width
    for i in sorted(
        (i for i, c in enumerate(columns) if c.shrink), key=lambda i: columns[i].shrink
    ):
        if excess <= 0:
            break
        floor = max(columns[i].min_width, len(columns[i].header))
        cut = min(excess, max(widths[i] - floor, 0))
        widths[i] -= cut
        excess -= cut
    return [
        [
            truncate(
                cell,
                widths[i],
                ellipsis,
                keep_end=columns[i].key in ("output", "outputs"),
            )
            for i, cell in enumerate(row)
        ]
        for row in rows
    ]


_STATE_COLORS = {"COMPLETED": "green", "RUNNING": "blue", "PENDING": "yellow"}


def _color_state(text: str, state: str | None) -> str:
    import click

    from .models import FINISHED_STATES

    if state in _STATE_COLORS:
        return click.style(text, fg=_STATE_COLORS[state])
    if state in FINISHED_STATES:
        return click.style(text, fg="red")
    if state in ("REQUEUED", "REQUEUE_HOLD", "SUSPENDED"):
        return click.style(text, fg="yellow")
    return text


def render_table(
    jobs: Sequence[Job],
    columns: Sequence[Column],
    *,
    requested: Iterable[str] = (),
    width: int | None = None,
    color: bool = False,
    header: bool = True,
    ellipsis: str = "…",
) -> str:
    """Render ``jobs`` as a table.

    Parameters
    ----------
    jobs
        The jobs, one per row.
    columns
        The columns, from :func:`select_columns`.
    requested
        Columns explicitly asked for: the others are hidden if empty for all jobs.
    width
        Truncate cells so the table fits this width; no truncation if ``None``.
    color
        Colour the state of jobs.
    header
        Show the header line.
    ellipsis
        Marks where cells were truncated.
    """
    requested = set(requested)
    rows = [[c.text(job) for c in columns] for job in jobs]
    shown = [
        i
        for i, c in enumerate(columns)
        if c.key in requested or any(row[i] for row in rows)
    ]
    columns = [columns[i] for i in shown]
    rows = [[row[i] for i in shown] for row in rows]
    if width is not None:
        rows = fit_to_width(rows, columns, width, ellipsis)
    widths = [
        max([len(c.header) if header else 0] + [len(row[i]) for row in rows])
        for i, c in enumerate(columns)
    ]

    def line(cells: Iterable[str]) -> str:
        return (" " * _SEPARATOR).join(cells).rstrip()

    def pad(text: str, i: int) -> str:
        if columns[i].align == "right":
            return text.rjust(widths[i])
        return text.ljust(widths[i])

    lines = []
    if header:
        lines.append(line(pad(c.header, i) for i, c in enumerate(columns)))
        lines.append(line("-" * w for w in widths))
    for row, job in zip(rows, jobs):
        cells = [pad(cell, i) for i, cell in enumerate(row)]
        if color:
            # colour after padding: escape codes have no width
            cells = [
                _color_state(cell, job.state) if c.key == "state" else cell
                for c, cell in zip(columns, cells)
            ]
        lines.append(line(cells))
    return "\n".join(lines)


def job_to_dict(job: Job, columns: Sequence[Column] | None = None) -> dict[str, Any]:
    """Return the JSON representation of ``job``, restricted to ``columns``
    (default: all).
    """
    columns = columns if columns is not None else list(COLUMNS.values())
    return {c.json_key: c.value(job) for c in columns}


def state_breakdown(jobs: Iterable[Job]) -> str:
    """Count jobs by state, e.g. ``2 running, 1 pending``, most frequent first."""
    counts = Counter((job.state or "UNKNOWN").lower() for job in jobs)
    return ", ".join(
        f"{n} {s}" for s, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    )


def summary_line(jobs: Sequence[Job]) -> str:
    """Return a one-line summary, e.g. ``3 jobs: 2 running, 1 pending``."""
    plural = "" if len(jobs) == 1 else "s"
    return f"{len(jobs)} job{plural}: {state_breakdown(jobs)}"
