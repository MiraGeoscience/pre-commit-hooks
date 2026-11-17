#!/usr/bin/env python3

# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                     '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

"""Some Git pre-commit hooks implementations."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys


_TRAILER_LINE = re.compile(r"([A-Za-z0-9-]+)[ \t]*:[ \t]*(.*)")


def get_jira_id(text) -> str:
    """Detect a JIRA issue ID at the begging of the given text.

    :return: the JIRA issue ID if found, else empty string
    """

    class JiraPattern:
        """Internal class that encapsulates the regular expression for the JIRA pattern,
        making sure it gets compiled only once."""

        __pattern = re.compile(
            r"(?:\w*!)?\s*\S?\b((?:GEOPY|GI|GA|GMS|VPem1D|VPem3D|VPmg|UBCGIF|LICMGR|DEVOPS|QA)-\d+)"
        )

        @staticmethod
        def get():
            """:return: the compiled regular expression for the JIRA pattern"""
            return JiraPattern.__pattern

    # use re.match() rather than re.search() to enforce the JIRA reference to be at the beginning
    match = re.match(JiraPattern.get(), text.strip())
    return match.group(1) if match else ""


def get_message_prefix_bang(line: str) -> str:
    """Capture Git autosquash prefixes, including nested fixup!, squash!, and amend!.

    :return: the standard commit message prefix if found, else empty string.
    """

    class BangPattern:
        """Internal class that encapsulates the regular expression for the bang pattern,
        making sure it gets compiled only once."""

        __pattern = re.compile(r"((?:(?:fixup|squash|amend)! )+)")

        @staticmethod
        def get():
            """:return: the compiled regular expression for the JIRA pattern"""
            return BangPattern.__pattern

    # use re.match() rather than re.search() to enforce pattern at the beginning
    match = re.match(BangPattern.get(), line.strip())
    return match.group(1) if match else ""


def _get_git_dir() -> pathlib.Path | None:
    """Resolve the actual git directory, handling GIT_DIR and worktrees.

    In a normal repo, `.git` is a directory.
    In a worktree, `.git` is a file containing "gitdir: <path>".
    """
    git_dir = os.environ.get("GIT_DIR")
    if git_dir:
        return pathlib.Path(git_dir).resolve()

    git_path = pathlib.Path(".git")
    if not git_path.exists():
        return None
    if git_path.is_dir():
        return git_path.resolve()
    # worktree: .git is a file
    content = git_path.read_text(encoding="utf-8").strip()
    if content.startswith("gitdir:"):
        git_dir_path = pathlib.Path(content[len("gitdir:") :].strip())
        if not git_dir_path.is_absolute():
            git_dir_path = git_path.parent / git_dir_path
        return git_dir_path.resolve()
    return None


def _is_rebase_in_progress() -> bool:
    """Return whether Git has an active rebase state directory."""
    git_dir = _get_git_dir()
    return git_dir is not None and any(
        (git_dir / rebase_dir).is_dir()
        for rebase_dir in ("rebase-merge", "rebase-apply")
    )


def _is_replay_in_progress() -> bool:
    """Return whether Git is rebasing or cherry-picking a commit."""
    git_dir = _get_git_dir()
    return _is_rebase_in_progress() or (
        git_dir is not None and (git_dir / "CHERRY_PICK_HEAD").is_file()
    )


def get_branch_name() -> str | None:
    """:return: the name of the current branch"""
    git_dir = _get_git_dir()
    if git_dir is None:
        return None

    head_file = git_dir / "HEAD"
    if not head_file.exists():
        return None

    content = head_file.read_text(encoding="utf-8").strip()
    if content.startswith("ref: refs/heads/"):
        return content[len("ref: refs/heads/") :]

    # Detached HEAD or active rebase: check rebase state files
    for rebase_dir in ("rebase-merge", "rebase-apply"):
        head_name_file = git_dir / rebase_dir / "head-name"
        if head_name_file.exists():
            ref = head_name_file.read_text(encoding="utf-8").strip()
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/") :]

    return None  # detached HEAD with no active rebase


def _get_trailer_block(lines: list[str]) -> tuple[int, int]:
    """Find the final trailer paragraph before template comments or patch text."""
    end = len(lines)
    for index, line in enumerate(lines):
        if (
            line.rstrip("\r\n") == "---"
            or line.startswith("# ------------------------ >8 ")
            or line.startswith("diff --git ")
        ):
            end = index
            break
    while end and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
        end -= 1
    start = end
    while start and lines[start - 1].strip():
        start -= 1
    if start == 0:
        return end, end

    has_trailer = False
    for line in lines[start:end]:
        if line.startswith("#"):
            continue
        if _TRAILER_LINE.fullmatch(line.rstrip("\r\n")):
            has_trailer = True
        elif not (has_trailer and line.startswith((" ", "\t"))):
            return end, end
    return (start, end) if has_trailer else (end, end)


def _get_issue_trailers(message: str) -> list[str]:
    """Read Issue values from the final block of colon-separated trailers."""
    lines = message.splitlines(keepends=True)
    start, end = _get_trailer_block(lines)
    issues = []
    current_issue = False
    for line in lines[start:end]:
        if line.startswith("#"):
            continue
        match = _TRAILER_LINE.fullmatch(line.rstrip("\r\n"))
        if match:
            current_issue = match.group(1).lower() == "issue"
            if current_issue:
                issues.append(match.group(2).strip())
        elif current_issue:
            issues[-1] = f"{issues[-1]} {line.strip()}".strip()
    return issues


def _prepare_issue_trailer(filepath: str, branch_jira_id: str) -> None:
    """Append a missing Issue trailer without changing the commit subject."""
    message_path = pathlib.Path(filepath)
    message = message_path.read_text(encoding="utf-8")
    if _get_issue_trailers(message):
        return

    lines = message.splitlines(keepends=True)
    start, end = _get_trailer_block(lines)
    prefix = "".join(lines[:end]).rstrip("\r\n")
    suffix = "".join(lines[end:]).lstrip("\r\n")
    separator = "\n\n" if start == end else "\n"
    message_path.write_text(
        f"{prefix}{separator}Issue: {branch_jira_id}\n{suffix}", encoding="utf-8"
    )


def check_commit_message(
    filepath: str, *, issue_trailer: bool = False
) -> tuple[bool, str]:
    """Check if the branch name or the commit message starts with a reference to JIRA,
    and if the message meets the minimum required length for the summary line.

    The JIRA reference has to be at the beginning of the branch name, or of the commit
    message, or in an Issue trailer when issue_trailer is enabled. Summary length
    is not checked for autosquash targets or during a rebase or cherry-pick.
    :return: a tuple telling whether the commit message is valid or not, and an error
        message (empty in case the message is valid).
    """

    branch_jira_id = ""
    branch_name = get_branch_name()
    if branch_name:
        branch_jira_id = get_jira_id(branch_name)

    first_line = None
    with open(filepath, encoding="utf-8") as message_file:
        message = message_file.read()
    for line in message.splitlines():
        # In trailer mode, a blank subject must not make its footer count as the summary.
        if not line.startswith("#") and (issue_trailer or len(line.strip()) > 0):
            first_line = line.strip()
            prefix_bang = get_message_prefix_bang(first_line)
            first_line = first_line[len(prefix_bang) :].strip()
            break
    assert first_line is not None

    if issue_trailer:
        message_jira_ids = _get_issue_trailers(message)
        if any(not value or get_jira_id(value) != value for value in message_jira_ids):
            return False, "Each Issue trailer must contain a valid JIRA ID."
    else:
        header_jira_id = get_jira_id(first_line)
        message_jira_ids = [header_jira_id] if header_jira_id else []
    message_jira_id = next(
        (jira_id for jira_id in message_jira_ids if jira_id != branch_jira_id),
        message_jira_ids[0] if message_jira_ids else "",
    )

    if (
        not branch_jira_id
        and not (
            message_jira_id
            or (not prefix_bang and first_line.lower().startswith("merge"))
        )
        and not _is_rebase_in_progress()
    ):
        return (
            False,
            (
                "Either the branch name must start with a JIRA ID "
                "or the commit message must contain an Issue trailer with a JIRA ID."
                if issue_trailer
                else "Either the branch name or the commit message must start with a JIRA ID."
            ),
        )

    if (
        branch_jira_id
        and message_jira_id
        and branch_jira_id != message_jira_id
        and not _is_replay_in_progress()
    ):
        location = "Issue trailer" if issue_trailer else "commit message"
        return (
            False,
            f"Different JIRA ID in {location} {message_jira_id} "
            f"and in branch name {branch_jira_id}.",
        )

    stripped_message_line = ""
    if first_line:
        stripped_message_line = first_line.strip()
        if message_jira_id and not issue_trailer:
            stripped_message_line = stripped_message_line[
                len(message_jira_id) + 1 :
            ].strip()

    min_required_length = 10
    if (
        len(stripped_message_line) < min_required_length
        and not prefix_bang
        and not _is_replay_in_progress()
    ):
        return (
            False,
            f"First line of commit message must be at least {min_required_length} characters long, "
            + ("in the subject." if issue_trailer else "beyond the JIRA ID."),
        )

    return True, ""


def check_commit_msg(filepath: str, *, issue_trailer: bool = False) -> None:
    """To be used as the Git commit-msg hook.

    Exit with non-0 status if the commit message is deemed invalid.
    """

    (is_valid, error_message) = check_commit_message(
        filepath, issue_trailer=issue_trailer
    )
    if not is_valid:
        print(
            f"""commit-msg hook: **ERROR** {error_message}
            Message has been saved to {filepath}."""
        )
        sys.exit(1)


def prepare_commit_msg(
    filepath: str,
    source: str | None = None,
    _commit_id: str | None = None,
    *,
    issue_trailer: bool = False,
) -> None:
    """To be used as the Git prepare-commit-msg hook.

    Will add the JIRA ID found in the branch name in case it is missing from the commit
    message. During a rebase or cherry-pick, this also handles reused commit messages
    and preserves any JIRA ID already in that message. Git may supply an unused
    third argument identifying the original commit.

    With issue_trailer enabled, use an Issue trailer instead of the subject line.
    Autosquash target subjects are never modified.
    """

    branch_jira_id = ""
    branch_name = get_branch_name()
    if branch_name:
        branch_jira_id = get_jira_id(branch_name)

    if not branch_jira_id:
        return

    if source not in [None, "message", "template"] and not (
        source in ["commit", "merge"] and _is_replay_in_progress()
    ):
        return

    if issue_trailer:
        _prepare_issue_trailer(filepath, branch_jira_id)
        return

    with open(filepath, "r+", encoding="utf-8") as message_file:
        message_has_jira_id = False
        message_lines = message_file.readlines()
        for line_index, line_content in enumerate(message_lines):
            if not line_content.startswith("#") and line_content.strip():
                line_content = line_content.strip()
                if get_message_prefix_bang(line_content):
                    # Preserve the exact autosquash target; inserting an ID would break matching.
                    # Validation still checks the existing subject ID or the branch ID.
                    return
                message_jira_id = get_jira_id(line_content)
                if not message_jira_id:
                    message_lines[line_index] = f"[{branch_jira_id}] {line_content}\n"
                message_has_jira_id = True
                break

        if not message_has_jira_id:
            # message is empty or all lines are comments: insert JIRA ID at the very beginning
            message_lines.insert(0, f"[{branch_jira_id}]\n")

        message_file.seek(0, 0)
        message_file.write("".join(message_lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("msg_file", help="the message file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-p", "--prepare", action="store_true", help="prepare the commit message"
    )
    group.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="check if the commit message is valid",
    )
    parser.add_argument(
        "--issue-trailer",
        action="store_true",
        help="use an Issue trailer for the JIRA ID instead of the commit subject",
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    if args.prepare:
        prepare_commit_msg(args.msg_file, *args.args, issue_trailer=args.issue_trailer)
    elif args.check:
        check_commit_msg(args.msg_file, issue_trailer=args.issue_trailer)
