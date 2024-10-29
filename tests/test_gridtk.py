# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import stat
import traceback

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from click.testing import CliRunner
from gridtk.__main__ import cli
from gridtk.tools import (
    job_ids_from_dep_str,
    parse_array_indexes,
    replace_job_ids_in_dep_str,
)


@pytest.fixture
def runner():
    return CliRunner()


def _sbatch_output(job_id):
    return f"Submitted batch job {job_id}\n"


def _submit_job(*, runner, mock_check_output, job_id):
    mock_check_output.return_value = _sbatch_output(job_id)
    result = runner.invoke(cli, ["submit", "--wrap=sleep"])
    assert_click_runner_result(result)
    return result


def _jobs_sacct_dict(job_ids, state, reason, nodes):
    job_list = []
    for job_id in job_ids:
        job = {
            "job_id": job_id,
            "state": {"current": [state], "reason": reason},
            "nodes": nodes,
            "derived_exit_code": {
                "status": ["SUCCESS"],
                "return_code": {
                    "number": 0,
                },
            },
        }
        job_list.append(job)

    return {"jobs": job_list}


def _pending_job_sacct_json(job_id):
    return json.dumps(
        _jobs_sacct_dict([job_id], "PENDING", "Unassigned", "None assigned")
    )


def _failed_job_sacct_json(job_id):
    return json.dumps(_jobs_sacct_dict([job_id], "FAILED", "None", "node001"))


def test_parse_array_indexes():
    # Simple range
    assert parse_array_indexes("0-15") == list(range(0, 16))

    # Multiple values (combination of single indexes and ranges)
    assert parse_array_indexes("0,6,16-32") == [0, 6] + list(range(16, 33))

    # Step function within a range
    assert parse_array_indexes("0-15:4") == [0, 4, 8, 12]

    # Maximum number of simultaneously running tasks (should ignore %)
    assert parse_array_indexes("0-15%4") == list(range(0, 16))

    # Combination of ranges and steps
    assert parse_array_indexes("0-4,10-20:5") == [0, 1, 2, 3, 4, 10, 15, 20]

    # Complex case with range, steps, and multiple values
    assert parse_array_indexes("0,2-6:2,10-12") == [0, 2, 4, 6, 10, 11, 12]

    # Minimum index value is 0
    assert parse_array_indexes("0,1,2-4") == [0, 1, 2, 3, 4]

    # Maximum index value one less than MaxArraySize (assuming MaxArraySize is 50)
    assert parse_array_indexes("45-49") == [45, 46, 47, 48, 49]

    # Mixed single indexes, ranges, and steps with %
    assert parse_array_indexes("0,2-8:2,10-14%3") == [0, 2, 4, 6, 8, 10, 11, 12, 13, 14]

    # Empty string should raise a ValueError
    with pytest.raises(ValueError):
        parse_array_indexes("")

    # Handling invalid step (should raise ValueError)
    with pytest.raises(ValueError):
        parse_array_indexes("1-5:a")

    # Non-integer segment (should raise ValueError)
    with pytest.raises(ValueError):
        parse_array_indexes("1,2,three")


def test_extract_job_ids_from_dep_str():
    """Test extract job ids from dependency string."""
    for dep_str, expected_result, expected_replaced in [
        (None, [], None),
        ("", [], ""),
        ("20", [20], "1020"),
        ("20,21", [20, 21], "1020,1021"),
        (
            "afterok:20:21:22,afterany:23:24:25:26",
            [20, 21, 22, 23, 24, 25, 26],
            "afterok:1020:1021:1022,afterany:1023:1024:1025:1026",
        ),
        (
            "after:20+5:21+5,after:23+10",
            [20, 21, 23],
            "after:1020+5:1021+5,after:1023+10",
        ),
        ("afterok:20:21?afterany:23", [20, 21, 23], "afterok:1020:1021?afterany:1023"),
        (
            "after:20+15:21+30?afterany:23",
            [20, 21, 23],
            "after:1020+15:1021+30?afterany:1023",
        ),
    ]:
        result = job_ids_from_dep_str(dep_str)
        assert result == expected_result
        replaced_deps = replace_job_ids_in_dep_str(dep_str, [v + 1000 for v in result])
        assert replaced_deps == expected_replaced


