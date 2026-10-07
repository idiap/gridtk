# SPDX-FileCopyrightText: 2024 Idiap Research Institute <contact@idiap.ch>
# SPDX-FileContributor: Amir Mohammadi  <amir.mohammadi@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import stat
import subprocess
import traceback

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from click.testing import CliRunner

from gridtk.__main__ import cli
from gridtk.tools import (
    add_default_dep_type,
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


def _make_side_effect(calls):
    """Create a side_effect that returns empty output for squeue calls
    (simulating no active jobs) and returns values from `calls` for other
    commands (sacct, scancel, sbatch)."""
    it = iter(calls)

    def side_effect(*args, **kwargs):
        if args[0][0] == "squeue":
            return ""
        return next(it)

    return side_effect


def _pending_job_sacct_json(job_id):
    return json.dumps(
        _jobs_sacct_dict([job_id], "PENDING", "Unassigned", "None assigned")
    )


def _failed_job_sacct_json(*job_ids):
    return json.dumps(_jobs_sacct_dict(list(job_ids), "FAILED", "None", "node001"))


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


@pytest.mark.parametrize(
    ("dependencies", "expected"),
    [
        (None, None),
        ("", ""),
        ("5", "afterany:5"),
        ("5:6", "afterany:5:6"),
        ("5+10", "afterany:5+10"),
        ("afterok:5:6", "afterok:5:6"),
        ("5,afterok:6", "afterany:5,afterok:6"),
        ("afterok:5?6", "afterok:5?afterany:6"),
        ("singleton", "singleton"),
        ("slurm:5:6", "afterany:slurm:5:6"),
        ("afterok:slurm:5,slurm:6", "afterok:slurm:5,afterany:slurm:6"),
    ],
)
def test_add_default_dep_type(dependencies, expected):
    assert add_default_dep_type(dependencies) == expected


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
        # slurm ids are kept as they are
        (
            "afterok:20:slurm:1234567,after:slurm:5+10",
            [20],
            "afterok:1020:1234567,after:5+10",
        ),
    ]:
        result = job_ids_from_dep_str(dep_str)
        assert result == expected_result
        replaced_deps = replace_job_ids_in_dep_str(
            dep_str, {v: v + 1000 for v in result}
        )
        assert replaced_deps == expected_replaced


def test_replace_unknown_job_ids():
    from gridtk.tools import UnknownJobIdsError

    with pytest.raises(UnknownJobIdsError) as error:
        replace_job_ids_in_dep_str("afterok:1:2:9,afterany:8:9", {1: 1001})
    assert error.value.job_ids == [2, 9, 8]
    assert str(error.value) == "job(s) 2, 9, 8 not found in the job database"


def assert_click_runner_result(result, exit_code=0, exception_type=None):
    """Helper for asserting click runner results."""
    m = "Click command exited with code `{}' and exception:\n{}\nThe output was:\n{}"
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
def test_submit_with_env_vars(mock_check_output: Mock, runner):
    """Test that environment variables with GRIDTK_SUBMIT_ prefix are properly converted to CLI options."""
    mock_check_output.return_value = _sbatch_output(123456789)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["submit", "job.sh"],
            env={
                "GRIDTK_SUBMIT_MAIL_USER": "test@example.com",
                "GRIDTK_SUBMIT_MAIL_TYPE": "END",
                "GRIDTK_SUBMIT_PARTITION": "debug",
            },
        )

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
            "--mail-type",
            "END",
            "--mail-user",
            "test@example.com",
            "--partition",
            "debug",
            "job.sh",
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


def _headers(output):
    return output.splitlines()[0].split()


