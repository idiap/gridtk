from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gridtk.gridtk import Job, JobManager, update_job_statuses

# Setup for Database tests
# @pytest.fixture
# def engine():
#     return create_engine("sqlite:///:memory:")


# @pytest.fixture
# def session(engine):
#     from gridtk.gridtk import Base  # Assuming Base is in your script

#     Base.metadata.create_all(engine)
#     Session = sessionmaker(bind=engine)
#     return Session()


@pytest.fixture
def job_manager(tmp_path):
    database_path = tmp_path / "jobs.sql3"
    logs_dir = tmp_path / "logs"
    return JobManager(database=database_path, logs_dir=logs_dir)


@pytest.fixture
def batch_script(tmp_path):
    path = tmp_path / "hello_world.sh"
    path.write_text('#!/bin/bash\necho "Hello, World!"')
    return str(path)


# Test JobManager Initialization
def test_job_manager_init(job_manager):
    assert job_manager.database.exists()
    assert job_manager.logs_dir.is_dir()


def check_output_side_effect(*args, **kwargs):
    if "sbatch" in args[0]:
        return "Submitted batch job 12345\n"
    elif "scontrol" in args[0]:
        return '{"jobs": [{"job_id": "12345", "standard_output": "/path/to/output", "standard_error": "/path/to/error", "array_job_id": {"number": 0}}]}'
    elif "sacct" in args[0]:
        # Simulate sacct output for job status check
        return '{"jobs": [{"job_id": "12345", "state": "RUNNING"}]}'
    raise ValueError("Unhandled command")


# Test Job Submission
@patch("subprocess.check_call")
def test_submit_job(mock_check_output, job_manager, batch_script):
    mock_check_output.side_effect = check_output_side_effect
    # with job_manager.session as s:
    for job_id, command in [
        (1, ["---", "echo", "Hello, World!"]),
        (2, ['--wrap="echo "Hello, World!""']),
        (3, [batch_script]),
    ]:
        job = job_manager.submit_job(
            name="test_job",
            command=command,
            output="test_job.out",
            error="test_job.err",
            dependencies={},
        )
        assert job.id == job_id
        # assert job_info["grid_id"] == 12345
        assert job.name == "test_job"
        assert job.output.read_text() == "Hello, World!\n"


# Test Job Update Status
def test_update_job_statuses():
    with patch("subprocess.check_output") as mock_check_output:
        mock_check_output.return_value = (
            '{"jobs": [{"job_id": "12345", "state": "COMPLETED"}]}'
        )
        status = update_job_statuses([12345])
        assert status[12345]["state"] == "COMPLETED"


# Test Job Cancel
@patch("subprocess.check_output")
def test_cancel_job(mock_check_output, job_manager, session):
    job = Job(name="test_cancel", command=["sleep", "10"])
    job.grid_id = 12345  # Mocking grid ID as if job was submitted
    session.add(job)
    session.commit()

    job_manager.delete_jobs(job_ids=[job.id])
    mock_check_output.assert_called_with(["scancel", "12345"])


# More tests can be added following similar structure for other methods

if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main())
