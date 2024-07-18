# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/idiap/gridtk/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                       |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|--------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/gridtk/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| src/gridtk/\_\_main\_\_.py |        3 |        1 |        2 |        2 |     40% |8->exit, 9 |
| src/gridtk/cli.py          |      306 |       32 |      356 |      161 |     70% |21, 34-41, 44->66, 51->44, 58->51, 65->58, 66->65, 74->73, 80->222, 92->80, 98->92, 103->98, 109->103, 116->109, 117->116, 118->117, 119->118, 120->119, 121->120, 122->121, 123->122, 124->123, 125->124, 126->125, 127->126, 128->127, 129->128, 130->129, 131->130, 132->131, 133->132, 134->133, 135->134, 136->135, 137->136, 138->137, 139->138, 140->139, 141->140, 142->141, 143->142, 144->143, 145->144, 146->145, 147->146, 148->147, 149->148, 150->149, 151->150, 152->151, 153->152, 154->153, 155->154, 156->155, 157->156, 158->157, 159->158, 160->159, 161->160, 162->161, 163->162, 164->163, 165->164, 166->165, 167->166, 168->167, 169->168, 170->169, 171->170, 172->171, 173->172, 174->173, 175->174, 176->175, 177->176, 178->177, 179->178, 180->179, 181->180, 182->181, 183->182, 184->183, 185->184, 186->185, 187->186, 188->187, 189->188, 190->189, 191->190, 192->191, 193->192, 194->193, 195->194, 196->195, 197->196, 198->197, 199->198, 200->199, 201->200, 202->201, 203->202, 204->203, 205->204, 206->205, 207->206, 208->207, 209->208, 210->209, 211->210, 212->211, 213->212, 214->213, 215->214, 216->215, 217->216, 218->217, 219->218, 220->219, 221->220, 222->221, 243, 248, 252->exit, 257, 280-283, 285-286, 288-290, 292-293, 304, 310, 364->367, 365->364, 366->365, 367->366, 378->exit, 387->390, 388->387, 389->388, 390->389, 401->exit, 410->413, 411->410, 412->411, 413->412, 426->exit, 451->460, 452->451, 453->452, 459->453, 460->459, 472->exit, 482->488, 484->482, 485, 490-492, 496, 498-500, 505->508, 506->505, 507->506, 508->507, 519->exit, 529 |
| src/gridtk/manager.py      |      141 |       27 |       60 |        7 |     78% |41-55, 60-67, 78-83, 122->121, 128-129, 157, 173, 212->221, 236->244, 237->236, 242->236 |
| src/gridtk/models.py       |      135 |       13 |       49 |       13 |     85% |36->35, 38->exit, 71, 90, 130, 170, 187->186, 190, 196->195, 223, 242->255, 263, 267-268, 281->280, 285-292, 295->294 |
| src/gridtk/tools.py        |       39 |        0 |       14 |        0 |    100% |           |
|                  **TOTAL** |  **624** |   **73** |  **481** |  **183** | **75%** |           |


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