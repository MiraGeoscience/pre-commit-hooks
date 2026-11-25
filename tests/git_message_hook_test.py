# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                     '
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
    prepare_commit_msg,
)
from mirageoscience.hooks.git_message_hook import (
    main as git_message_hook_main,
)


@pytest.fixture(name="mock_get_branch_name")
def fixture_mock_get_branch_name(mocker):
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


@pytest.mark.parametrize(
    "prefix", ["fixup! ", "squash! ", "amend! ", "fixup! fixup! ", "amend! squash! "]
)
def test_get_message_prefix_bang_with_bang(prefix: str):
    """Tests if get_message_prefix_bang can extract the prefix bang from a line."""
    line = f"{prefix}This is a fix"
    expected_prefix_bang = prefix
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
            mock_prepare_commit_msg.assert_called_once_with(
                "msg_file", issue_trailer=False
            )


def test_main_calls_check_commit_msg():
    test_args = ["script_name", "--check", "msg_file"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.git_message_hook.check_commit_msg"
        ) as mock_check_commit_msg:
            git_message_hook_main()
            mock_check_commit_msg.assert_called_once_with(
                "msg_file", issue_trailer=False
            )


def test_main_with_remaining_args():
    test_args = ["script_name", "--prepare", "msg_file", "arg1", "arg2"]
    with mock.patch.object(sys, "argv", test_args):
        with mock.patch(
            "mirageoscience.hooks.git_message_hook.prepare_commit_msg"
        ) as mock_prepare_commit_msg:
            git_message_hook_main()
            mock_prepare_commit_msg.assert_called_once_with(
                "msg_file", "arg1", "arg2", issue_trailer=False
            )


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

    def test_git_dir_environment_variable(self, tmp_path: Path, monkeypatch):
        """Uses GIT_DIR when Git provides an alternate git directory."""
        git_dir = tmp_path / "alternate_git_dir"
        git_dir.mkdir()
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_DIR", str(git_dir))
        assert _get_git_dir() == git_dir


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
        (rebase_dir / "head-name").write_text("refs/heads/GA-5678\n", encoding="utf-8")
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
        (rebase_dir / "head-name").write_text("refs/heads/GA-7777\n", encoding="utf-8")

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