def assert_click_runner_result(result, exit_code=0, exception_type=None):
    """Helper for asserting click runner results."""
    m = "Click command exited with code `{}' and exception:\n{}" "\nThe output was:\n{}"
    exception = (
        "None"
        if result.exc_info is None
        else "".join(traceback.format_exception(*result.exc_info))
    )
    m = m.format(result.exit_code, exception, result.output)
    assert result.exit_code == exit_code, m
    if exit_code == 0:
        assert not result.exception, m
    if exception_type is not None:
        assert isinstance(result.exception, exception_type), m


@patch("subprocess.check_output")
def test_submit_bash_script(mock_check_output, runner):
    mock_check_output.return_value = _sbatch_output(123456789)
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["submit", "-J", "jobname", "my_script.sh"])

        assert_click_runner_result(result)
        assert "1" in result.output

        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "jobname",
                "--output",
                "logs/jobname.%j.out",
                "--error",
                "logs/jobname.%j.out",
                "my_script.sh",
            ],
            text=True,
        )


@patch("subprocess.check_output")
def test_submit_wrap(mock_check_output, runner):
    mock_check_output.return_value = _sbatch_output(123456789)
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["submit", "--wrap=hostname"])

        assert_click_runner_result(result)
        assert "1" in result.output

    mock_check_output.assert_called_with(
        [
            "sbatch",
            "--job-name",
            "gridtk",
            "--output",
            "logs/gridtk.%j.out",
            "--error",
            "logs/gridtk.%j.out",
            "--wrap",
            "hostname",
        ],
        text=True,
    )


@patch("subprocess.check_output")
def test_submit_triple_dash(mock_check_output: Mock, runner):
    mock_check_output.return_value = _sbatch_output(123456789)
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["submit", "---", "hostname"])

        assert_click_runner_result(result)
        assert "1" in result.output

    args = mock_check_output.call_args.args
    assert len(args) == 1
    assert args[0][:-1] == [
        "sbatch",
        "--job-name",
        "gridtk",
        "--output",
        "logs/gridtk.%j.out",
        "--error",
        "logs/gridtk.%j.out",
    ]
    assert mock_check_output.call_args.kwargs == {"text": True}


@patch("subprocess.check_output")
def test_list_jobs(mock_check_output, runner):
    # override shutil.get_terminal_size to return a fixed size with COLUMNS=80
    with runner.isolated_filesystem(), runner.isolation(env={"COLUMNS": "80"}):
        # test when there are no jobs
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        assert result.output == ""

        # test when there are jobs
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        assert str(submit_job_id) in result.output
        mock_check_output.assert_called_with(
            ["sacct", "-j", str(submit_job_id), "--json"], text=True
        )
        # full command
        assert "gridtk submit --wrap sleep\n" in result.output
        # full log file name
        assert "logs/gridtk.9876543.out " in result.output

        # test gridtk list --truncate
        result = runner.invoke(cli, ["list", "--truncate"])
        assert_click_runner_result(result)
        assert str(submit_job_id) in result.output
        mock_check_output.assert_called_with(
            ["sacct", "-j", str(submit_job_id), "--json"], text=True
        )
        # truncated command
        assert "gridtk sub..\n" in result.output
        # truncated log file name
        assert "logs/gridt.. " in result.output

        # test gridtk list --wrap
        result = runner.invoke(cli, ["list", "--wrap"])
        assert_click_runner_result(result)
        assert str(submit_job_id) in result.output
        mock_check_output.assert_called_with(
            ["sacct", "-j", str(submit_job_id), "--json"], text=True
        )
        # wraped command
        assert "gridtk" in result.output
        assert "submit" in result.output
        assert "--wrap" in result.output
        assert "sleep" in result.output
        # wraped log file name
        assert "logs/gridtk.9 " in result.output
        assert "876543.out " in result.output


@patch("subprocess.check_output")
def test_list_jobs_readonly_database(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )
        # Simulate a readonly database
        mock_check_output.side_effect = []
        Path("jobs.sql3").chmod(stat.S_IREAD)
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        # The job should be UNKNOWN because we can't query the slurm when the
        # database is read-only
        assert "UNKNOWN" in result.output


@patch("subprocess.check_output")
def test_report_job(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["report"])
        assert_click_runner_result(result)
        assert str(submit_job_id) in result.output
        assert result.output.startswith(
            "Job ID: 1\nName: gridtk\nState: PENDING (0)\nNodes: Unassigned\nSubmitted command: ['sbatch', '--job-name', 'gridtk'"
        )
        assert "Output file: /tmp/" in result.output
        mock_check_output.assert_called_with(
            ["sacct", "-j", str(submit_job_id), "--json"], text=True
        )


