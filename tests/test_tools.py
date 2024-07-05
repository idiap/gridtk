# SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from gridtk.tools import get_array_job_slice


class SGE_EnvWrapper:
    def __init__(
        self,
        SGE_TASK_ID=1,
        SGE_TASK_LAST=1,
        SGE_TASK_FIRST=1,
        SGE_TASK_STEPSIZE=1,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.variables = {
            "SGE_TASK_ID": str(SGE_TASK_ID),
            "SGE_TASK_LAST": str(SGE_TASK_LAST),
            "SGE_TASK_FIRST": str(SGE_TASK_FIRST),
            "SGE_TASK_STEPSIZE": str(SGE_TASK_STEPSIZE),
        }
        self.old_variables = None

    def __enter__(self):
        # backup current variables
        self.old_variables = {
            name: os.environ.get(name) for name in self.variables
        }

        # set the requested variables
        for name, value in self.variables.items():
            os.environ[name] = value

        return self

    def __exit__(self, *args):
        # restore old variables
        for name, value in self.old_variables.items():
            if value is None:
                del os.environ[name]
            else:
                os.environ[name] = value

    def set(self, name, value):
        assert name in self.old_variables
        os.environ[name] = str(value)


def test_get_array_job_slice():
    with SGE_EnvWrapper() as wrapper:
        s = get_array_job_slice(10)
        assert s == slice(0, 10)

        wrapper.set("SGE_TASK_LAST", 5)
        s = get_array_job_slice(10)
        assert s == slice(0, 2)

        wrapper.set("SGE_TASK_ID", 2)
        s = get_array_job_slice(10)
        assert s == slice(2, 4)

        wrapper.set("SGE_TASK_ID", 5)
        s = get_array_job_slice(10)
        assert s == slice(8, 10)
