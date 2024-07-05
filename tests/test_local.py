# SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import pathlib
import shutil
import subprocess
import time

import gridtk.local

from gridtk.models import Job
from gridtk.script import jman


def test_local(tmp_path: pathlib.Path, datadir: pathlib.Path):
    # This test executes all commands of the local grid manager and asserts that everything is fine

    # first test, if the '/bin/bash' exists
    bash = "/bin/bash"
    assert os.path.exists(bash)

    jman_exec = shutil.which("jman")
    assert jman_exec

    scheduler_job = None

    try:
        # first, add some commands to the database
        script_1 = str(datadir / "test_script.sh")
        script_2 = str(datadir / "test_array.sh")
        rdir = str(datadir)

        # add a simple script that will write some information to the console
        jman.main(
            [
                shutil.which("jman"),
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_1",
                bash,
                script_1,
            ]
        )
        jman.main(
            [
                shutil.which("jman"),
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_2",
                "--dependencies",
                "1",
                "--parametric",
                "1-7:2",
                bash,
                script_2,
            ]
        )
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_3",
                "--dependencies",
                "1",
                "2",
                "--exec-dir",
                rdir,
                bash,
                "test_array.sh",
            ]
        )
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_1",
                "--repeat",
                "2",
                bash,
                script_1,
            ]
        )

        # check that the database was created successfully
        assert os.path.exists(str(tmp_path / "database.sql3"))

        # test that the list command works (should also work with the "default"
        # grid manager)
        jman.main(
            [
                jman_exec,
                "--database",
                str(tmp_path / "database.sql3"),
                "list",
                "--job-ids",
                "1",
            ]
        )
        jman.main(
            [
                jman_exec,
                "--database",
                str(tmp_path / "database.sql3"),
                "list",
                "--job-ids",
                "2",
                "--print-array-jobs",
                "--print-dependencies",
                "--print-times",
            ]
        )
        jman.main(
            [
                jman_exec,
                "--database",
                str(tmp_path / "database.sql3"),
                "list",
                "--job-ids",
                "4-5",
                "--print-array-jobs",
                "--print-dependencies",
                "--print-times",
            ]
        )

        # get insight into the database
        job_manager = gridtk.local.JobManagerLocal(
            database=str(tmp_path / "database.sql3")
        )
        session = job_manager.lock()
        jobs = list(session.query(Job))
        assert len(jobs) == 5
        assert jobs[0].id == 1
        assert jobs[1].id == 2
        assert jobs[2].id == 3
        assert jobs[3].id == 4
        assert jobs[4].id == 5
        assert len(jobs[1].array) == 4
        assert jobs[0].status == "submitted"
        assert jobs[1].status == "submitted"
        assert jobs[2].status == "submitted"
        assert jobs[3].status == "submitted"
        assert jobs[4].status == "submitted"
        assert all(j.submit_time is not None for j in jobs)
        assert all(j.start_time is None for j in jobs)
        assert all(j.finish_time is None for j in jobs)
        assert all(j.submit_time is not None for j in jobs[1].array)
        assert all(j.start_time is None for j in jobs[1].array)
        assert all(j.finish_time is None for j in jobs[1].array)

        # check that the job dependencies are correct
        waiting = jobs[0].get_jobs_waiting_for_us()
        assert len(waiting) == 2
        assert waiting[0].id == 2
        assert waiting[1].id == 3
        waited = jobs[2].get_jobs_we_wait_for()
        assert len(waited) == 2
        assert waited[0].id == 1
        assert waited[1].id == 2

        # check dependencies for --repeat
        waiting = jobs[3].get_jobs_waiting_for_us()
        assert len(waiting) == 1
        assert waiting[0].id == 5
        waited = jobs[4].get_jobs_we_wait_for()
        assert len(waited) == 1
        assert waited[0].id == 4

        job_manager.unlock()

        # now, start the local execution of the job in a parallel job
        scheduler_job = subprocess.Popen(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "run-scheduler",
                "--sleep-time",
                "5",
                "--parallel",
                "2",
            ]
        )

        # sleep some time to assure that the scheduler was able to start the first job
        time.sleep(5)
        # ... and kill the scheduler
        scheduler_job.kill()
        scheduler_job = None

        # now, the first job needs to have status failure, and the second needs
        # to be queued
        session = job_manager.lock()
        jobs = list(session.query(Job))
        assert len(jobs) == 5
        if jobs[0].status in ("submitted", "queued", "executing"):
            # on slow machines, we don0t want the tests to fail, so we just skip
            job_manager.unlock()
            raise RuntimeError(
                "This machine seems to be quite slow in processing parallel jobs."
            )
        assert jobs[0].status == "failure"
        assert jobs[1].status == "queued"
        assert jobs[2].status == "waiting"
        assert jobs[0].start_time is not None
        assert jobs[0].finish_time is not None
        assert jobs[1].start_time is None
        assert jobs[1].finish_time is None
        assert jobs[2].start_time is None
        assert jobs[2].finish_time is None

        # the result files should already be there
        assert os.path.exists(jobs[0].std_out_file())
        assert os.path.exists(jobs[0].std_err_file())
        job_manager.unlock()

        # reset the job 1
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "resubmit",
                "--job-id",
                "1",
                "--running-jobs",
                "--overwrite-command",
                bash,
                script_1,
            ]
        )

        # now, start the local execution of the job in a parallel job
        scheduler_job = subprocess.Popen(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "run-scheduler",
                "--sleep-time",
                "5",
                "--parallel",
                "2",
            ]
        )

        # sleep some time to assure that the scheduler was able to finish the first and start the second job
        time.sleep(10)
        # ... and kill the scheduler
        scheduler_job.kill()
        scheduler_job = None

        # Job 1 and two array jobs of job two should be finished now, the other two still need to be queued
        session = job_manager.lock()
        jobs = list(session.query(Job))
        assert len(jobs) == 5
        if (
            jobs[0].status in ("queued", "executing")
            or jobs[1].status == "queued"
        ):
            # on slow machines, we don0t want the tests to fail, so we just skip
            job_manager.unlock()
            raise RuntimeError(
                "This machine seems to be quite slow in processing parallel jobs."
            )
        assert jobs[0].status == "failure"
        assert jobs[1].status == "executing"
        if (
            jobs[1].array[0].status == "executing"
            or jobs[1].array[1].status == "executing"
        ):
            # on slow machines, we don0t want the tests to fail, so we just skip
            job_manager.unlock()
            raise RuntimeError(
                "This machine seems to be quite slow in processing parallel jobs."
            )
        assert jobs[1].array[0].status == "failure"
        assert jobs[1].array[0].result == 1
        assert jobs[1].array[1].status == "success"
        assert jobs[1].array[1].result == 0
        assert len([a for a in jobs[1].array if a.status == "queued"]) == 2
        out_file = jobs[0].std_out_file()
        err_file = jobs[0].std_err_file()
        job_manager.unlock()

        # the result files of the first job should now be there
        assert os.path.isfile(out_file)
        assert os.path.isfile(err_file)
        assert (
            open(out_file).read().rstrip()
            == "This is a text message to std-out"
        )
        assert "This is a text message to std-err" in open(
            err_file
        ).read().split("\n")

        # resubmit all jobs
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "resubmit",
                "--running-jobs",
            ]
        )
        # check that the log files have been cleaned
        assert not os.path.exists(out_file)
        assert not os.path.exists(err_file)

        # ... but the log dir still exists
        assert os.path.exists(str(tmp_path / "logs"))

        # now, let the scheduler run all jobs, but this time in verbose mode
        scheduler_job = subprocess.Popen(
            [
                jman_exec,
                "--local",
                "-vv",
                "--database",
                str(tmp_path / "database.sql3"),
                "run-scheduler",
                "--sleep-time",
                "1",
                "--parallel",
                "2",
                "--die-when-finished",
            ]
        )
        # and wait for the job to finish (the timeout argument to Popen only exists from python 3.3 onwards)
        scheduler_job.wait()
        scheduler_job = None

        # check that all output files are generated again
        assert os.path.isfile(out_file)
        assert os.path.isfile(err_file)
        assert (
            open(out_file).read().rstrip()
            == "This is a text message to std-out"
        )
        assert "This is a text message to std-err" in open(
            err_file
        ).read().split("\n")

        # check that exactly four output and four error files have been created
        files = os.listdir(str(tmp_path / "logs"))
        assert len(files) == 16
        for i in range(1, 8, 2):
            assert "test_2.o2.%d" % i in files
            assert "test_2.e2.%d" % i in files

        # check that all array jobs are finished now
        session = job_manager.lock()
        jobs = list(session.query(Job))
        assert len(jobs) == 5
        assert jobs[1].status == "failure"
        assert jobs[1].array[0].status == "failure"
        assert jobs[1].array[0].result == 1
        for i in range(1, 4):
            assert jobs[1].array[i].status == "success"
            assert jobs[1].array[i].result == 0
        assert jobs[2].status == "success"
        assert jobs[2].result == 0

        assert all(j.submit_time is not None for j in jobs)
        assert all(j.start_time is not None for j in jobs)
        assert all(j.finish_time is not None for j in jobs)
        assert all(j.submit_time is not None for j in jobs[1].array)
        assert all(j.start_time is not None for j in jobs[1].array)
        assert all(j.finish_time is not None for j in jobs[1].array)

        job_manager.unlock()

        # test that the list command still works
        jman.main(
            [
                jman_exec,
                "--database",
                str(tmp_path / "database.sql3"),
                "list",
                "--print-array-jobs",
            ]
        )
        jman.main(
            [
                jman_exec,
                "--database",
                str(tmp_path / "database.sql3"),
                "list",
                "--long",
                "--print-array-jobs",
            ]
        )

        # test that the report command works
        jman.main(
            [jman_exec, "--database", str(tmp_path / "database.sql3"), "report"]
        )

        # clean-up
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "delete",
                "--job-ids",
                "1+4",
            ]
        )

        # check that the database and the log files are gone
        assert len(os.listdir(tmp_path)) == 0

        # add the scripts again, but this time with the --stop-on-failure option
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_1",
                "--stop-on-failure",
                bash,
                script_1,
            ]
        )
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_2",
                "--dependencies",
                "1",
                "--parametric",
                "1-7:2",
                "--stop-on-failure",
                bash,
                script_2,
            ]
        )
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "submit",
                "--log-dir",
                str(tmp_path / "logs"),
                "--name",
                "test_3",
                "--dependencies",
                "1",
                "2",
                "--exec-dir",
                rdir,
                "--stop-on-failure",
                bash,
                "test_array.sh",
            ]
        )

        # and execute them, but without writing the log files
        scheduler_job = subprocess.Popen(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "run-scheduler",
                "--sleep-time",
                "0.1",
                "--parallel",
                "2",
                "--die-when-finished",
                "--no-log-files",
            ]
        )
        # and wait for the job to finish (the timeout argument to Popen only exists from python 3.3 onwards)
        scheduler_job.wait()
        scheduler_job = None

        # assert that the log files are not there
        assert not os.path.isfile(out_file)
        assert not os.path.isfile(err_file)

        # check that all array jobs are finished now
        session = job_manager.lock()
        jobs = list(session.query(Job))
        assert len(jobs) == 3
        assert jobs[0].status == "failure"
        assert jobs[0].result == 255
        assert jobs[1].status == "failure"
        assert jobs[1].result is None
        assert jobs[2].status == "failure"
        assert jobs[2].result is None
        job_manager.unlock()

        # and clean up again
        jman.main(
            [
                jman_exec,
                "--local",
                "--database",
                str(tmp_path / "database.sql3"),
                "delete",
            ]
        )
        assert len(os.listdir(tmp_path)) == 0

    except KeyboardInterrupt:
        # make sure that the keyboard interrupt is captured and the mess is cleaned up (i.e. by calling tearDown)
        pass

    finally:
        if scheduler_job is not None:
            scheduler_job.kill()
