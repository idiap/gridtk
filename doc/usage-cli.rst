.. SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
..
.. SPDX-License-Identifier: GPL-3.0-or-later

.. _gridtk.usage_cli:

========================
 Command Line Interface
========================

This section explains the use of ``gridtk`` through its command-line interface
(CLI).


The Job Manager
===============

The central important CLI is ``jman``, the "job manager". This application can
be used to:

* submit jobs (with support for parametric/array jobs)
* probe for submitted jobs
* identify problems with submitted jobs
* cleanup logs from submitted jobs
* easily re-submit jobs if problems occur

``jman`` has a common set of parameters, which will be explained in the
next section.  Additionally, several commands can be issued, each of which has
its own set of options.  These commands will be explained afterwards.


Basic Job Manager Parameters
----------------------------

There are two versions of Job Managers: One that submits jobs to the SGE grid,
and one that submits jobs so that they are run in parallel on the local
machine.  By default, the SGE manager is engaged.  If you don't have access to
the SGE grid, or you want to submit locally, issue the ``jman --local`` (or
shortly ``jman -l``) command instead.

To keep track of the submitted jobs, a SQLite_ database is written.  This
database is by default called ``submitted.sql3``, and put in the current
directory. This can be changed using the ``jman --database`` (``jman -d``)
flag.

Normally, the Job Manager acts silently, and only errors are reported. To make
the application more verbose, you can use the ``--verbose`` (``-v``) option
several times, to increase the verbosity level to 1) WARNING, 2) INFO, 3)
DEBUG.


Submitting Jobs
---------------

To submit a job, the ``jman submit`` command is used. The simplest way to
submit a job to be run in the SGE grid is:

.. code:: sh

   jman -vv submit myscript.py

This command will create a SQLite database, submit the job to the grid and
register it in the database. To be more easily separable from other jobs in the
database, you can give your job a name:

.. code:: sh

   jman -vv submit -n [name] myscript.py

If the job requires certain machine specifications, you can add these (please
see the SGE manual for possible specifications of [key] and [value] pairs).
Please note the ``--`` option that separates specifications from the command:

.. code:: sh

   jman -vv submit -q [queue-name] -m [memory] --io-big -s [key1]=[value1] [key2]=[value2] -- myscript.py

To have jobs run in parallel, you can submit a parametric job.  Simply call:

.. code:: sh

   jman -vv submit -t 10 myscript.py

to run ``myscript.py`` 10 times in parallel.  Each of the parallel jobs will
have a different environment variable called ``SGE_TASK_ID``, which will range
from 1 to 10 in this case.  If your script can handle this environment
variable, it can actually execute 10 different tasks (switched by the value of
the variable itself).

Also, jobs with dependencies can be submitted.  When submitted to the grid,
each job has its own job identifier.  These job ids can be used to create
dependencies between the jobs (i.e., one job needs to finish before the next
one can be started):

.. code:: sh

   jman -vv submit -x [job_id_1] [job_id_2] -- myscript.py

In case the first job fails, it can automatically stop the depending jobs from
being executed.  Just submit jobs with the ``--stop-on-failure`` option.

.. note::

   The ``--stop-on-failure`` option is under development and might not work
   properly. Use this option with care.

Also, you can submit the same job several times in a way that each one will
depend on the last one. This is useful when for GPU training when your jobs
gets killed because you run out of time but you want to submit the same job
again.

.. code:: sh

   jman submit --repeat 5 -- myscript.py


While the jobs run, the output and error stream are captured in log files,
which are written into a ``logs`` directory. This directory can be changed by
specifying:

.. code:: sh

   jman -vv submit -l [log_dir]

.. note::

   When submitting jobs locally, by default the output and error streams are
   written to console and no log directory is created.  To get back the SGE
   grid logging behavior, please specify the log directory.  In this case,
   output and error streams are written into the log files **after** the job
   has finished.


