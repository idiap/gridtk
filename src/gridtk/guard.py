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

import dataclasses
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


@dataclasses.dataclass(frozen=True)
class RepositoryState:
    """Fingerprint of a git repository at a given moment.

    Instances are created with :func:`repository_state` and stored on the job as a
    JSON object (see :meth:`to_dict` and :meth:`from_dict`).
    """

    repo: Path
    """Root of the repository."""

    head: str
    """Commit sha of ``HEAD``."""

    diff_sha256: str
    """sha256 of ``git diff HEAD`` (changes to tracked files)."""

    status_sha256: str
    """sha256 of ``git status --porcelain`` including untracked files."""

    @property
    def is_dirty(self) -> bool:
        """Whether the working tree differs from ``HEAD`` (untracked files included)."""
        return self.status_sha256 != _EMPTY_SHA256

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation (``is_dirty`` included)."""
        return {
            "repo": str(self.repo),
            "head": self.head,
            "diff_sha256": self.diff_sha256,
            "status_sha256": self.status_sha256,
            "is_dirty": self.is_dirty,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryState":
        """Rebuild an instance from the output of :meth:`to_dict`."""
        return cls(
            repo=Path(data["repo"]),
            head=data["head"],
            diff_sha256=data["diff_sha256"],
            status_sha256=data["status_sha256"],
        )

    def describe(self) -> str:
        """Return a one-line human-readable description of the state."""
        tree = "dirty" if self.is_dirty else "clean"
        return f"{self.repo} @ {self.head[:12]} ({tree})"

    def guard_script(self) -> str:
        """Return bash lines that verify the state and exit :data:`GUARD_EXIT_CODE`.

        The lines are meant to be placed before the user command in the job script.
        Setting ``GRIDTK_GIT_GUARD=0`` in the job environment skips the check.
        """
        repo = shlex.quote(str(self.repo))
        expected = f"{self.head} {self.diff_sha256} {self.status_sha256}"
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


def repository_state(repo: Path) -> RepositoryState:
    """Fingerprint the current state of a git repository.

    Parameters
    ----------
    repo
        Root of the repository (see :func:`repository_root`).
    """
    repo = Path(repo)
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    diff = _git(repo, "diff", "--no-color", "--no-ext-diff", "HEAD")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return RepositoryState(
        repo=repo,
        head=head,
        diff_sha256=hashlib.sha256(diff).hexdigest(),
        status_sha256=hashlib.sha256(status).hexdigest(),
    )