@patch("subprocess.check_output")
def test_list_jobs(mock_check_output, runner):
    # override shutil.get_terminal_size to return a fixed size with COLUMNS=80
    with runner.isolated_filesystem(), runner.isolation(env={"COLUMNS": "80"}):
        # test when there are no jobs
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        assert "No jobs were found." in result.output

        # test when there are jobs
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        mock_check_output.assert_called_with(
            ["sacct", "-j", str(submit_job_id), "--json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        # compact overview: empty columns (ELAPSED) are hidden, and there is no
        # summary line when the output is not a terminal
        assert _headers(result.output) == ["ID", "SLURM", "STATE", "NAME", "NODES"]
        assert result.output.splitlines()[2].split() == [
            "1",
            str(submit_job_id),
            "PENDING",
            "gridtk",
            "(Unassigned)",
        ]
        assert len(result.output.splitlines()) == 3

        # more columns with -v and -vv (empty ones stay hidden)
        result = runner.invoke(cli, ["list", "-v"])
        assert_click_runner_result(result)
        assert _headers(result.output)[-2:] == ["EXIT", "OUTPUT"]
        result = runner.invoke(cli, ["list", "-vv"])
        assert_click_runner_result(result)
        assert _headers(result.output)[-1] == "COMMAND"
        # values are not truncated when the output is not a terminal
        assert "gridtk submit --wrap sleep\n" in result.output
        assert "logs/gridtk.9876543.out " in result.output

        # forced truncation fits the terminal and keeps the end of log paths
        result = runner.invoke(cli, ["list", "-vv", "--truncate"])
        assert_click_runner_result(result)
        assert all(len(line) <= 80 for line in result.output.splitlines())
        assert "9876543.out" in result.output
        assert "gridtk submit --wrap sleep" not in result.output

        # deprecated --wrap shows full values
        result = runner.invoke(cli, ["list", "-vv", "--wrap"])
        assert_click_runner_result(result)
        assert "--wrap is deprecated" in result.output
        assert "gridtk submit --wrap sleep\n" in result.output

        # select columns
        result = runner.invoke(cli, ["list", "-o", "id,state"])
        assert_click_runner_result(result)
        assert _headers(result.output) == ["ID", "STATE"]
        result = runner.invoke(cli, ["list", "-o", "+command,-nodes,-slurm-id"])
        assert_click_runner_result(result)
        assert _headers(result.output) == ["ID", "STATE", "NAME", "COMMAND"]
        result = runner.invoke(cli, ["list", "-o", "id,foo"])
        assert result.exit_code == 2
        assert "Unknown column 'foo'" in result.output

        # explicitly requested columns are shown even if empty
        result = runner.invoke(cli, ["list", "-o", "id,deps"])
        assert_click_runner_result(result)
        assert _headers(result.output) == ["ID", "DEPS"]

        # shell-friendly outputs
        result = runner.invoke(cli, ["list", "-q"])
        assert_click_runner_result(result)
        assert result.output == "1\n"
        result = runner.invoke(cli, ["list", "--no-header", "-o", "id,name"])
        assert_click_runner_result(result)
        assert result.output.split() == ["1", "gridtk"]
        result = runner.invoke(cli, ["list", "--summary"])
        assert_click_runner_result(result)
        assert result.output.splitlines()[-1] == "1 job: 1 pending"

        result = runner.invoke(cli, ["list", "--json", "-q"])
        assert result.exit_code == 2


@patch("subprocess.check_output")
def test_list_jobs_timing_from_squeue(mock_check_output, runner):
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        mock_check_output.return_value = (
            "1000|RUNNING|None|node001|1-02:03:04|2026-01-31T12:00:00\n"
        )
        result = runner.invoke(cli, ["list", "-vv"])
        assert_click_runner_result(result)
        assert "ELAPSED" in _headers(result.output)
        assert "1-02:03:04" in result.output
        assert "2026-01-31 12:00" in result.output

        result = runner.invoke(cli, ["list", "--json"])
        assert_click_runner_result(result)
        job = json.loads(result.output)[0]
        assert job["elapsed_seconds"] == 93784
        assert job["start"] == "2026-01-31T12:00:00"
        assert job["reason"] is None
        assert job["finished"] is False


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
            ["sacct", "-j", str(submit_job_id), "--json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )


@patch("subprocess.check_output")
def test_report_tail(mock_check_output, runner):
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        Path("logs/gridtk.1000.out").write_bytes(
            b"start\n" + b"".join(b"\r%d%%" % i for i in range(101)) + b"\nok\ndone\n"
        )
        mock_check_output.return_value = json.dumps(
            _jobs_sacct_dict([1000], "COMPLETED", "None", "node001")
        )
        result = runner.invoke(cli, ["report", "--tail", "2"])
        assert_click_runner_result(result)
        assert "[last 2 of 4 lines]\nok\ndone\n" in result.output
        assert "start" not in result.output

        result = runner.invoke(cli, ["report", "--json", "-n", "3"])
        assert_click_runner_result(result)
        log = json.loads(result.output)[0]["output_files"][0]
        assert log["content"] == "100%\nok\ndone\n"
        assert log["total_lines"] == 4
        assert log["truncated"] is True

        result = runner.invoke(cli, ["report", "--json", "--raw"])
        assert_click_runner_result(result)
        log = json.loads(result.output)[0]["output_files"][0]
        assert "\r50%\r" in log["content"]
        assert log["truncated"] is False


@patch("subprocess.check_output")
def test_squeue_array_jobs(mock_check_output):
    from gridtk.manager import job_statuses_from_squeue

    mock_check_output.return_value = (
        "7_1|RUNNING|None|n1|0:10|2026-01-31T12:00:00\n"
        "7_[2-3]|PENDING|(Resources)||0:00|N/A\n"
    )
    status = job_statuses_from_squeue([7])
    assert list(status) == [7]
    assert status[7]["state"]["current"] == ["RUNNING"]
    assert status[7]["time"]["elapsed"] == 10


def test_read_log(tmp_path):
    from gridtk.tools import read_log

    path = tmp_path / "log.out"
    path.write_bytes(b"a\r\nb\rc\r\n\rd\re\r\nlast")
    assert read_log(path) == ("a\nc\ne\nlast\n", 4)
    assert read_log(path, tail=1) == ("last\n", 4)
    assert read_log(path, tail=0) == ("", 4)
    assert read_log(path, collapse_cr=False, tail=2) == ("\rd\re\r\nlast\n", 4)


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [
        ("0:00", 0),
        ("1:02", 62),
        ("1:02:03", 3723),
        ("2-01:00:00", 176400),
        ("N/A", None),
        ("INVALID", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_slurm_duration(duration, seconds):
    from gridtk.tools import format_duration, parse_slurm_duration

    assert parse_slurm_duration(duration) == seconds
    if seconds is not None:
        assert parse_slurm_duration(format_duration(seconds)) == seconds


def test_compact_ranges():
    from gridtk.tools import compact_ranges

    assert compact_ranges([0, 1, 2, 5, 7, 8]) == "0-2,5,7-8"
    assert compact_ranges([]) == ""


def test_select_columns():
    from gridtk.listing import select_columns

    def keys(*args):
        return [c.key for c in select_columns(*args)[0]]

    assert keys(0) == ["id", "slurm_id", "state", "name", "nodes", "elapsed"]
    assert keys(0, "name,ID") == ["name", "id"]
    assert keys(1, "-deps,+command,reason")[-3:] == ["output", "command", "reason"]
    assert keys(0, "+job-id") == keys(0)
    with pytest.raises(ValueError, match="Unknown column 'nope'"):
        select_columns(0, "nope")


def test_fit_to_width():
    from gridtk.listing import COLUMNS, fit_to_width

    columns = [COLUMNS[k] for k in ("id", "name", "output", "command")]
    row = ["1", "a-long-job-name", "logs/a-long-job-name.12345.out", "x" * 40]
    # widths: 2 (the header "ID") + 15 + 30 + 40 + 3 * 2 separators = 93
    assert fit_to_width([row], columns, 93) == [row]
    # the command is cut first...
    fitted = fit_to_width([row], columns, 80)[0]
    assert fitted[:3] == row[:3]
    assert fitted[3] == "x" * 26 + "…"
    # ...then the output (from its start, to keep the Slurm job id), then the name
    # (there are no nodes here)
    fitted = fit_to_width([row], columns, 50)[0]
    assert fitted[3] == "x" * 15 + "…"
    assert fitted[2] == "…-name.12345.out"
    assert fitted[1] == "a-long-jo…"
    # fixed columns are never cut
    assert fit_to_width([row], columns, 10)[0][0] == "1"


def test_render_table():
    from gridtk.listing import render_table, select_columns, summary_line
    from gridtk.models import Job

    jobs = [
        Job(
            id=1,
            name="train",
            command=[],
            is_array_job=True,
            state="FAILED",
            exit_code="1",
            array_task_ids=[0, 1, 2, 5],
            grid_id=10,
            nodes="n1",
        ),
        Job(
            id=2,
            name="eval",
            command=[],
            is_array_job=False,
            state="COMPLETED",
            exit_code="0",
            grid_id=11,
            nodes="n2",
        ),
    ]
    columns, _ = select_columns(0, "id,state,name")
    lines = render_table(jobs, columns).splitlines()
    assert lines[2].split() == ["1", "FAILED", "(1)", "train[0-2,5]"]
    assert lines[3].split() == ["2", "COMPLETED", "eval"]
    colored = render_table(jobs, columns, color=True)
    assert "\x1b[31mFAILED (1)" in colored
    assert "\x1b[32mCOMPLETED" in colored
    assert summary_line(jobs) == "2 jobs: 1 completed, 1 failed"


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
        mock_check_output.side_effect = _make_side_effect(
            [
                json.dumps({"jobs": jobs}),
                "",  # for scancel
            ]
        )
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

        mock_check_output.side_effect = _make_side_effect(
            [
                _failed_job_sacct_json(submit_job_id),  # sacct
                "",  # scancel
                _sbatch_output(submit_job_id),  # sbatch
            ]
        )
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
def test_resubmit_no_jobs(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        # Job is in pending state (not failed), so default resubmit filters exclude it
        mock_check_output.side_effect = _make_side_effect(
            [
                _pending_job_sacct_json(submit_job_id),  # sacct
            ]
        )
        result = runner.invoke(cli, ["resubmit"])
        assert_click_runner_result(result)
        assert "No jobs were resubmitted." in result.output
        assert "default state filter" in result.output
        assert "--state all" in result.output


@patch("subprocess.check_output")
def test_list_after_resubmit_sacct_delay(mock_check_output, runner):
    """Test that gridtk list uses squeue (live state) over stale sacct data
    after a resubmit (issue #17)."""
    with runner.isolated_filesystem(), runner.isolation(env={"COLUMNS": "80"}):
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )

        # Resubmit: squeue returns empty (no active jobs), sacct shows FAILED,
        # scancel, sbatch gives new job id
        new_job_id = 1111111
        mock_check_output.side_effect = _make_side_effect(
            [
                _failed_job_sacct_json(submit_job_id),  # sacct for list_jobs
                "",  # scancel
                _sbatch_output(new_job_id),  # sbatch
            ]
        )
        result = runner.invoke(cli, ["resubmit"])
        assert_click_runner_result(result)
        assert "Resubmitted job 1" in result.output

        # Now list: squeue returns PENDING (live state), sacct not needed
        squeue_output = f"{new_job_id}|PENDING|Priority|"
        mock_check_output.return_value = squeue_output
        mock_check_output.side_effect = None
        result = runner.invoke(cli, ["list"])
        assert_click_runner_result(result)
        assert "PENDING" in result.output
        assert str(new_job_id) in result.output


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
                f"afterany:{first_grid_id}",
                "script.sh",
            ],
            text=True,
        )

        # test if dependent jobs get resubmitted too
        mock_check_output.side_effect = _make_side_effect(
            [
                _failed_job_sacct_json(first_grid_id, second_grid_id),  # sacct
                "",  # scancel
                _sbatch_output(first_grid_id + 10),  # sbatch
                "",  # scancel
                _sbatch_output(second_grid_id + 10),  # sbatch
            ]
        )
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
                f"afterany:{first_grid_id + 10}",
                "script.sh",
            ],
            text=True,
        )

        # test if dependent jobs get deleted too
        mock_check_output.side_effect = _make_side_effect(
            [
                _failed_job_sacct_json(
                    first_grid_id + 10, second_grid_id + 10
                ),  # sacct
                "",  # scancel
                "",  # scancel
            ]
        )
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
        assert_click_runner_result(result, exit_code=2, exception_type=SystemExit)
        assert "job(s) 0 not found in jobs.sql3" in result.output

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
                f"afterany:{first_grid_id}",
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
                f"afterany:{first_grid_id + 10}:{second_grid_id + 10}",
                "script.sh",
            ],
            text=True,
        )

        # now delete all the jobs
        mock_check_output.side_effect = _make_side_effect(
            [
                _failed_job_sacct_json(
                    first_grid_id,
                    second_grid_id,
                    first_grid_id + 10,
                    second_grid_id + 10,
                    third_grid_id + 10,
                ),  # sacct
                "",  # scancel 1
                "",  # scancel 2
                "",  # scancel 3
                "",  # scancel 4
                "",  # scancel 5
            ]
        )
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


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        ("afterok:2,afterany:1", "afterok:1001,afterany:1000"),
        ("afterok:2?after:1+5", "afterok:1001?after:1000+5"),
        ("afterok:1,afterany:1", "afterok:1000,afterany:1000"),
        # slurm ids of jobs submitted outside gridtk
        ("afterok:1:slurm:777", "afterok:1000:777"),
        ("slurm:777", "afterany:777"),
        ("after:slurm:777+5?afterok:2", "after:777+5?afterok:1001"),
    ],
)
@patch("subprocess.check_output")
def test_submit_dependency_keeps_order(mock_check_output, runner, dependency, expected):
    """Each job id of the dependency is replaced by the slurm id of that job,
    whatever the order of the ids or how often they appear."""
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1001)
        mock_check_output.return_value = _sbatch_output(1002)
        result = runner.invoke(cli, ["submit", "--dependency", dependency, "job.sh"])
        assert_click_runner_result(result)
        args = mock_check_output.call_args.args[0]
        assert args[args.index("--dependency") + 1] == expected


