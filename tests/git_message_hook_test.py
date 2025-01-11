# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2025 Mira Geoscience Ltd.                                     '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from mirageoscience.hooks.git_message_hook import (
    check_commit_message,
    get_jira_id,
    get_message_prefix_bang,
)
from mirageoscience.hooks.git_message_hook import (
    main as git_message_hook_main,
)


@pytest.fixture
def mock_get_branch_name(mocker):
    def _mock_get_branch_name(branch_name):
        mocker.patch(
            "mirageoscience.hooks.git_message_hook.get_branch_name",
            return_value=branch_name,
        )
        return get_jira_id(branch_name)

    return _mock_get_branch_name


def test_get_jira_id():
    text = "[GEOPY-1233] Git commit message"
    assert get_jira_id(text) == "GEOPY-1233"


def test_get_message_prefix_bang_with_bang():
    """Tests if get_message_prefix_bang can extract the prefix bang from a line."""
    line = "fixup! This is a fix"
    expected_prefix_bang = "fixup! "
    actual_prefix_bang = get_message_prefix_bang(line)
    assert actual_prefix_bang == expected_prefix_bang


def test_get_message_prefix_bang_no_bang():
    """Tests if get_message_prefix_bang returns empty string for a line without bang."""
    line = "This is a commit message"
    expected_prefix_bang = ""
    actual_prefix_bang = get_message_prefix_bang(line)
    assert actual_prefix_bang == expected_prefix_bang


def test_check_commit_message_valid_with_message_jira(
    mock_get_branch_name, tmp_path: Path
):
    """Test avec identifiant JIRA dans le message de commit"""
    branch_name = "feature_branch"
    mock_get_branch_name(branch_name)
    message_content = "GEOPY-123 Fix a bug xx"
    filepath = tmp_path / "test_commit_message.txt"
    filepath.write_text(message_content, encoding="utf-8")

    is_valid, error_message = check_commit_message(str(filepath))
    assert is_valid
    assert error_message == ""


def test_check_commit_message_invalid_no_jira(mock_get_branch_name, tmp_path: Path):
    """Test without JIRA id in the branch name or message content"""
    branch_name = "feature_branch"
    mock_get_branch_name(branch_name)
    message_content = "Fix a bug"
    filepath = tmp_path / "test_commit_message.txt"
    filepath.write_text(message_content, encoding="utf-8")

    is_valid, error_message = check_commit_message(str(filepath))
    assert not is_valid
    assert (
        error_message
        == "Either the branch name or the commit message must start with a JIRA ID."
    )


def test_check_commit_message_invalid_different_jira(
    mock_get_branch_name, tmp_path: Path
):
    """Test with different JIRA id in the branch name and in the message content"""
    branch_name = "GEOPY-123_fix_bug"
    mock_get_branch_name(branch_name)
    message_content = "GI-456 Fix a bug"
    filepath = tmp_path / "test_commit_message.txt"
    filepath.write_text(message_content, encoding="utf-8")

    is_valid, error_message = check_commit_message(str(filepath))
    assert not is_valid
    assert error_message.startswith("Different JIRA ID in commit message")


def test_check_commit_message_invalid_short_message(
    mock_get_branch_name, tmp_path: Path
):
    """Test with a too short message content"""
    branch_name = "GEOPY-123_fix_bug"
    mock_get_branch_name(branch_name)
    message_content = "Fix"
    filepath = tmp_path / "test_commit_message.txt"
    filepath.write_text(message_content, encoding="utf-8")

    is_valid, error_message = check_commit_message(str(filepath))
    assert not is_valid
    assert error_message.startswith("First line of commit message must be at least")


def test_main_calls_prepare_commit_msg():
    test_args = ["script_name", "--prepare", "msg_file"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.git_message_hook.prepare_commit_msg"
        ) as mock_prepare_commit_msg:
            git_message_hook_main()
            mock_prepare_commit_msg.assert_called_once_with("msg_file", *[])


def test_main_calls_check_commit_msg():
    test_args = ["script_name", "--check", "msg_file"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.git_message_hook.check_commit_msg"
        ) as mock_check_commit_msg:
            git_message_hook_main()
            mock_check_commit_msg.assert_called_once_with("msg_file")


def test_main_with_remaining_args():
    test_args = ["script_name", "--prepare", "msg_file", "arg1", "arg2"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.git_message_hook.prepare_commit_msg"
        ) as mock_prepare_commit_msg:
            git_message_hook_main()
            mock_prepare_commit_msg.assert_called_once_with("msg_file", "arg1", "arg2")
