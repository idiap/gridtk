# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        1 |     60% |         9 |
| src/gridtk/cli.py          |      447 |       57 |      126 |       21 |     84% |25, 38-45, 54-57, 59-60, 62-64, 66-67, 83, 416, 421, 431, 528, 549-550, 580-581, 661, 686, 717-718, 731-742, 781-786, 797-799, 802, 813-821, 858-860, 864, 866-868, 874 |
| src/gridtk/guard.py        |       44 |        0 |        0 |        0 |    100% |           |
| src/gridtk/manager.py      |      204 |       23 |       82 |        8 |     88% |46, 58, 64-73, 95-96, 104-105, 174-180, 254, 287-288, 292, 325, 342, 348-\>347, 414-\>exit |
| src/gridtk/models.py       |      163 |       14 |       50 |        9 |     88% |38-\>exit, 90, 115, 159, 223, 244, 279, 316, 327, 331-332, 349-356 |
| src/gridtk/tools.py        |       43 |        0 |       16 |        0 |    100% |           |
| **TOTAL**                  |  **904** |   **95** |  **276** |   **39** | **87%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/idiap/gridtk/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/idiap/gridtk/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fidiap%2Fgridtk%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.