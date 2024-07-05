# SPDX-FileCopyrightText: Copyright © 2022 Idiap Research Institute <contact@idiap.ch>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# We simply write one line to stdout and one line to stderr
echo "This is a text message to std-out"
echo "This is a text message to std-err" >&2

# We exit with -1 (should be 255 as the "result")
exit -1
