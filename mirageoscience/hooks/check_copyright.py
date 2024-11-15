#!/usr/bin/env python3

# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024 Mira Geoscience Ltd.                                              '
#                                                                                       '
#  This file is part of mirageoscience.pre-commit-hooks package.                        '
#                                                                                       '
#  mirageoscience_pre_commit_hooks is distributed under the terms and conditions of     '
#  the MIT License (see LICENSE file at the root of this source code package).          '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import re
import sys
from datetime import date


def main(args=None):
    """Checks for valid copyright statements in given files.

    This function scans the specified files for copyright notices and reports
    any files that either lack a copyright statement or have an invalid year.

    Args:
        args (list, optional): A list of filenames to be checked. Defaults to
            `sys.argv[1:]` if not provided.

    Raises:
        SystemExit: Exits the program with an exit code of 1 if any
            files have missing or invalid copyright statements.
    """
    current_year = date.today().year
    copyright_re = re.compile(
        rf"\bcopyright \(c\) (:?\d{{4}}-|)\b{current_year}\b", re.IGNORECASE
    )
    files = sys.argv[1:]
    max_lines = 10
    report_files = []
    for f in files:
        with open(f, encoding="utf-8") as file:
            count = 0
            has_dated_copyright = False
            for line in file:
                count += 1
                if count >= max_lines and not (
                    f.endswith("README.rst") or f.endswith("README-dev.rst")
                ):
                    break
                if re.search(copyright_re, line):
                    has_dated_copyright = True
                    break

            if not has_dated_copyright:
                report_files.append(f)

    if len(report_files) > 0:
        for f in report_files:
            sys.stderr.write(f"{f}: No copyright or invalid year\n")
        exit(1)


# readonly CURRENT_YEAR=$(date +"%Y")

# if ! grep -e "Copyright (c) .*$CURRENT_YEAR" $(head -10 $f) 2>&1 1>/dev/null; then
#    echo "File '$f' has no copyright or an invalid year"
#    exit 1
# fi
