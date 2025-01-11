# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2025 Mira Geoscience Ltd.                                          '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from mirageoscience.hooks.check_copyright import _FULL_SCAN_FILE_NAMES, check_files
from mirageoscience.hooks.check_copyright import main as check_copyright_main


def test_valid_copyright(tmp_path: Path):
    current_year = date.today().year
    file_content = f"\n\n\n# Copyright (c) {current_year}\n"
    test_file = tmp_path / "test_current_year.py"
    test_file.write_text(file_content, encoding="utf-8")
    assert check_files([str(test_file)])


def test_old_copyright_date(tmp_path: Path):
    current_year = date.today().year
    file_content = f"\n\n\n# Copyright (c) {current_year - 1}\n"
    test_file = tmp_path / "test_old_year.py"
    test_file.write_text(file_content, encoding="utf-8")
    assert not check_files([str(test_file)])


def test_missing_copyright(tmp_path: Path):
    test_file = tmp_path / "test_missing.py"
    test_file.write_text("No statement here", encoding="utf-8")
    assert not check_files([str(test_file)])


@pytest.mark.parametrize("year_is_current", [True, False])
def test_full_scan_custom_files(tmp_path: Path, year_is_current: bool):
    statement_year = date.today().year
    if not year_is_current:
        statement_year -= 1
    file_content = "\n Not Here" * 100 + f"# Copyright (c) {statement_year}\n"
    file_names = ["something.else", "another.thing"]
    test_files = []
    for f in file_names:
        test_file = tmp_path / f
        test_file.write_text(file_content, encoding="utf-8")
        test_files.append(str(test_file))
    assert year_is_current == check_files(test_files, full_scan_files=file_names)


def test_copyright_not_found_further_down(tmp_path: Path):
    current_year = date.today().year
    file_content = "\n Not Here" * 100 + f"# Copyright (c) {current_year}\n"
    file_name = "something.else"
    test_file = tmp_path / file_name
    test_file.write_text(file_content, encoding="utf-8")
    assert not check_files([str(test_file)])


@pytest.mark.parametrize("outdated_file_position", [0, 1, 2])
def test_multiple_good_files(tmp_path: Path, outdated_file_position: int):
    current_year = date.today().year
    good_file_content = f"# Copyright (c) {current_year}\n"
    outdated_file_content = f"# Copyright (c) {current_year - 1}\n"
    test_file_good1 = tmp_path / "test_good1.py"
    test_file_good1.write_text(good_file_content, encoding="utf-8")
    test_file_good2 = tmp_path / "test_good2.py"
    test_file_good2.write_text(good_file_content, encoding="utf-8")
    test_file_outdated = tmp_path / "test_outdated.py"
    test_file_outdated.write_text(outdated_file_content, encoding="utf-8")
    test_files = [
        str(test_file_good1),
        str(test_file_good2),
    ]
    test_files.insert(outdated_file_position, str(test_file_outdated))
    assert not check_files(test_files)


def test_main_passes_args_to_check_files():
    test_args = ["script_name", "file1.py", "file2.py"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.check_copyright.check_files"
        ) as mock_check_files:
            mock_check_files.return_value = True
            check_copyright_main()
            mock_check_files.assert_called_once_with(
                ["file1.py", "file2.py"],
                ["README.rst", "README-dev.rst", "package.rst"],
            )


def test_main_exits_with_error():
    test_args = ["script_name", "file1.py"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.check_copyright.check_files"
        ) as mock_check_files:
            mock_check_files.return_value = False
            with pytest.raises(SystemExit) as e:
                check_copyright_main()
            assert e.value.code == 1


def test_main_with_full_scan_files():
    test_args = [
        "script_name",
        "file1.py",
        "--full-scan-files",
        "full_file1.py",
        "full_file2.py",
    ]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.check_copyright.check_files"
        ) as mock_check_files:
            mock_check_files.return_value = True
            check_copyright_main()
            mock_check_files.assert_called_once_with(
                ["file1.py"], [*_FULL_SCAN_FILE_NAMES, "full_file1.py", "full_file2.py"]
            )
