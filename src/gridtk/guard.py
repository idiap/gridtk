# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Andre Anjos <andre.anjos@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pins a submission to the state of a git repository.

Slurm jobs frequently run code that is installed in *editable* mode from a working
copy.  Such a job imports whatever the working copy contains when it **starts**,
possibly hours after submission, so edits made in between silently change what the
job computes.  The guard captures a fingerprint of the repository at submission time
(HEAD, tracked changes and untracked files) and makes the generated job script
recompute it at start, aborting with :data:`GUARD_EXIT_CODE` when they differ.
"""

import hashlib
import shlex
import subprocess

from pathlib import Path
from typing import Any

GUARD_EXIT_CODE = 75
"""Exit code of a job whose repository changed after submission (``EX_TEMPFAIL``)."""

_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    """Run a git command in ``repo`` and return its raw standard output."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


def repository_root(path: Path) -> Path:
    """Return the root of the git repository containing ``path``.

    Raises
    ------
    RuntimeError
        If ``path`` is not inside a git working tree.
    """
    try:
        output = _git(Path(path), "rev-parse", "--show-toplevel")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"{path} is not inside a git repository") from e
    return Path(output.decode().strip())


def repository_state(repo: Path) -> dict[str, Any]:
    """Fingerprint the current state of a git repository.

    Parameters
    ----------
    repo
        Root of the repository (see :func:`repository_root`).

    Returns
    -------
    dict
        A JSON-serializable dictionary with the repository path (``repo``), the
        ``head`` commit sha, ``diff_sha256`` (sha256 of ``git diff HEAD``),
        ``status_sha256`` (sha256 of ``git status --porcelain`` including untracked
        files) and ``dirty`` (whether the working tree differs from ``HEAD``).
    """
    repo = Path(repo)
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    diff = _git(repo, "diff", "--no-color", "--no-ext-diff", "HEAD")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    diff_sha256 = hashlib.sha256(diff).hexdigest()
    status_sha256 = hashlib.sha256(status).hexdigest()
    return {
        "repo": str(repo),
        "head": head,
        "diff_sha256": diff_sha256,
        "status_sha256": status_sha256,
        "dirty": status_sha256 != _EMPTY_SHA256,
    }


def guard_script(state: dict[str, Any]) -> str:
    """Return bash lines that verify ``state`` and exit :data:`GUARD_EXIT_CODE`.

    The lines are meant to be placed before the user command in the job script.
    Setting ``GRIDTK_GIT_GUARD=0`` in the job environment skips the check.
    """
    repo = shlex.quote(state["repo"])
    expected = f"{state['head']} {state['diff_sha256']} {state['status_sha256']}"
    return f"""\
# gridtk git guard: abort if the repository changed since submission
if [ "${{GRIDTK_GIT_GUARD:-1}}" = "1" ]; then
  _gridtk_repo={repo}
  _gridtk_expected="{expected}"
  _gridtk_actual="$(git -C "$_gridtk_repo" rev-parse HEAD) \
$(git -C "$_gridtk_repo" diff --no-color --no-ext-diff HEAD | sha256sum | cut -d' ' -f1) \
$(git -C "$_gridtk_repo" status --porcelain=v1 --untracked-files=all | sha256sum | cut -d' ' -f1)"
  if [ "$_gridtk_actual" != "$_gridtk_expected" ]; then
    echo "gridtk: $_gridtk_repo changed since submission; aborting (exit {GUARD_EXIT_CODE})." >&2
    echo "  expected HEAD/diff/status: $_gridtk_expected" >&2
    echo "  actual   HEAD/diff/status: $_gridtk_actual" >&2
    exit {GUARD_EXIT_CODE}
  fi
fi
"""


def describe(state: dict[str, Any]) -> str:
    """Return a one-line human-readable description of a captured state."""
    tree = "dirty" if state["dirty"] else "clean"
    return f"{state['repo']} @ {state['head'][:12]} ({tree})"
