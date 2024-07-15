MiraGeoscience-Pre-Commit Hooks
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
   in case it is missing from the commit message.
-  ``check-commit-message``: Checks that the branch name or the commit
   message starts with a reference to JIRA, and if the message meets the
   minimum required length for the summary line. Also checks that the JIRA ID in
   the commit message is consistant with the one extracted from the
   branch name (if any).

Usage
^^^^^

Example of ``.pre-commit-config.yamnl``:

.. code:: yaml

   - repo: http://github.com/MiraGeoscience/mirageoscience-pre-commit-hooks
     rev: <release>
     hooks:
     - id: check-copyright
       types: [text]
       files: (^LICENSE|^README(|-dev).rst|\.py|\.pyi)$
       exclude: (^\.|^docs/)
     - id: prepare-commit-msg
     - id: check-commit-msg

License
^^^^^^^

MIT License

Copyright (c) 2024 Mira Geoscience

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
Copyright (c) 2024 Mira Geoscience Ltd.
