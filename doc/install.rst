.. SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
..
.. SPDX-License-Identifier: GPL-3.0-or-later

.. _gridtk.install:

==============
 Installation
==============

Installation may follow one of two paths: deployment or development. Choose the
relevant tab for details on each of those installation paths.


.. tab:: Deployment (pip/uv)

   Install using pip_, or your preferred Python project management solution (e.g.
   uv_, rye_ or poetry_).

   **Stable** release, from PyPI:

   .. code:: sh

      pip install gridtk

   **Latest** development branch, from its git repository:

   .. code:: sh

      pip install git+https://gitlab.idiap.ch/software/gridtk@main


.. tab:: Deployment (pixi)

   Use pixi_ to add this package as a dependence:

   .. code:: sh

      pixi add gridtk


.. tab:: Development

   Checkout the repository, and then use pixi_ to setup a full development
   environment:

   .. code:: sh

      git clone git@gitlab.idiap.ch:software/gridtk
      pixi install --frozen

   .. tip::

      The ``--frozen`` flag will ensure that the latest lock-file available
      with sources is used.  If you'd like to update the lock-file to the
      latest set of compatible dependencies, remove that option.

      If you use `direnv to setup your pixi environment
      <https://pixi.sh/latest/features/environment/#using-pixi-with-direnv>`_
      when you enter the directory containing this package, you can use a
      ``.envrc`` file similar to this:

      .. code:: sh

         watch_file pixi.lock
         export PIXI_FROZEN="true"
         eval "$(pixi shell-hook)"


.. _gridtk.config:

Setup
-----

A configuration file may be useful to setup global options that should be often
reused.  The location of the configuration file depends on the value of the
environment variable ``$XDG_CONFIG_HOME``, but defaults to
``~/.config/gridtk.toml``.  You may edit this file using your preferred editor.

Here is an example configuration file that may be useful to many (replace
``<projectname>`` by the name of the project to charge):

.. code:: toml

   # selects project to submit jobs
   sge-extra-args-prepend = "-P <projectname>"


.. tip::

   To get a list of valid project names, execute:

   .. code:: sh

      qconf -sprjl


.. include:: links.rst