@patch("subprocess.check_output")
def test_submit_unknown_dependency(mock_check_output, runner):
    """Unknown local ids are named, nothing is submitted, and slurm ids do not
    become local dependencies."""
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["submit", "--dependency", "5", "job.sh"])
        assert result.exit_code == 2
        assert not Path("jobs.sql3").exists()  # no empty database left behind

        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        calls = mock_check_output.call_count
        result = runner.invoke(
            cli, ["submit", "--dependency", "afterok:1:1234567,afterany:7", "job.sh"]
        )
        assert result.exit_code == 2
        assert (
            "job(s) 1234567, 7 not found in jobs.sql3 (--dependency takes local "
            "ids; write slurm ids as slurm:<id>, e.g. afterok:slurm:1234567)"
        ) in result.output
        assert mock_check_output.call_count == calls  # sbatch was not called

        mock_check_output.return_value = _sbatch_output(1001)
        result = runner.invoke(
            cli, ["submit", "--dependency", "afterok:1:slurm:1234567", "job.sh"]
        )
        assert_click_runner_result(result)
        mock_check_output.side_effect = _make_side_effect(
            [_failed_job_sacct_json(1000, 1001)]
        )
        result = runner.invoke(cli, ["list", "--json", "-o", "id,deps"])
        assert_click_runner_result(result)
        assert json.loads(result.output)[1] == {"job_id": 2, "dependencies": [1]}