@patch("subprocess.check_output")
def test_stop_jobs(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["stop", "--name", "gridtk"])
        assert_click_runner_result(result)
        assert result.output == f"Stopped job 1 with slurm id {submit_job_id}\n"
        mock_check_output.assert_called_with(["scancel", str(submit_job_id)])


@patch("subprocess.check_output")
def test_delete_jobs(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["delete"])
        assert_click_runner_result(result)
        assert result.output == f"Deleted job 1 with slurm id {submit_job_id}\n"
        mock_check_output.assert_called_with(["scancel", str(submit_job_id)])

        # test if state filtering works
        submit_job_id_1 = 9876544
        _submit_job(
            runner=runner,
            mock_check_output=mock_check_output,
            job_id=submit_job_id_1,
        )
        submit_job_id_2 = submit_job_id_1 + 1
        _submit_job(
            runner=runner,
            mock_check_output=mock_check_output,
            job_id=submit_job_id_2,
        )
        jobs = [
            _jobs_sacct_dict([submit_job_id_1], "COMPLETED", "None", "node001")["jobs"][
                0
            ],
            _jobs_sacct_dict([submit_job_id_2], "TIMEOUT", "None", "node002")["jobs"][
                0
            ],
        ]
        mock_check_output.side_effect = [
            json.dumps({"jobs": jobs}),
            "",  # for scancel
        ]
        result = runner.invoke(cli, ["delete", "-s", "CD"])
        assert_click_runner_result(result)
        assert result.output == f"Deleted job 1 with slurm id {submit_job_id_1}\n"
        mock_check_output.assert_called_with(["scancel", str(submit_job_id_1)])


@patch("subprocess.check_output")
def test_resubmit_jobs(mock_check_output, runner):
    # this test might fail on NFS drives or Google Drive or Dropbox synced folders
    # see: https://stackoverflow.com/questions/29244788/error-disk-i-o-error-on-a-newly-created-database
    # see: https://stackoverflow.com/questions/47540607/disk-i-o-error-with-sqlite3-in-python-3-when-writing-to-a-database
    with runner.isolated_filesystem() as tmpdir:
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.side_effect = [
            _failed_job_sacct_json(submit_job_id),  # sacct
            "",  # scancel
            _sbatch_output(submit_job_id),  # sbatch
        ]
        result = runner.invoke(cli, ["resubmit"])
        assert_click_runner_result(result)
        assert result.output == "Resubmitted job 1\n"
        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "gridtk",
                "--output",
                f"{tmpdir}/logs/gridtk.%j.out",
                "--error",
                f"{tmpdir}/logs/gridtk.%j.out",
                "--wrap",
                "sleep",
            ],
            text=True,
        )


