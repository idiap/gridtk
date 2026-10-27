# SPDX-FileCopyrightText: 2026 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import contextlib
import os
import tempfile

from collections.abc import Iterator
from pathlib import Path

import pytest

from click.testing import CliRunner


class Runner(CliRunner):
    """A CliRunner with the ``isolated_filesystem`` that Click deprecated.

    Click 9.0 removes ``CliRunner.isolated_filesystem``, advising to use a
    temporary directory instead.  The tests run commands that use relative paths,
    so this keeps the same behaviour: run in a new temporary directory.
    """

    @contextlib.contextmanager
    def isolated_filesystem(
        self, temp_dir: str | os.PathLike[str] | None = None
    ) -> Iterator[str]:
        """Change to a new temporary directory (created in ``temp_dir``) until the
        end of the ``with`` block, and yield its path.
        """
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory(dir=temp_dir) as path:
            os.chdir(path)
            try:
                yield path
            finally:
                os.chdir(cwd)


@pytest.fixture
def runner():
    return Runner()