@patch("subprocess.check_output")
def test_resubmit_deleted_dependency(mock_check_output, runner):
    """Resubmitting a job whose dependency was deleted fails before cancelling
    anything."""
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        mock_check_output.return_value = _sbatch_output(1001)
        result = runner.invoke(cli, ["submit", "--dependency", "1", "job.sh"])
        assert_click_runner_result(result)
        mock_check_output.side_effect = _make_side_effect(
            [_failed_job_sacct_json(1000, 1001), ""]  # sacct, scancel
        )
        result = runner.invoke(cli, ["delete", "-j", "1"])
        assert_click_runner_result(result)

        mock_check_output.side_effect = _make_side_effect(
            [_failed_job_sacct_json(1001)]
        )
        result = runner.invoke(cli, ["resubmit", "-j", "2"])
        assert result.exit_code == 1
        assert "job 2 depends on job(s) 1, which are no longer in jobs.sql3" in (
            result.output
        )
        commands = [call.args[0][0] for call in mock_check_output.call_args_list]
        assert commands[-1] == "sacct"  # neither scancel nor sbatch


@pytest.mark.parametrize(
    ("dependency", "dep_type"), [("1", "afterany"), ("afterok:1", "afterok")]
)
@patch("subprocess.check_output")
def test_submit_repeat_after_dependency(
    mock_check_output, runner, dependency, dep_type
):
    """Each repeated job depends on the given job and on the previous repeats,
    with a dependency type sbatch accepts (a bare id means afterany)."""
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        mock_check_output.side_effect = [_sbatch_output(1001 + i) for i in range(3)]
        result = runner.invoke(
            cli, ["submit", "--dependency", dependency, "--repeat", "3", "job.sh"]
        )
        assert_click_runner_result(result)
        assert result.output == "2\n3\n4\n"
        dependencies = [
            call.args[0][call.args[0].index("--dependency") + 1]
            for call in mock_check_output.call_args_list[-3:]
        ]
        assert dependencies == [
            f"{dep_type}:1000",
            f"{dep_type}:1000:1001",
            f"{dep_type}:1000:1001:1002",
        ]


