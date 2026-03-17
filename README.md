# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        1 |     60% |         9 |
| src/gridtk/cli.py          |      396 |       67 |      112 |       19 |     79% |23, 36-43, 52-55, 57-58, 60-62, 64-65, 76, 81, 365, 370, 379, 475, 496-497, 527-528, 608, 633, 673-678, 681-729, 740, 745-747, 751, 753-755, 761 |
| src/gridtk/manager.py      |      171 |       30 |       64 |        3 |     82% |41-55, 60-69, 91-92, 100-101, 135-141, 197-198, 226, 247->246, 313->315 |
| src/gridtk/models.py       |      131 |       12 |       36 |        7 |     87% |38->exit, 90, 130, 170, 190, 223, 263, 267-268, 285-292 |
| src/gridtk/tools.py        |       39 |        0 |       14 |        0 |    100% |           |
| **TOTAL**                  |  **740** |  **110** |  **228** |   **30** | **82%** |           |


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