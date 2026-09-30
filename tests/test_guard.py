# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Andre Anjos <andre.anjos@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the git guard."""

import json
import os
import subprocess

from pathlib import Path
from unittest.mock import patch

import pytest

from click.testing import CliRunner

from gridtk import guard
from gridtk.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=gridtk",
            "-c",
            "user.email=gridtk@example.com",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_repo(path: Path) -> Path:
    """Create a git repository with one committed file and return its root."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "code.py").write_text("print('v1')\n")
    # gridtk's own files must be ignored, or they make the tree dirty; the CLI tests
    # run inside a temporary sub-directory of the repository
    (path / ".gitignore").write_text("jobs.sql3\nlogs/\ntmp*/\n")
    _git(path, "add", "code.py", ".gitignore")
    _git(path, "commit", "-q", "-m", "v1")
    return Path(_git(path, "rev-parse", "--show-toplevel"))


def _sacct_json(*grid_ids: int, state: str = "PENDING") -> str:
    """Return a ``sacct --json`` reply listing ``grid_ids`` in ``state``."""
    return json.dumps(
        {
            "jobs": [
                {
                    "job_id": grid_id,
                    "state": {"current": [state], "reason": "Unassigned"},
                    "nodes": "None assigned",
                    "derived_exit_code": {
                        "status": ["SUCCESS"],
                        "return_code": {"number": 0},
                    },
                }
                for grid_id in grid_ids
            ]
        }
    )


def _slurm_replies(*replies: str):
    """Side effect answering ``squeue`` with no jobs and other commands in turn."""
    it = iter(replies)

    def side_effect(*args, **kwargs):
        if args[0][0] == "squeue":
            return ""
        return next(it)

    return side_effect


def _run_guard(state: guard.RepositoryState) -> int:
    """Run the bash guard for ``state`` followed by a no-op and return its exit code."""
    script = "#!/bin/bash\n" + state.guard_script() + "true\n"
    return subprocess.run(["bash", "-c", script]).returncode


def test_repository_state_and_bash_guard_agree(tmp_path):
    repo = _make_repo(tmp_path / "repo")

    state = guard.repository_state(repo)
    assert state.repo == repo
    assert state.head == _git(repo, "rev-parse", "HEAD")
    assert not state.is_dirty
    assert _run_guard(state) == 0

    # a tracked change trips the guard
    (repo / "code.py").write_text("print('v2')\n")
    assert _run_guard(state) == guard.GUARD_EXIT_CODE
    dirty = guard.repository_state(repo)
    assert dirty.is_dirty
    assert dirty.diff_sha256 != state.diff_sha256
    assert _run_guard(dirty) == 0

    # so does a new untracked file
    (repo / "notes.txt").write_text("todo\n")
    assert _run_guard(dirty) == guard.GUARD_EXIT_CODE
    assert _run_guard(guard.repository_state(repo)) == 0

    # and a new commit
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "v2")
    assert _run_guard(dirty) == guard.GUARD_EXIT_CODE
    committed = guard.repository_state(repo)
    assert committed.head != state.head
    assert not committed.is_dirty
    assert _run_guard(committed) == 0

    # the guard can be switched off in the job environment
    assert (
        subprocess.run(
            ["bash", "-c", "#!/bin/bash\n" + state.guard_script() + "true\n"],
            env={**os.environ, "GRIDTK_GIT_GUARD": "0"},
        ).returncode
        == 0
    )


def test_repository_root_outside_repository(tmp_path):
    with pytest.raises(RuntimeError, match="not inside a git repository"):
        guard.repository_root(tmp_path)


@patch("subprocess.check_output")
def test_submit_git_guard_records_state(mock_check_output, runner, tmp_path):
    repo = _make_repo(tmp_path / "repo")
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=repo):
        result = runner.invoke(cli, ["submit", "--git-guard", "---", "hostname"])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "1"

        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report", "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)[0]
        head = _git(repo, "rev-parse", "HEAD")
        assert report["git_guard"]["repo"] == str(repo)
        assert report["git_guard"]["head"] == head
        assert report["git_guard"]["is_dirty"] is False

        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report"])
        assert result.exit_code == 0, result.output
        assert f"Git guard: {repo} @ {head[:12]} (clean)" in result.output
        assert "gridtk git guard" in result.output
        assert "hostname" in result.output


@patch("subprocess.check_output")
def test_submit_without_git_guard_records_nothing(mock_check_output, runner, tmp_path):
    repo = _make_repo(tmp_path / "repo")
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=repo):
        result = runner.invoke(cli, ["submit", "---", "hostname"])
        assert result.exit_code == 0, result.output
        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)[0]["git_guard"] is None
        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report"])
        assert "Git guard" not in result.output
        assert "gridtk git guard" not in result.output


@pytest.mark.parametrize("separate", [True, False])
@patch("subprocess.check_output")
def test_submit_git_guard_on_another_repository(
    mock_check_output, runner, tmp_path, separate
):
    # jobs are submitted from one folder (holding jobs.sql3 and logs/) and pinned to
    # another repository, e.g. a git worktree of a branch
    other = _make_repo(tmp_path / "other")
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        option = ["--git-guard", str(other)] if separate else [f"--git-guard={other}"]
        result = runner.invoke(cli, ["submit", *option, "---", "hostname"])
        assert result.exit_code == 0, result.output

        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report", "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)[0]
        assert report["git_guard"]["repo"] == str(other)
        assert report["git_guard"]["head"] == _git(other, "rev-parse", "HEAD")


@patch("subprocess.check_output")
def test_submit_no_git_guard_overrides_default(mock_check_output, runner, tmp_path):
    repo = _make_repo(tmp_path / "repo")
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=repo):
        result = runner.invoke(
            cli,
            ["submit", "--no-git-guard", "---", "hostname"],
            env={"GRIDTK_SUBMIT_GIT_GUARD": "."},
        )
        assert result.exit_code == 0, result.output
        mock_check_output.side_effect = _slurm_replies(_sacct_json(1000))
        result = runner.invoke(cli, ["report", "--json"])
        assert json.loads(result.output)[0]["git_guard"] is None


def test_submit_git_guard_requires_triple_dash(runner, tmp_path):
    repo = _make_repo(tmp_path / "repo")
    with runner.isolated_filesystem(temp_dir=repo):
        Path("job.sh").write_text("#!/bin/bash\nhostname\n")
        result = runner.invoke(cli, ["submit", "--git-guard", "job.sh"])
        assert result.exit_code == 2
        assert "requires the command form" in result.output


def test_submit_git_guard_outside_repository(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["submit", "--git-guard", "---", "hostname"])
        assert result.exit_code == 2
        assert "not inside a git repository" in result.output


@patch("subprocess.check_output")
def test_resubmit_pins_the_current_repository_state(
    mock_check_output, runner, tmp_path
):
    repo = _make_repo(tmp_path / "repo")
    first_head = _git(repo, "rev-parse", "HEAD")
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=repo):
        result = runner.invoke(cli, ["submit", "--git-guard", "---", "hostname"])
        assert result.exit_code == 0, result.output

        (repo / "code.py").write_text("print('v2')\n")
        _git(repo, "commit", "-q", "-am", "v2")
        second_head = _git(repo, "rev-parse", "HEAD")
        assert second_head != first_head

        # sacct (status update), scancel, then sbatch for the resubmission
        mock_check_output.side_effect = _slurm_replies(
            _sacct_json(1000, state="FAILED"), "", "Submitted batch job 1001\n"
        )
        result = runner.invoke(cli, ["resubmit", "-j", "1", "-s", "ALL"])
        assert result.exit_code == 0, result.output

        mock_check_output.side_effect = _slurm_replies(_sacct_json(1001))
        result = runner.invoke(cli, ["report", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)[0]["git_guard"]["head"] == second_head


@patch("subprocess.check_output")
def test_database_without_git_guard_column_is_rejected(
    mock_check_output, runner, tmp_path
):
    mock_check_output.return_value = "Submitted batch job 1000\n"
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["submit", "---", "hostname"])
        assert result.exit_code == 0, result.output

        # simulate a database written by a gridtk version without the column
        import sqlite3

        connection = sqlite3.connect("jobs.sql3")
        connection.execute("ALTER TABLE jobs DROP COLUMN git_guard")
        connection.commit()
        connection.close()

        for args in (["list", "-s", "ALL"], ["submit", "---", "hostname"]):
            result = runner.invoke(cli, args)
            assert result.exit_code != 0
            assert "Error:" in result.output
            assert "older version of gridtk" in result.output
            assert "jobs.git_guard" in result.output
            assert "Traceback" not in result.output