If the SGE backend is used, ``--sge-extra-args`` or shortly ``-e`` allows you
to send extra arguments to ``qsub``.

.. code:: sh

   jman -vv submit -e="<sge_extra_args>"

For example, ``jman submit .. -e="-P project_name -l pytorch" -- ...`` will be
translated to ``qsub ... -P project_name -l pytorch -- ...``.

.. note::

   Note that extra options for qsub must be wrapped in single or double quotes
   **and** should attach to the ``-e`` option with an ``=`` sign, e.g. ``jman
   submit -e='-P project_name -l pytorch'``. Examples like ``jman submit -e '-P
   project_name -l pytorch'`` and ``jman submit -e -P project_name -l pytorch``
   will not work.

To avoid adding the same ``-e`` option each time you run ``jman submit``, you
may also change its default value via the :ref:`gridtk configuration file
<gridtk.config>`, by setting the variable ``sge-extra-args-default``:

.. code:: toml

   sge-extra-args-default = "-P myproject"

Then, if you do ``jman submit ...``, this will translate to ``qsub -P myproject
...``. This configuration only changes the default value, you still can provide
a new value by providing the ``-e`` option on the command-line.

Another (**recommended**) option is to always a prepend a string to this
option, via the :ref:`gridtk configuration file <gridtk.config>`, by setting
the variable ``sge-extra-args-prepend``:

.. code:: toml

   sge-extra-args-prepend = "-P myproject"

Then, if you do ``jman submit -e="-l pytorch"``, this will translate to
``qsub -P myproject -l pytorch`` and will work as expected.


Running Jobs Locally
--------------------

When jobs are submitted to the SGE grid, ``jman`` typically returns
immediately, as nothing gets really executed, but only scheduled. However, when
jobs are submitted locally, (using the ``--local`` option, see above), a local
scheduler, mimicking the SGE scheduler, needs to be run.  This is achieved by
issuing the command:

.. code:: sh

   jman -vv run-scheduler -p [parallel_jobs] -s [sleep_time]

This will start the scheduler in the daemon mode.  This will constantly monitor
the SQLite database and execute jobs after submission, starting every
``[sleep_time]`` second.  Use ``Ctrl-C`` to stop the scheduler (if jobs are
still running locally, they will automatically be stopped).

If you want to submit a list of jobs and have the scheduler to run the jobs and
stop afterward, simply use the ``--die-when-finished`` option.  Also, it is
possible to run only specific jobs (and array jobs), which can be specified
with the ``--j`` and ``--a`` option, respectively.


Probing for Jobs
----------------

To list the contents of the job database, you can use the ``jman list``
command.  This will show you the job-id, the queue, the current status, the
name and the command line of each job.  Since the database is automatically
updated when jobs finish, you can use the ``jman list`` again after some time.

Normally, long command lines are cut so that each job is listed in a single
line.  To get the full command line, please use the ``-vv`` option:

.. code:: sh

   jman -vv list

By default, array jobs are not listed, but the ``-a`` option changes this
behavior.  Usually, it is a good idea to combine the ``-a`` option with ``-j``,
which will list only the jobs of the given job id(s):

.. code:: sh

   jman -vv list -a -j [job_id_1] [job_id_2]

Note that the ``-j`` option is in general relatively smart. You can use it to
select a range of job ids, e.g., ``-j 1-4 6-8 10+2`` is the same as ``-j 1 2 3
4 6 7 8 10 11 12``.  In this case, please assert that there are no spaces
between job ids and the ``-`` and ``+`` separators. You cannot use both ``-``
and ``+`` in one part, i.e., something like ``-j 1-4+2`` will not work. If any
job id is specified, which is not available in the database, it will simply be
ignored, including job ids that are in the ranges.

Since version 1.3.0, ``gridtk`` also saves timing information about jobs, i.e.,
time stamps when jobs were submitted, started and finished.  You can use the
``-t`` option of ``jman ls`` to add the time stamps to the listing, which are
both written for jobs and parametric jobs (i.e., when using the ``-a`` option).


