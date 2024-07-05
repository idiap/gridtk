# Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Executes a given command within the context of a shell script that has its
enviroment set like Idiap's 'SETSHELL grid' does."""

from __future__ import annotations

import os
import shutil
import sys


def main() -> None:
    from ..setshell import environ

    # get the name of the script that we actually want to execute
    # (as defined in the setup.py)
    prog = os.path.basename(sys.argv[0])

    # get the base environment for searching for the command
    env = environ("grid")

    # removes the location from the current program from the list of paths to
    # search
    install_dir = os.path.realpath(os.path.dirname(sys.argv[0]))
    paths = env.get("PATH", os.defpath).split(os.pathsep)
    paths = [k for k in paths if os.path.realpath(k) != install_dir]
    env["PATH"] = os.pathsep.join(paths)

    # check that this program is avalid on that environment
    app = shutil.which(prog, path=env["PATH"])

    if app is None:
        raise RuntimeError(
            f"The CLI {prog} is not available when SETSHELL "
            f"grid is executed.  Are you at an Idiap computer?"
        )

    # call that specific command on the grid environment
    os.execvpe(prog, sys.argv, env)