class TestPrepareCommitMsg:
    @staticmethod
    def _set_up_rebase_git_dir(tmp_path: Path, monkeypatch) -> None:
        git_dir = tmp_path / "alternate_git_dir"
        rebase_dir = git_dir / "rebase-merge"
        rebase_dir.mkdir(parents=True)
        (git_dir / "HEAD").write_text("abc123\n", encoding="utf-8")
        (rebase_dir / "head-name").write_text("refs/heads/GA-5678\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_DIR", str(git_dir))

    @pytest.mark.parametrize("issue_trailer", [False, True])
    def test_rebase_commit_without_jira_gets_branch_jira(
        self, tmp_path: Path, monkeypatch, issue_trailer: bool
    ):
        self._set_up_rebase_git_dir(tmp_path, monkeypatch)
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text("An original commit message\n", encoding="utf-8")

        args = ["git_message_hook", "--prepare"]
        if issue_trailer:
            args.append("--issue-trailer")
        args.extend([str(message_file), "commit", "HEAD"])
        monkeypatch.setattr(sys, "argv", args)
        git_message_hook_main()

        expected_message = (
            "An original commit message\n\nIssue: GA-5678\n"
            if issue_trailer
            else "[GA-5678] An original commit message\n"
        )
        assert message_file.read_text(encoding="utf-8") == expected_message

    @pytest.mark.parametrize("issue_trailer", [False, True])
    def test_rebase_commit_with_different_jira_is_preserved(
        self, tmp_path: Path, monkeypatch, issue_trailer: bool
    ):
        self._set_up_rebase_git_dir(tmp_path, monkeypatch)
        message_file = tmp_path / "COMMIT_EDITMSG"
        original_message = (
            "An original commit message\n\nIssue: GI-1234\n"
            if issue_trailer
            else "[GI-1234] An original commit message\n"
        )
        message_file.write_text(original_message, encoding="utf-8")

        prepare_commit_msg(str(message_file), "commit", issue_trailer=issue_trailer)

        assert message_file.read_text(encoding="utf-8") == original_message
        assert check_commit_message(str(message_file), issue_trailer=issue_trailer) == (
            True,
            "",
        )

    @pytest.mark.parametrize("source", ["message", "commit", "merge"])
    @pytest.mark.parametrize("has_jira", [False, True])
    @pytest.mark.parametrize("issue_trailer", [False, True])
    def test_cherry_pick_message(
        self,
        tmp_path: Path,
        monkeypatch,
        source: str,
        has_jira: bool,
        issue_trailer: bool,
    ):
        git_dir = tmp_path / "alternate_git_dir"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/GA-5678\n", encoding="utf-8")
        (git_dir / "CHERRY_PICK_HEAD").write_text("abc123\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GIT_DIR", str(git_dir))
        message_file = tmp_path / "COMMIT_EDITMSG"
        original_message = "An original commit message\n"
        if has_jira:
            original_message = (
                f"{original_message}\nIssue: GI-1234\n"
                if issue_trailer
                else f"[GI-1234] {original_message}"
            )
        message_file.write_text(original_message, encoding="utf-8")

        prepare_commit_msg(str(message_file), source, issue_trailer=issue_trailer)

        expected_message = original_message
        if not has_jira:
            expected_message = (
                f"{original_message}\nIssue: GA-5678\n"
                if issue_trailer
                else f"[GA-5678] {original_message}"
            )
        assert message_file.read_text(encoding="utf-8") == expected_message
        assert check_commit_message(str(message_file), issue_trailer=issue_trailer) == (
            True,
            "",
        )

    @pytest.mark.parametrize("source", ["merge", "commit"])
    def test_non_replay_message_is_unchanged(
        self, tmp_path: Path, monkeypatch, mock_get_branch_name, source: str
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        original_message = "[GI-1234] An original commit message\n"
        message_file.write_text(original_message, encoding="utf-8")
        args = ["git_message_hook", "--prepare", str(message_file), source]
        if source == "commit":
            args.append("HEAD")
        monkeypatch.setattr(sys, "argv", args)

        git_message_hook_main()

        assert message_file.read_text(encoding="utf-8") == original_message
        is_valid, error_message = check_commit_message(str(message_file))
        assert not is_valid
        assert error_message.startswith("Different JIRA ID in commit message")

    @pytest.mark.parametrize(
        "operation", ["rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", None]
    )
    @pytest.mark.parametrize("issue_trailer", [False, True])
    def test_missing_jira_is_only_allowed_during_rebase(
        self, tmp_path: Path, monkeypatch, operation: str | None, issue_trailer: bool
    ):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text(
            "ref: refs/heads/feature_branch\n", encoding="utf-8"
        )
        if operation == "CHERRY_PICK_HEAD":
            (git_dir / operation).write_text("abc123\n", encoding="utf-8")
        elif operation:
            (git_dir / operation).mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)
        message_file = tmp_path / "COMMIT_EDITMSG"
        original_message = "An original commit message\n"
        message_file.write_text(original_message, encoding="utf-8")

        prepare_commit_msg(
            str(message_file), "commit", "HEAD", issue_trailer=issue_trailer
        )

        assert message_file.read_text(encoding="utf-8") == original_message
        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=issue_trailer
        )
        if operation in ("rebase-merge", "rebase-apply"):
            assert is_valid
            assert error_message == ""
        else:
            assert not is_valid
            assert error_message.startswith("Either the branch name")

    @pytest.mark.parametrize(
        "operation", ["rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", None]
    )
    @pytest.mark.parametrize("summary", ["123456789", "1234567890"])
    @pytest.mark.parametrize("issue_trailer", [False, True])
    def test_minimum_message_length_is_not_enforced_during_replay(
        self,
        tmp_path: Path,
        monkeypatch,
        operation: str | None,
        summary: str,
        issue_trailer: bool,
    ):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/GA-5678\n", encoding="utf-8")
        if operation == "CHERRY_PICK_HEAD":
            (git_dir / operation).write_text("abc123\n", encoding="utf-8")
        elif operation:
            (git_dir / operation).mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = (
            f"{summary}\n\nIssue: GA-5678\n"
            if issue_trailer
            else f"GA-5678 {summary}\n"
        )
        message_file.write_text(message, encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=issue_trailer
        )

        if operation or len(summary) >= 10:
            assert is_valid
            assert error_message == ""
        else:
            assert not is_valid
            assert error_message.startswith(
                "First line of commit message must be at least"
            )


