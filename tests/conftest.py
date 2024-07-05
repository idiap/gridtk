# SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import pathlib

import pytest


@pytest.fixture
def datadir(request) -> pathlib.Path:
    """Returns the directory in which the test is sitting."""
    return pathlib.Path(request.fspath).parent / "data"