@patch("subprocess.check_output")
def test_list_json(mock_check_output, runner):
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )
        mock_check_output.return_value = _pending_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["list", "--json"])
        assert_click_runner_result(result)
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        job = data[0]
        assert job["job_id"] == 1
        assert job["slurm_id"] == submit_job_id
        assert job["name"] == "gridtk"
        assert job["state"] == "PENDING"
        assert str(job["exit_code"]) == "0"
        assert job["nodes"] == "Unassigned"
        assert "dependencies" in job
        assert "command" in job
        assert "output" in job
        # details not shown in the table
        assert job["reason"] == "Unassigned"
        assert job["finished"] is False
        assert job["outputs"] == ["logs/gridtk.9876543.out"]
        assert job["array_task_ids"] is None
        assert job["git_guard"] is None
        assert job["elapsed_seconds"] is None
        assert job["start"] is None

        # select keys
        result = runner.invoke(cli, ["list", "--json", "-o", "id,state,exit_code"])
        assert_click_runner_result(result)
        assert json.loads(result.output) == [
            {"job_id": 1, "state": "PENDING", "exit_code": "0"}
        ]
        result = runner.invoke(cli, ["list", "--json", "-o", "-command"])
        assert_click_runner_result(result)
        assert "command" not in json.loads(result.output)[0]
        assert "outputs" in json.loads(result.output)[0]


