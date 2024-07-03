# SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import time

from importlib.metadata import distribution

# -- General configuration -----------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
needs_sphinx = "1.3"

# Add any Sphinx extension module names here, as strings. They can be extensions
# coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    "myst_parser",
]

# General information about the project.
project = "gridtk"
package = distribution(project)

copyright = "%s, Idiap Research Institute" % time.strftime("%Y")

# The short X.Y version.
version = package.version
# The full version, including alpha/beta/rc tags.
release = version

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"
pygments_dark_style = "monokai"

# Some variables which are useful for generated material
project_variable = project.replace(".", "_")
short_description = package.metadata["Summary"]
owner = ["Idiap Research Institute"]

# -- Options for HTML output ---------------------------------------------------

html_theme = "furo"

html_theme_options = {
    "source_edit_link": f"https://gitlab.idiap.ch/software/{project}/-/edit/main/doc/{{filename}}",
}

html_title = f"{project} {release}"