class TestIssueTrailers:
    @pytest.fixture(autouse=True)
    def isolate_git_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)

    @pytest.mark.parametrize(
        "message, expected",
        [
            (
                "A sufficiently long subject\n",
                "A sufficiently long subject\n\nIssue: GA-5678\n",
            ),
            (
                "fixup! A sufficiently long subject\n\nSome body text.\n",
                "fixup! A sufficiently long subject\n\nSome body text.\n\nIssue: GA-5678\n",
            ),
            (
                "A sufficiently long subject\n\nSigned-off-by: Example <test@example.invalid>\n",
                "A sufficiently long subject\n\n"
                "Signed-off-by: Example <test@example.invalid>\nIssue: GA-5678\n",
            ),
            (
                "A sufficiently long subject\n\n# Template instructions\n",
                "A sufficiently long subject\n\nIssue: GA-5678\n# Template instructions\n",
            ),
            (
                "[GI-1234] A sufficiently long subject\n",
                "[GI-1234] A sufficiently long subject\n\nIssue: GA-5678\n",
            ),
            (
                "A sufficiently long subject",
                "A sufficiently long subject\n\nIssue: GA-5678\n",
            ),
            (
                "A sufficiently long subject\n\nIssue: GI-1234\n\nMore body text.\n",
                "A sufficiently long subject\n\nIssue: GI-1234\n\n"
                "More body text.\n\nIssue: GA-5678\n",
            ),
            (
                "A sufficiently long subject\n\n"
                "Signed-off-by: Example <test@example.invalid>\n"
                " continuation\n\n# Template instructions\n",
                "A sufficiently long subject\n\n"
                "Signed-off-by: Example <test@example.invalid>\n"
                " continuation\nIssue: GA-5678\n# Template instructions\n",
            ),
            (
                "A sufficiently long subject\n\n---\nIssue: GI-1234\n",
                "A sufficiently long subject\n\nIssue: GA-5678\n---\nIssue: GI-1234\n",
            ),
            (
                "A sufficiently long subject\n\n"
                "# ------------------------ >8 ------------------------\n"
                "Issue: GI-1234\n",
                "A sufficiently long subject\n\nIssue: GA-5678\n"
                "# ------------------------ >8 ------------------------\n"
                "Issue: GI-1234\n",
            ),
        ],
    )
    def test_prepare_adds_only_a_footer(
        self, tmp_path: Path, mock_get_branch_name, message: str, expected: str
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(message, encoding="utf-8")

        prepare_commit_msg(str(message_file), issue_trailer=True)
        prepare_commit_msg(str(message_file), issue_trailer=True)

        assert message_file.read_text(encoding="utf-8") == expected

    @pytest.mark.parametrize("value", ["GI-1234", "", "not-an-issue"])
    def test_prepare_preserves_existing_trailer(
        self, tmp_path: Path, mock_get_branch_name, value: str
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        original_message = f"A sufficiently long subject\n\nIssue: {value}\n"
        message_file.write_text(original_message, encoding="utf-8")

        prepare_commit_msg(str(message_file), issue_trailer=True)

        assert message_file.read_text(encoding="utf-8") == original_message

    @pytest.mark.parametrize(
        "message, valid",
        [
            ("A sufficiently long subject\n\nIssue: GA-5678\n", True),
            ("A sufficiently long subject\n\nissue: GA-5678\n", True),
            ("A sufficiently long subject\n\nIssue: GA-5678\nIssue: GI-1234\n", True),
            ("A sufficiently long subject\n\nIssue:\n GA-5678\n", True),
            (
                "A sufficiently long subject\n\n"
                "Issue: GA-5678\nSigned-off-by: Example <test@example.invalid>\n",
                True,
            ),
            ("[GA-5678] A sufficiently long subject\n", False),
            ("A sufficiently long subject\n\nRefs: GA-5678\n", False),
            ("A sufficiently long subject\n\n# Issue: GA-5678\n", False),
            ("A sufficiently long subject\n\nIssue: GA-5678\n\nBody text.\n", False),
            ("A sufficiently long subject\n\nIssue: not-an-issue\n", False),
            ("A sufficiently long subject\n\nIssue:\n", False),
            ("A sufficiently long subject\n\n---\nIssue: GA-5678\n", False),
            (
                "A sufficiently long subject\n\n"
                "# ------------------------ >8 ------------------------\n"
                "Issue: GA-5678\n",
                False,
            ),
            ("A sufficiently long subject\nIssue: GA-5678\n", False),
        ],
    )
    def test_check_uses_only_valid_issue_trailers(
        self, tmp_path: Path, mock_get_branch_name, message: str, valid: bool
    ):
        mock_get_branch_name("feature_branch")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(message, encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=True
        )

        assert is_valid == valid
        assert bool(error_message) != valid

    @pytest.mark.parametrize("operation", [None, "rebase-merge", "CHERRY_PICK_HEAD"])
    @pytest.mark.parametrize(
        "trailers", ["Issue: GI-1234\n", "Issue: GA-5678\nIssue: GI-1234\n"]
    )
    def test_mismatch_and_short_subject_during_replay(
        self, tmp_path: Path, mock_get_branch_name, operation: str | None, trailers: str
    ):
        mock_get_branch_name("GA-5678")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        if operation == "CHERRY_PICK_HEAD":
            (git_dir / operation).write_text("abc123\n", encoding="utf-8")
        elif operation:
            (git_dir / operation).mkdir()
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(f"Short\n\n{trailers}", encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=True
        )

        if operation:
            assert is_valid
            assert error_message == ""
        else:
            assert not is_valid
            assert "Different JIRA ID in Issue trailer GI-1234" in error_message

    @pytest.mark.parametrize("mode", ["--prepare", "--check"])
    def test_cli_option(
        self, tmp_path: Path, monkeypatch, mock_get_branch_name, mode: str
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = "A sufficiently long subject\n"
        if mode == "--check":
            message += "\nIssue: GI-1234\n"
        message_file.write_text(message, encoding="utf-8")
        monkeypatch.setattr(
            sys,
            "argv",
            ["git_message_hook", mode, "--issue-trailer", str(message_file)],
        )

        if mode == "--check":
            with pytest.raises(SystemExit) as exc_info:
                git_message_hook_main()
            assert exc_info.value.code == 1
        else:
            git_message_hook_main()
            assert message_file.read_text(encoding="utf-8") == (
                "A sufficiently long subject\n\nIssue: GA-5678\n"
            )

    @pytest.mark.parametrize("message", ["", "# Template instructions\n"])
    def test_prepared_trailer_does_not_count_as_a_summary(
        self, tmp_path: Path, mock_get_branch_name, message: str
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(message, encoding="utf-8")

        prepare_commit_msg(str(message_file), issue_trailer=True)
        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=True
        )

        assert not is_valid
        assert error_message.startswith("First line of commit message must be at least")

    def test_default_mode_does_not_use_issue_trailers(
        self, tmp_path: Path, mock_get_branch_name
    ):
        mock_get_branch_name("feature_branch")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(
            "A sufficiently long subject\n\nIssue: GA-5678\n", encoding="utf-8"
        )

        is_valid, error_message = check_commit_message(str(message_file))

        assert not is_valid
        assert error_message == (
            "Either the branch name or the commit message must start with a JIRA ID."
        )

    def test_trailer_preparation_and_check_do_not_start_subprocesses(
        self, tmp_path: Path, mock_get_branch_name
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text("A sufficiently long subject\n", encoding="utf-8")

        with mock.patch(
            "subprocess.Popen", side_effect=AssertionError("Unexpected subprocess")
        ):
            prepare_commit_msg(str(message_file), issue_trailer=True)
            assert check_commit_message(str(message_file), issue_trailer=True) == (
                True,
                "",
            )
            prepare_commit_msg(str(message_file), issue_trailer=True)

        assert message_file.read_text(encoding="utf-8") == (
            "A sufficiently long subject\n\nIssue: GA-5678\n"
        )


class TestBangPrefixes:
    @pytest.fixture(autouse=True)
    def isolate_git_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GIT_DIR", raising=False)

    @pytest.mark.parametrize("issue_trailer", [False, True])
    @pytest.mark.parametrize(
        "prefix", ["fixup! ", "squash! ", "amend! ", "fixup! fixup! "]
    )
    def test_preparation_preserves_autosquash_target(
        self, tmp_path: Path, mock_get_branch_name, prefix: str, issue_trailer: bool
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = f"{prefix}Original target without a ticket\n"
        message_file.write_text(message, encoding="utf-8")

        prepare_commit_msg(str(message_file), issue_trailer=issue_trailer)

        expected = f"{message}\nIssue: GA-5678\n" if issue_trailer else message
        assert message_file.read_text(encoding="utf-8") == expected

    @pytest.mark.parametrize("issue_trailer", [False, True])
    @pytest.mark.parametrize(
        "subject",
        [
            "fixup! 1234abcd",
            "squash! Short",
            "amend! Short",
            "fixup! fixup! Short",
        ],
    )
    def test_bang_targets_are_exempt_from_summary_length(
        self, tmp_path: Path, mock_get_branch_name, subject: str, issue_trailer: bool
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = f"{subject}\n"
        if issue_trailer:
            message += "\nIssue: GA-5678\n"
        message_file.write_text(message, encoding="utf-8")

        assert check_commit_message(str(message_file), issue_trailer=issue_trailer) == (
            True,
            "",
        )

    @pytest.mark.parametrize("issue_trailer", [False, True])
    @pytest.mark.parametrize("branch", ["feature_branch", "GI-1234", "GA-5678"])
    def test_bang_prefix_does_not_bypass_jira_validation(
        self, tmp_path: Path, mock_get_branch_name, branch: str, issue_trailer: bool
    ):
        mock_get_branch_name(branch)
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = (
            "fixup! fixup! Short\n\nIssue: GI-1234\n"
            if issue_trailer
            else "fixup! fixup! [GI-1234] Short\n"
        )
        message_file.write_text(message, encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=issue_trailer
        )

        if branch != "GA-5678":
            assert is_valid
            assert error_message == ""
        else:
            assert not is_valid
            assert error_message.startswith("Different JIRA ID")

    @pytest.mark.parametrize("issue_trailer", [False, True])
    @pytest.mark.parametrize(
        "subject", ["fixup! Merge another branch", "fixup! Original target"]
    )
    def test_bang_still_requires_jira(
        self, tmp_path: Path, mock_get_branch_name, issue_trailer: bool, subject: str
    ):
        mock_get_branch_name("feature_branch")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message_file.write_text(f"{subject}\n", encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=issue_trailer
        )

        assert not is_valid
        assert error_message.startswith("Either the branch name")

    @pytest.mark.parametrize("issue_trailer", [False, True])
    @pytest.mark.parametrize("subject", ["custom! X", "fixup!X", "Short"])
    def test_non_autosquash_subjects_still_require_minimum_length(
        self, tmp_path: Path, mock_get_branch_name, subject: str, issue_trailer: bool
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = f"{subject}\n"
        if issue_trailer:
            message += "\nIssue: GA-5678\n"
        message_file.write_text(message, encoding="utf-8")

        is_valid, error_message = check_commit_message(
            str(message_file), issue_trailer=issue_trailer
        )

        assert not is_valid
        assert error_message.startswith("First line of commit message must be at least")

    def test_leading_blank_and_comments_do_not_hide_bang(
        self, tmp_path: Path, mock_get_branch_name
    ):
        mock_get_branch_name("GA-5678")
        message_file = tmp_path / "COMMIT_EDITMSG"
        message = "# Template comment\n\nfixup! Original target without a ticket\n"
        message_file.write_text(message, encoding="utf-8")

        prepare_commit_msg(str(message_file))

        assert message_file.read_text(encoding="utf-8") == message
