.. SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
..
.. SPDX-License-Identifier: GPL-3.0-or-later

.. _gridtk.usage_api:

===============
 Using the API
===============

The ``gridtk`` framework is a python library to help submitting, tracking and
querying SGE.  Here is quick example on how to use the ``gridtk`` framework to
submit a python script:

.. code:: python

   import sys
   from gridtk.sge import JobManagerSGE
   from gridtk.tools import make_shell

   manager = JobManagerSGE()
   command = make_shell(sys.executable, ['myscript.py', '--help'])
   job = manager.submit(command)


You can do, programatically, everything you can do with the job manager - just
browse the help messages and the ``jman`` script for more information.


.. include:: links.rst
