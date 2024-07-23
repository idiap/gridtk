# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        1 |     60% |         9 |
| src/gridtk/cli.py          |      310 |       34 |      356 |       14 |     92% |21, 34-41, 50-53, 55-56, 58-60, 62-63, 74, 79, 339, 344, 353, 423-424, 515, 520-522, 526, 528-530, 536 |
| src/gridtk/manager.py      |      147 |       27 |       66 |        3 |     81% |41-55, 60-67, 78-83, 139-140, 168, 186, 255->249 |
| src/gridtk/models.py       |      135 |       12 |       49 |        7 |     89% |38->exit, 90, 130, 170, 190, 223, 263, 267-268, 285-292 |
| src/gridtk/tools.py        |       39 |        0 |       14 |        0 |    100% |           |
|                  **TOTAL** |  **634** |   **74** |  **487** |   **25** | **89%** |           |


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