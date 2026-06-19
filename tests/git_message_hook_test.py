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
    _get_git_dir,
    check_commit_message,
    get_branch_name,
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


class TestGetGitDir:
    def test_no_git(self, tmp_path: Path, monkeypatch):
        """Returns None when there is no .git entry at all."""
        monkeypatch.chdir(tmp_path)
        assert _get_git_dir() is None

    def test_normal_repo(self, tmp_path: Path, monkeypatch):
        """Returns the .git directory for a normal (non-worktree) repo."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        assert _get_git_dir() == git_dir

    def test_worktree(self, tmp_path: Path, monkeypatch):
        """Follows the gitdir: pointer written by git worktree."""
        # Simulate the real git dir living elsewhere
        real_git_dir = tmp_path / "main_repo" / ".git" / "worktrees" / "my-worktree"
        real_git_dir.mkdir(parents=True)

        worktree_root = tmp_path / "worktree"
        worktree_root.mkdir()
        (worktree_root / ".git").write_text(
            f"gitdir: {real_git_dir}\n", encoding="utf-8"
        )

        monkeypatch.chdir(worktree_root)
        assert _get_git_dir() == real_git_dir


class TestGetBranchName:
    def test_normal_repo_on_branch(self, tmp_path: Path, monkeypatch):
        """Reads the branch name from HEAD in a normal repo."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/GA-1234\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert get_branch_name() == "GA-1234"

    def test_normal_repo_detached_head(self, tmp_path: Path, monkeypatch):
        """Returns None for a detached HEAD with no active rebase."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text(
            "abc123def456abc123def456abc123def456abc123\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert get_branch_name() is None

    def test_normal_repo_rebase_merge(self, tmp_path: Path, monkeypatch):
        """Returns the original branch name during an active rebase-merge."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        # HEAD points to a commit SHA during a rebase
        (git_dir / "HEAD").write_text(
            "abc123def456abc123def456abc123def456abc123\n", encoding="utf-8"
        )
        rebase_dir = git_dir / "rebase-merge"
        rebase_dir.mkdir()
        (rebase_dir / "head-name").write_text(
            "refs/heads/GA-5678\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert get_branch_name() == "GA-5678"

    def test_normal_repo_rebase_apply(self, tmp_path: Path, monkeypatch):
        """Returns the original branch name during an active rebase-apply (git am)."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text(
            "abc123def456abc123def456abc123def456abc123\n", encoding="utf-8"
        )
        rebase_dir = git_dir / "rebase-apply"
        rebase_dir.mkdir()
        (rebase_dir / "head-name").write_text(
            "refs/heads/feature/my-feature\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert get_branch_name() == "feature/my-feature"

    def test_worktree_on_branch(self, tmp_path: Path, monkeypatch):
        """Reads the branch name through the worktree gitdir: pointer."""
        real_git_dir = tmp_path / "main_repo" / ".git" / "worktrees" / "my-worktree"
        real_git_dir.mkdir(parents=True)
        (real_git_dir / "HEAD").write_text(
            "ref: refs/heads/GA-9999\n", encoding="utf-8"
        )

        worktree_root = tmp_path / "worktree"
        worktree_root.mkdir()
        (worktree_root / ".git").write_text(
            f"gitdir: {real_git_dir}\n", encoding="utf-8"
        )

        monkeypatch.chdir(worktree_root)
        assert get_branch_name() == "GA-9999"

    def test_worktree_rebase_merge(self, tmp_path: Path, monkeypatch):
        """Reads the rebase branch name through the worktree gitdir: pointer."""
        real_git_dir = tmp_path / "main_repo" / ".git" / "worktrees" / "my-worktree"
        real_git_dir.mkdir(parents=True)
        (real_git_dir / "HEAD").write_text(
            "abc123def456abc123def456abc123def456abc123\n", encoding="utf-8"
        )
        rebase_dir = real_git_dir / "rebase-merge"
        rebase_dir.mkdir()
        (rebase_dir / "head-name").write_text(
            "refs/heads/GA-7777\n", encoding="utf-8"
        )

        worktree_root = tmp_path / "worktree"
        worktree_root.mkdir()
        (worktree_root / ".git").write_text(
            f"gitdir: {real_git_dir}\n", encoding="utf-8"
        )

        monkeypatch.chdir(worktree_root)
        assert get_branch_name() == "GA-7777"

    def test_no_git(self, tmp_path: Path, monkeypatch):
        """Returns None when there is no .git entry."""
        monkeypatch.chdir(tmp_path)
        assert get_branch_name() is None
