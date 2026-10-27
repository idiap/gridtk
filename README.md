# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        1 |     60% |         9 |
| src/gridtk/cli.py          |      431 |       40 |      116 |       17 |     88% |29, 42-49, 58-61, 63-64, 66-68, 70-71, 87, 430, 435, 445, 683, 708, 739-740, 753-760, 828-830, 835, 844-849, 893-\>895, 901 |
| src/gridtk/guard.py        |       44 |        0 |        0 |        0 |    100% |           |
| src/gridtk/listing.py      |      140 |        5 |       42 |        4 |     94% |46, 57, 286-\>288, 365-367 |
| src/gridtk/manager.py      |      221 |       23 |       88 |        8 |     89% |52, 64, 84-93, 115-116, 126-127, 185-191, 265, 304-305, 309, 343, 362, 368-\>367, 446-\>exit |
| src/gridtk/models.py       |      212 |       18 |       60 |       11 |     89% |44-\>exit, 113, 138, 182, 214, 266, 287, 335, 372, 383, 387-388, 397, 436-437, 446-453 |
| src/gridtk/tools.py        |      101 |        1 |       40 |        1 |     99% |       133 |
| **TOTAL**                  | **1152** |   **88** |  **348** |   **42** | **90%** |           |


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