@patch("subprocess.check_output")
def test_submit_json(mock_check_output, runner):
    mock_check_output.return_value = _sbatch_output(123456789)
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["submit", "--json", "--wrap=hostname"])
        assert_click_runner_result(result)
        data = json.loads(result.output)
        assert data["job_id"] == 1
        assert data["slurm_id"] == 123456789
        assert data["name"] == "gridtk"


@patch("subprocess.check_output")
def test_wait_command(mock_check_output, runner):
    # Test wait with COMPLETED job (exit code 0)
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )
        mock_check_output.return_value = json.dumps(
            _jobs_sacct_dict([submit_job_id], "COMPLETED", "None", "node001")
        )
        result = runner.invoke(cli, ["wait"])
        assert_click_runner_result(result)
        assert "Job 1: COMPLETED" in result.output

    # Test wait with FAILED job (exit code 1)
    with runner.isolated_filesystem():
        submit_job_id = 9876543
        mock_check_output.side_effect = None
        _submit_job(
            runner=runner, mock_check_output=mock_check_output, job_id=submit_job_id
        )
        mock_check_output.return_value = _failed_job_sacct_json(submit_job_id)
        result = runner.invoke(cli, ["wait"])
        assert_click_runner_result(result, exit_code=1)
        assert "Job 1: FAILED" in result.output


