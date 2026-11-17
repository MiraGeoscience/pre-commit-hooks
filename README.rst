MiraGeoscience.Pre-Commit Hooks
===============================

This repository provides a collection of pre-commit hooks to automate
essential checks and streamline your development workflow. By utilizing
these hooks, you can maintain code quality and consistency across your
projects, fostering a more efficient and collaborative development
environment.

Included Hooks
^^^^^^^^^^^^^^

-  ``check-copyright``: Checks for valid copyright statements in files.
-  ``prepare-commit-msg``: Adds the JIRA ID found in the branch name
   in case it is missing from the commit message, including during a rebase or
   cherry-pick. Existing JIRA IDs in replayed commit messages are preserved.
-  ``check-commit-message``: Checks that the branch name or the commit
   message starts with a reference to JIRA, and if the message meets the
   minimum required length for the summary line. Also checks that the JIRA ID in
   the commit message is consistEnt with the one extracted from the
   branch name (if any), except during a rebase or cherry-pick where original
   commit messages may have a different JIRA ID. During a rebase, a JIRA ID is
   also optional when neither the branch nor the commit message supplies one.
   Minimum summary length is not enforced during rebases or cherry-picks.

Usage
^^^^^

Example of ``.pre-commit-config.yamnl``:

.. code:: yaml

   repos:
   -  repo: http://github.com/MiraGeoscience/pre-commit-hooks
      rev: <release>
      hooks:
      -  id: check-copyright
         types: [text]
         files: (^LICENSE|^README(|-dev).rst|\.py|\.pyi)$
         exclude: (^\.|^docs/)
      -  id: prepare-commit-msg
      -  id: check-commit-msg

Issue trailers
^^^^^^^^^^^^^^

By default, the message hooks use a JIRA ID at the beginning of the commit
subject. To use an ``Issue: GA-1234`` footer trailer instead, enable
``--issue-trailer`` on both hooks:

.. code:: yaml

   hooks:
   -  id: prepare-commit-msg
      args: [--issue-trailer]
   -  id: check-commit-msg
      args: [--issue-trailer]

For example, a prepared message would be:

.. code:: text

   Fix the coordinate transformation

   Explain the change here.

   Issue: GA-1234

In this mode, preparation leaves the subject unchanged and adds the branch's
JIRA ID as an Issue trailer only when no Issue trailer already exists. Existing
trailers and the message body are retained.
Trailers form the final block of colon-separated fields, separated from the subject
or body by a blank line; indented continuation lines are supported.
An ID in the subject, body, ``#`` template comments, or patch text does not count
as an Issue trailer.

The hooks handle trailers directly in Python, without starting Git. They use
fixed ``Issue:`` syntax and do not read Git's ``trailer.*`` configuration settings
for custom keys, separators, insertion order, duplicate handling, or commands
that generate trailer values. No Git trailer configuration is required.
Those settings still apply when using Git's own trailer commands.

Validation uses Issue trailers instead of subject prefixes. Each Issue trailer
must contain a valid JIRA ID, and IDs must match the branch's ID when one exists,
except during rebases or cherry-picks. As in subject mode, the branch's ID alone
can satisfy the JIRA requirement. Summary length is measured on the subject
without counting trailer text. The existing rebase and cherry-pick exceptions
apply in both modes.

Autosquash commits
^^^^^^^^^^^^^^^^^^

The Git prefixes ``fixup!``, ``squash!``, and ``amend!`` identify autosquash
targets, including when those prefixes are nested. The hooks preserve the exact
target subject so that ``git rebase --autosquash`` can still match the original
commit. In header mode, no JIRA ID is inserted into these subjects; the branch's
JIRA ID can satisfy validation, and an existing ID after the bang prefixes is
still parsed and checked for consistency. In trailer mode, validation continues
to use the Issue trailer or branch, and a missing Issue trailer can still be
added without changing the subject.

Autosquash targets are exempt from the minimum summary length because they can
reference short original subjects or commit hashes. JIRA presence and consistency
checks still apply, subject to the existing rebase and cherry-pick exceptions.

License
^^^^^^^

MIT License

Copyright (c) 2024-2026 Mira Geoscience Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Copyright
^^^^^^^^^
Copyright (c) 2024-2026 Mira Geoscience Ltd.
