#!/usr/bin/env python3

# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2025 Mira Geoscience Ltd.                                     '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path


MAX_TOP_LINES = 10


def check_files(
    files: list[str] | None = None, full_scan_files: list[str] | None = None
):
    """Checks for valid copyright statements in given files.

    This function scans the specified files for copyright notices and reports
    any files that either lack a copyright statement or have an invalid year.

    Args:
        files (list, optional): A list of filenames to be checked. Defaults to
            `sys.argv[1:]` if not provided.
        full_scan_files (list, optional): A list of filenames to be scanned
            entirely, instead of checking only the top lines.

    Raises:
        SystemExit: Exits the program with an exit code of 1 if any
            files have missing or invalid copyright statements.
    """
    current_year = date.today().year
    copyright_re = re.compile(
        rf"\bcopyright \(c\) (:?\d{{4}}-|)\b{current_year}\b", re.IGNORECASE
    )
    if full_scan_files is None:
        full_scan_files = []
    if files is None:
        files = sys.argv[1:]
    file_paths = [Path(f) for f in files]
    report_files = []
    for f in file_paths:
        with open(f, encoding="utf-8") as file:
            count = 0
            has_dated_copyright = False
            for line in file:
                count += 1
                if count >= MAX_TOP_LINES and f.name not in full_scan_files:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="list of files to scan")
    parser.add_argument(
        "--full-scan-files",
        nargs="+",
        help=f"list of files to scan entirely, instead of checking only the {MAX_TOP_LINES} top lines",
        default=["README.rst", "README-dev.rst", "package.rst"],
        required=False,
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    check_files(args.files, args.full_scan_files)


# Note: a simpler bash script for this task would be:
# ----------------------------
# readonly CURRENT_YEAR=$(date +"%Y")
#
# if ! grep -e "Copyright (c) .*$CURRENT_YEAR" $(head -10 $f) 2>&1 1>/dev/null; then
#    echo "File '$f' has no copyright or an invalid year"
#    exit 1
# fi
# ----------------------------