def _sacct_record(job_id, state, return_code, signal=0, derived=0):
    """Return a ``sacct --json`` job record with separate exit codes."""
    return {
        "job_id": job_id,
        "state": {"current": [state], "reason": "None"},
        "nodes": "node001",
        "exit_code": {
            "return_code": {"set": True, "number": return_code},
            "signal": {"id": {"set": bool(signal), "number": signal}},
        },
        "derived_exit_code": {
            "return_code": {"set": True, "number": derived},
            "signal": {"id": {"set": False, "number": 0}},
        },
    }


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        # the batch script failed, no srun step (derived exit code stays 0)
        (_sacct_record(1, "FAILED", 75), "75"),
        # killed by a signal (e.g. scancel -s KILL)
        (_sacct_record(1, "CANCELLED", 0, signal=9), "0:9"),
        (_sacct_record(1, "COMPLETED", 0), "0"),
        # older sacct without exit_code
        ({"derived_exit_code": {"return_code": {"number": 2}}}, "2"),
        # squeue reports no exit code
        ({}, "0"),
    ],
)
def test_exit_code_from_status(record, expected):
    from gridtk.models import exit_code_from_status

    assert exit_code_from_status(record) == expected


@pytest.mark.parametrize(
    ("exit_code", "expected"), [("75:0", "75"), ("0:15", "0:15"), ("0:0", "0")]
)
def test_exit_code_from_scontrol(exit_code, expected):
    from gridtk.manager import parse_scontrol_output
    from gridtk.models import exit_code_from_status

    output = f"JobId=1 JobState=FAILED Reason=None ExitCode={exit_code} NodeList=n1"
    assert exit_code_from_status(parse_scontrol_output(output)) == expected


@patch("subprocess.check_output")
def test_list_shows_batch_exit_code(mock_check_output, runner):
    """The exit code of the batch script is shown, not the derived one of the
    job steps, which is 0 for jobs without ``srun``."""
    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        mock_check_output.side_effect = _make_side_effect(
            [json.dumps({"jobs": [_sacct_record(1000, "FAILED", 75)]})]
        )
        result = runner.invoke(cli, ["list", "--json"])
        assert_click_runner_result(result)
        job = json.loads(result.output)[0]
        assert job["state"] == "FAILED"
        assert str(job["exit_code"]) == "75"


@patch("subprocess.check_output")
def test_list_reads_exit_code_of_jobs_finished_in_squeue(mock_check_output, runner):
    """Slurm keeps finished jobs in squeue for a while, without exit code: gridtk
    reads those from sacct, and keeps squeue's state if sacct lacks them."""
    replies = {"squeue": "1000|FAILED|NonZeroExitCode|node001\n"}

    def side_effect(command, **kwargs):
        return replies[command[0]]

    with runner.isolated_filesystem():
        _submit_job(runner=runner, mock_check_output=mock_check_output, job_id=1000)
        mock_check_output.side_effect = side_effect

        replies["sacct"] = json.dumps({"jobs": [_sacct_record(1000, "FAILED", 75)]})
        result = runner.invoke(cli, ["list", "--json"])
        assert_click_runner_result(result)
        assert str(json.loads(result.output)[0]["exit_code"]) == "75"
        assert mock_check_output.call_args_list[-1].args[0][0] == "sacct"

        replies["sacct"] = json.dumps({"jobs": []})
        result = runner.invoke(cli, ["list", "--json"])
        assert_click_runner_result(result)
        assert json.loads(result.output)[0]["state"] == "FAILED"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main())