Submitting dependent jobs
-------------------------

Sometimes, the execution of one job might depend on the execution of another
job. ``jman`` can take care of this, simply by adding the id of the job that we
have to wait for:

.. code:: sh

   jman -vv submit --dependencies 6151645 -- /usr/bin/python myscript.py --help
   ... Added job '<Job: 3> : submitted -- /usr/bin/python myscript.py --help' to the database
   ... Submitted job '<Job: 6151647> : queued -- /usr/bin/python myscript.py --help' to the SGE grid.

Now, the new job will only be run after the first one finished.

.. note::

   Note the ``--`` between the list of dependencies and the command.


Inspecting log files
--------------------

When a job fails, the status will be ``failure``.  In this case, you might want
to know what happened.  As a first indicator, the exit code of the program is
reported as well.  Also, the output and error streams of the job are recorded
and can be seen using ``jman``.  E.g.:

.. code:: sh

   jman -vv report -j [job_id] -a [array_id]

will print the contents of the output and error log file from the job with the
desired ID (and only the array job with the given ID).

To report only the output or only the error logs, you can use the ``-o`` or
``-e`` option, respectively.  Hopefully, that helps in debugging the problem!


Re-submitting the job
---------------------

After correcting your code you might want to submit the same command line
again.  For this purpose, the ``jman resubmit`` command exists.  Simply
specify the job id(s) that you want to resubmit:

.. code:: sh

   jman -vv resubmit -j [job_id_1] [job_id_2]

This will clean up the old log files (if you didn't specify the ``--keep-logs``
option) and re-submit the job. If the submission is done in the grid the job
id(s) will change during this process.


Stopping a grid job
-------------------

In case you found an error in the code of a grid job that is currently
executing, you might want to kill the job in the grid.  For this purpose, you
can use the command:

.. code:: sh

   jman stop

The job is removed from the grid, but all log files are still available.  A
common use case is to stop the grid job, fix the bugs, and re-submit it.


Note about verbosity and time stamps
------------------------------------

For some jobs, it might be interesting to get the time stamps when the job has
started and when it has finished.  These time stamps are added to the log files
(usually the error log file) automatically, when you use the ``-vv`` option,
one when starting the process and one when it is finished.  However, there is a
difference between the ``SGE`` operation and the ``--local`` operation.  For
the ``SGE`` operation, you need to use the ``-vv`` option during the submission
or re-submission of a job.  In ``--local`` mode, the ``-vv`` flag during
execution (using ``--run-local-scheduler``) is used instead.

.. note::

   Why writing info logs the error log file, and not to the default output log
   file?  This is the default behavior of python's logging module.  All logs,
   independent of whether they are error, warning, info or debug logs are
   written to ``sys.stderr``, which in turn will be written into the error log
   files.


Cleaning up
-----------

After the job was successfully (or not) executed, you should clean up the
database using the ``jman delete`` command.  If not specified otherwise (i.e.,
using the ``--keep-logs`` option), this command will delete all jobs from the
database and delete the log files (including the log directory in case it is
empty), and remove the database as well.

Again, job ids and array ids can be specified to limit the deleted jobs with
the ``-j`` and ``-a`` option, respectively.  It is also possible to clean up
only those jobs (and array jobs) with a certain status. E.g. use:

.. code:: sh

   jman -vv delete -s success -j 10-20

to delete all jobs and the logs of all successfully finished jobs with job ids
from 10 to 20 from the database.


Other command line tools
========================

For convenience, we also provide additional command line tools, which
*transparently* wrap the equivalent SGE tools, and make the process of using
SGE at Idiap a bit easier (no need to execute ``SETSHELL grid``, if this
package is installed):

- qsub
- qdel
- qrst
- qstat
- qhost

Please refer to the relevant manual pages for operational details.

.. include:: links.rst