@patch("subprocess.check_output")
def test_submit_with_dependencies(mock_check_output, runner):
    with runner.isolated_filesystem() as tmpdir:
        first_grid_id = 1111
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=first_grid_id
        )

        second_grid_id = 1112
        mock_check_output.return_value = _sbatch_output(second_grid_id)
        result = runner.invoke(cli, ["submit", "--dependency", "1", "script.sh"])
        assert_click_runner_result(result)
        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "gridtk",
                "--output",
                "logs/gridtk.%j.out",
                "--error",
                "logs/gridtk.%j.out",
                "--dependency",
                f"{first_grid_id}",
                "script.sh",
            ],
            text=True,
        )

        # test if dependent jobs get resubmitted too
        mock_check_output.side_effect = [
            _failed_job_sacct_json(first_grid_id),  # sacct
            "",  # scancel
            _sbatch_output(first_grid_id + 10),  # sbatch
            "",  # scancel
            _sbatch_output(second_grid_id + 10),  # sbatch
        ]
        result = runner.invoke(cli, ["resubmit", "--jobs", "1", "--dependents"])
        assert_click_runner_result(result)
        assert result.output == "Resubmitted job 1\nResubmitted job 2\n"
        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "gridtk",
                "--output",
                f"{tmpdir}/logs/gridtk.%j.out",
                "--error",
                f"{tmpdir}/logs/gridtk.%j.out",
                "--dependency",
                str(first_grid_id + 10),
                "script.sh",
            ],
            text=True,
        )

        # test if dependent jobs get deleted too
        mock_check_output.side_effect = [
            _failed_job_sacct_json(first_grid_id + 10),  # sacct
            "",  # scancel
            "",  # scancel
        ]
        result = runner.invoke(cli, ["delete", "--jobs", "1", "--dependents"])
        assert_click_runner_result(result)
        assert (
            result.output
            == f"Deleted job 1 with slurm id {first_grid_id + 10}\nDeleted job 2 with slurm id {second_grid_id + 10}\n"
        )
        mock_check_output.assert_called_with(["scancel", str(second_grid_id + 10)])

        # what happens if you depend on job that doesn't exist?
        mock_check_output.return_value = _sbatch_output(second_grid_id)
        result = runner.invoke(cli, ["submit", "--dependency", "0", "script.sh"])
        assert_click_runner_result(result, exit_code=1, exception_type=ValueError)

        # test submit with --repeat 2
        mock_check_output.side_effect = [
            _sbatch_output(first_grid_id),
            _sbatch_output(second_grid_id),
        ]
        result = runner.invoke(cli, ["submit", "--repeat", "2", "script.sh"])
        assert_click_runner_result(result)
        assert result.output == "1\n2\n"
        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "gridtk",
                "--output",
                "logs/gridtk.%j.out",
                "--error",
                "logs/gridtk.%j.out",
                "--dependency",
                f"{first_grid_id}",
                "script.sh",
            ],
            text=True,
        )

        third_grid_id = first_grid_id + 2
        mock_check_output.side_effect = [
            _sbatch_output(first_grid_id + 10),
            _sbatch_output(second_grid_id + 10),
            _sbatch_output(third_grid_id + 10),
        ]
        result = runner.invoke(cli, ["submit", "--repeat", "3", "script.sh"])
        assert_click_runner_result(result)
        assert result.output == "3\n4\n5\n"
        mock_check_output.assert_called_with(
            [
                "sbatch",
                "--job-name",
                "gridtk",
                "--output",
                "logs/gridtk.%j.out",
                "--error",
                "logs/gridtk.%j.out",
                "--dependency",
                f"{first_grid_id + 10}:{second_grid_id + 10}",
                "script.sh",
            ],
            text=True,
        )

        # now delete all the jobs
        mock_check_output.side_effect = [
            _failed_job_sacct_json(first_grid_id),  # sacct
            "",  # scancel 1
            "",  # scancel 2
            "",  # scancel 3
            "",  # scancel 4
            "",  # scancel 5
        ]
        result = runner.invoke(cli, ["delete", "--dependents"])
        assert_click_runner_result(result)
        assert (
            result.output
            == f"""Deleted job 1 with slurm id {first_grid_id}
Deleted job 2 with slurm id {second_grid_id}
Deleted job 3 with slurm id {first_grid_id + 10}
Deleted job 4 with slurm id {second_grid_id + 10}
Deleted job 5 with slurm id {third_grid_id + 10}
"""
        )


# @patch("subprocess.check_output")
# def test_list_jobs_with_truncation(mock_check_output, runner):
#     with runner.isolated_filesystem():
#         submit_job_id = 9876543
#         _submit_job(
#             runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
#         )

#         mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
#         result = runner.invoke(cli, ["list"])
#         assert_click_runner_result(result)
#         assert str(submit_job_id) in result.output
#         assert "gridtk submit --wrap sleep" in result.output
#         # wraped log file name
#         assert "logs/gridtk.987 " in result.output
#         mock_check_output.assert_called_with(
#             ["sacct", "-j", str(submit_job_id), "--json"], text=True
#         )


# @patch("subprocess.check_output")
# def test_list_jobs_with_full_output(mock_check_output, runner):
#     with runner.isolated_filesystem():
#         submit_job_id = 9876543
#         _submit_job(
#             runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
#         )

#         mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
#         result = runner.invoke(cli, ["list", "--full-output"])
#         assert_click_runner_result(result)
#         assert str(submit_job_id) in result.output
#         assert "gridtk submit --wrap sleep" in result.output
#         assert "logs/gridtk.9876543.out" in result.output
#         mock_check_output.assert_called_with(
#             ["sacct", "-j", str(submit_job_id), "--json"], text=True
#         )


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main())
