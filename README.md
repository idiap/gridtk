# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        1 |     60% |         9 |
| src/gridtk/cli.py          |      446 |       57 |      126 |       21 |     84% |24, 37-44, 53-56, 58-59, 61-63, 65-66, 82, 407, 412, 421, 518, 539-540, 570-571, 651, 676, 732-733, 746-757, 796-801, 812-814, 817, 828-836, 873-875, 879, 881-883, 889 |
| src/gridtk/guard.py        |       44 |        0 |        0 |        0 |    100% |           |
| src/gridtk/manager.py      |      194 |       33 |       78 |        6 |     82% |43-57, 62-71, 93-94, 102-103, 137-143, 217, 250-251, 255, 288, 305, 311-\>310, 377-\>exit |
| src/gridtk/models.py       |      156 |       14 |       48 |        9 |     88% |38-\>exit, 90, 115, 159, 203, 224, 259, 296, 307, 311-312, 329-336 |
| src/gridtk/tools.py        |       38 |        0 |       14 |        0 |    100% |           |
| **TOTAL**                  |  **881** |  **105** |  **268** |   **37** | **86%** |           |


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