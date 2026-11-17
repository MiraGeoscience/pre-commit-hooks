# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                     '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from packaging.version import Version

from mirageoscience import hooks as mira_hooks


def _get_json_version() -> str:
    version_json_path = Path(__file__).resolve().parents[1] / "_version.json"
    with version_json_path.open(encoding="utf-8") as file:
        version_json = json.load(file)
    return version_json["version"]


def _version_module_exists():
    try:
        importlib.import_module("mirageoscience.hooks._version")
        return True
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(
    _version_module_exists(),
    reason="mirageoscience.hooks._version can be found: package is built",
)
def test_fallback_version_is_zero():
    project_version = Version(mira_hooks.__version__)
    fallback_version = Version("0.0.0.dev0")
    assert project_version.base_version == fallback_version.base_version
    assert project_version.pre is None
    assert project_version.post is None
    assert project_version.dev == fallback_version.dev


@pytest.mark.skipif(
    not _version_module_exists(),
    reason="mirageoscience.hooks._version cannot be found: uses a fallback version",
)
def test_version_json_is_consistent():
    project_version = Version(mira_hooks.__version__)
    json_version = Version(_get_json_version())
    assert project_version == json_version


def test_version_is_pep440():
    version = Version(mira_hooks.__version__)
    assert version is not None
