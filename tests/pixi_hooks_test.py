# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                      '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import sys

import pytest

from mirageoscience.hooks.check_pixi_lock import (
    LockOptions,
    validate_lock,
)
from mirageoscience.hooks.check_pixi_lock import (
    main as check_pixi_lock_main,
)
from mirageoscience.hooks.check_recipe import (
    RecipeOptions,
    validate_recipe,
)
from mirageoscience.hooks.check_recipe import (
    main as check_recipe_main,
)


def _lock_fixture(
    *,
    features: list[str],
    pypi_names: tuple[str, ...] = (),
) -> tuple[dict, dict]:
    pixi = {
        "feature": {
            "mira-pypi": {
                "pypi-dependencies": {"mira-package": "*"},
            },
        },
        "environments": {"default": {"features": features}},
    }
    packages = [
        {"pypi": f"https://pypi.org/simple/{name}/", "name": name}
        for name in pypi_names
    ]
    entries = [{"pypi": package["pypi"]} for package in packages]
    lock = {
        "packages": packages,
        "environments": {"default": {"packages": {"win-64": entries}}},
    }
    return pixi, lock


def _multiline_pixi_manifest() -> str:
    return """\
[workspace.conda-pypi-map]
"https://example.org/conda" = {
    mapping-mode = "overlay",
    mapping = {
        gempy = "gempy",
        gempy-engine = "gempy-engine",
    },
}

[constraints]
filelock = ">=4.2.1"

[feature.mira-pypi]
pypi-dependencies = {}
"""


def test_recipe_main_parses_toml_11_inline_tables(tmp_path, monkeypatch, capsys):
    pixi_file = tmp_path / "pixi.toml"
    recipe_file = tmp_path / "recipe.yaml"
    project_file = tmp_path / "pyproject.toml"
    pixi_file.write_text(_multiline_pixi_manifest(), encoding="utf-8")
    recipe_file.write_text(
        "requirements:\n  run_constraints:\n    - filelock >=4.2.1\n",
        encoding="utf-8",
    )
    project_file.write_text("[project]\ndependencies = []\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check-recipe",
            "--pixi-file",
            str(pixi_file),
            "--recipe-file",
            str(recipe_file),
            "--project-file",
            str(project_file),
        ],
    )

    assert check_recipe_main() == 0
    assert "Recipe constraints match" in capsys.readouterr().out


def test_pixi_lock_main_parses_toml_11_inline_tables(tmp_path, monkeypatch, capsys):
    pixi_file = tmp_path / "pixi.toml"
    lock_file = tmp_path / "pixi.lock"
    pixi_file.write_text(_multiline_pixi_manifest(), encoding="utf-8")
    lock_file.write_text(
        "packages: []\nenvironments:\n  default:\n    packages:\n      win-64: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check-pixi-lock",
            "--pixi-file",
            str(pixi_file),
            "--lock-file",
            str(lock_file),
            "--pypi-feature",
            "mira-pypi",
        ],
    )

    assert check_pixi_lock_main() == 0
    assert "Pixi lock package sources match" in capsys.readouterr().out


def test_pypi_packages_are_forbidden_without_feature():
    pixi, lock = _lock_fixture(features=[], pypi_names=("mira-package",))

    errors = validate_lock(pixi, lock, LockOptions(pypi_feature="mira-pypi"))

    assert any("without the 'mira-pypi' feature" in error for error in errors)


def test_strict_pypi_rejects_transitive_packages_for_standalone_packages():
    pixi, lock = _lock_fixture(
        features=["mira-pypi"],
        pypi_names=("mira-package", "transitive-dependency"),
    )

    errors = validate_lock(
        pixi,
        lock,
        LockOptions(pypi_feature="mira-pypi", strict_pypi=True),
    )

    assert any("expected exactly PyPI packages" in error for error in errors)


def test_non_strict_pypi_allows_transitive_packages_for_meta_packages():
    pixi, lock = _lock_fixture(
        features=["mira-pypi"],
        pypi_names=("mira-package", "transitive-dependency"),
    )

    errors = validate_lock(pixi, lock, LockOptions(pypi_feature="mira-pypi"))

    assert not errors


def test_pypi_source_validation_defaults_to_mira_git_urls():
    index = "https://packages.example.org/simple"
    git_url = "git+https://github.com/MiraGeoscience/mira-package.git"
    pixi, lock = _lock_fixture(
        features=["mira-pypi"],
        pypi_names=("mira-package", "mira-git-package"),
    )
    pixi["feature"]["mira-pypi"]["pypi-options"] = {"index-url": index}
    pixi["feature"]["mira-pypi"]["pypi-dependencies"]["mira-git-package"] = "*"
    lock["packages"][0]["pypi"] = f"{index.removesuffix('/simple')}/mira-package.whl"
    lock["packages"][1]["pypi"] = git_url
    lock["environments"]["default"]["indexes"] = [index]
    lock["environments"]["default"]["packages"]["win-64"] = [
        {"pypi": package["pypi"]} for package in lock["packages"]
    ]

    errors = validate_lock(
        pixi,
        lock,
        LockOptions(
            pypi_feature="mira-pypi",
            strict_pypi=True,
            validate_pypi_sources=True,
        ),
    )

    assert not errors


@pytest.mark.parametrize(
    "git_url",
    [
        "git+https://github.com/MiraGeoscience/../attacker/package.git",
        "git+https://github.com/MiraGeoscience/%2e%2e/attacker/package.git",
        "git+https://github.com/MiraGeoscience/%252e%252e/attacker/package.git",
        "git+https://github.com/MiraGeoscience/%2f..%2fattacker/package.git",
        "git+https://github.com/MiraGeoscience/%252f..%252fattacker/package.git",
        "git+https://github.com/MiraGeoscience/%5c..%5cattacker/package.git",
        "git+https://github.com/MiraGeoscience/package%0a.git",
        "git+https://github.com/MiraGeoscience/..\\attacker/package.git",
    ],
)
def test_pypi_source_validation_rejects_git_path_traversal(git_url):
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    lock["packages"][0]["pypi"] = git_url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": git_url}]

    errors = validate_lock(
        pixi, lock, LockOptions("mira-pypi", validate_pypi_sources=True)
    )

    assert any("unexpected Git source" in error for error in errors)


def test_pypi_source_validation_matches_git_host_for_custom_prefix():
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    url = "git+https://github.com.evil.example/MiraGeoscience/package.git"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    options = LockOptions(
        "mira-pypi",
        validate_pypi_sources=True,
        git_url_prefixes=("git+https://github.com",),
    )
    assert any(
        "unexpected Git source" in error for error in validate_lock(pixi, lock, options)
    )

    url = "git+https://github.com/other/package%2dname.git@v1.0#subdirectory=python"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    assert not validate_lock(pixi, lock, options)


def test_target_specific_feature_dependencies_are_checked_per_platform():
    pixi, lock = _lock_fixture(features=["mira-pypi", "conda-rt"])
    pixi["feature"]["mira-pypi"] = {
        "target": {
            "win-64": {"pypi-dependencies": {"win-package": "*"}},
            "linux": {"pypi-dependencies": {"linux-package": "*"}},
        }
    }
    pixi["feature"]["conda-rt"] = {
        "dependencies": {"base-package": "*"},
        "target": {"win-64": {"dependencies": {"win-conda": "*"}}},
    }
    win_url = "https://example.org/win.whl"
    linux_url = "https://example.org/linux.whl"
    lock["packages"] = [
        {"pypi": win_url, "name": "win-package"},
        {"pypi": linux_url, "name": "linux-package"},
    ]
    base = {"conda": "https://example.org/base-package-1-0.conda"}
    win = {"conda": "https://example.org/win-conda-1-0.conda"}
    lock["environments"]["default"]["packages"] = {
        "win-64": [{"pypi": win_url}, base, win],
        "linux-64": [{"pypi": linux_url}, base],
    }
    options = LockOptions("mira-pypi", conda_feature="conda-rt", strict_pypi=True)

    assert not validate_lock(pixi, lock, options)
    lock["environments"]["default"]["packages"]["win-64"].remove(win)
    assert any("win-conda" in error for error in validate_lock(pixi, lock, options))


@pytest.mark.parametrize("configured", [True, False])
def test_pypi_source_validation_accepts_public_pypi_artifact_host(configured):
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    if configured:
        pixi["feature"]["mira-pypi"]["pypi-options"] = {
            "index-url": "https://pypi.org/simple"
        }
    url = "https://files.pythonhosted.org/packages/mira-package.whl"
    lock["packages"][0]["pypi"] = url
    if configured:
        lock["environments"]["default"]["indexes"] = ["https://pypi.org/simple"]
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    options = LockOptions("mira-pypi", validate_pypi_sources=True)

    assert not validate_lock(pixi, lock, options)
    url = "https://files.pythonhosted.org.evil.example/package.whl"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    assert any(
        "unexpected PyPI source" in error
        for error in validate_lock(pixi, lock, options)
    )


def test_pypi_source_validation_inherits_workspace_index_options():
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    index = "https://packages.example.org/simple"
    url = "https://packages.example.org/packages/mira-package.whl"
    pixi["pypi-options"] = {"index-url": index}
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["indexes"] = [index]
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    options = LockOptions("mira-pypi", validate_pypi_sources=True)

    assert not validate_lock(pixi, lock, options)
    url = "https://files.pythonhosted.org/packages/mira-package.whl"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    assert any(
        "unexpected PyPI source" in error
        for error in validate_lock(pixi, lock, options)
    )


def test_pypi_source_validation_ignores_inactive_index_feature():
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    pixi["feature"]["mira-pypi-index"] = {
        "pypi-options": {"index-url": "https://packages.example.org/simple"}
    }
    url = "https://files.pythonhosted.org/packages/mira-package.whl"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    options = LockOptions(
        "mira-pypi",
        pypi_index_feature="mira-pypi-index",
        validate_pypi_sources=True,
    )

    assert not validate_lock(pixi, lock, options)


def test_pypi_source_validation_accepts_configured_artifact_root():
    pixi, lock = _lock_fixture(features=["mira-pypi"], pypi_names=("mira-package",))
    pixi["feature"]["mira-pypi"]["pypi-options"] = {
        "index-url": "https://index.example/simple"
    }
    url = "https://artifacts.example/packages/mira-package.whl"
    lock["packages"][0]["pypi"] = url
    lock["environments"]["default"]["indexes"] = ["https://index.example/simple"]
    lock["environments"]["default"]["packages"]["win-64"] = [{"pypi": url}]
    options = LockOptions("mira-pypi", validate_pypi_sources=True)
    assert any(
        "unexpected PyPI source" in error
        for error in validate_lock(pixi, lock, options)
    )
    options = LockOptions(
        "mira-pypi",
        validate_pypi_sources=True,
        artifact_source_roots=("https://artifacts.example/packages",),
    )
    assert not validate_lock(pixi, lock, options)


@pytest.mark.parametrize("environments", [None, {"other": []}])
def test_implicit_default_environment_and_unknown_named_environment(environments):
    pixi, lock = _lock_fixture(features=[])
    if environments is None:
        del pixi["environments"]
    else:
        pixi["environments"] = environments
    assert not validate_lock(pixi, lock, LockOptions("mira-pypi"))
    lock["environments"]["unknown"] = lock["environments"]["default"]
    assert any(
        "unknown: missing" in error
        for error in validate_lock(pixi, lock, LockOptions("mira-pypi"))
    )


def test_pixi_lock_main_reports_validation_errors(tmp_path, monkeypatch, capsys):
    pixi_file = tmp_path / "pixi.toml"
    lock_file = tmp_path / "pixi.lock"
    pixi_file.write_text(_multiline_pixi_manifest(), encoding="utf-8")
    lock_file.write_text(
        "packages: []\nenvironments:\n  default:\n    packages:\n      win-64: []\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check-pixi-lock",
            "--pixi-file",
            str(pixi_file),
            "--lock-file",
            str(lock_file),
            "--pypi-feature",
            "missing-feature",
        ],
    )

    assert check_pixi_lock_main() == 1
    assert "Pixi feature 'missing-feature' is not defined" in capsys.readouterr().err


def test_recipe_checks_constraints_and_optional_pytorch():
    pixi = {
        "constraints": {"filelock": ">=4.2.1"},
        "feature": {},
    }
    recipe = {
        "requirements": {
            "run": ["python >=3.12"],
            "run_constraints": ["filelock >=4.2.1"],
        }
    }

    options = RecipeOptions(check_pytorch=True)
    errors = validate_recipe(pixi, recipe, {}, options)

    assert not errors
    recipe["requirements"]["run"].append("pytorch-cpu >=2.0")
    errors = validate_recipe(pixi, recipe, {}, options)
    assert any("PyTorch backend selection" in error for error in errors)
    assert not validate_recipe(pixi, recipe, {}, RecipeOptions())


@pytest.mark.parametrize(
    "dependency",
    [
        "pytorch",
        "pytorch >=2.13.0,<2.15.0",
        "conda-forge::pytorch >=2.13.0, <2.15.0",
        "pytorch=2.14",
        "pytorch-lightning >=2.0",
    ],
)
def test_recipe_allows_backend_neutral_pytorch(dependency):
    recipe = {"requirements": {"run": [dependency]}}
    assert not validate_recipe({}, recipe, {}, RecipeOptions(check_pytorch=True))


@pytest.mark.parametrize(
    "dependency",
    [
        "pytorch-cpu >=2.0",
        "conda-forge::pytorch_gpu >=2.0",
        "pytorch-cuda >=12",
        "cpuonly",
        "pytorch >=2.0 cpu*",
        "pytorch=2.14=*cuda*",
        "pytorch[version='>=2.0',build='cuda*']",
        "pytorch-mutex 1.0 cuda",
    ],
)
def test_recipe_rejects_pytorch_backend_selection(dependency):
    recipe = {"requirements": {"run": [dependency]}}
    errors = validate_recipe({}, recipe, {}, RecipeOptions(check_pytorch=True))
    assert any("PyTorch backend selection" in error for error in errors)
    assert not validate_recipe({}, recipe, {}, RecipeOptions())


def test_recipe_rejects_pytorch_backend_run_constraint():
    recipe = {"requirements": {"run_constraints": ["pytorch >=2.0 cpu*"]}}
    errors = validate_recipe({}, recipe, {}, RecipeOptions(check_pytorch=True))
    assert any("PyTorch backend selection" in error for error in errors)


def test_recipe_infers_feature_constraint_source_and_floor():
    pixi: dict = {
        "constraints": {"filelock": ">=4.2.1", "setuptools": ">=84.1.0"},
        "feature": {
            "conda-rt": {
                "dependencies": {
                    "pillow": "13.*",
                }
            }
        },
    }
    recipe = {
        "requirements": {
            "run": ["python >=3.12"],
            "run_constraints": [
                "filelock >=4.2.1",
                "pillow >=13.0.0",
                "setuptools >=84.1.0",
            ],
        }
    }

    errors = validate_recipe(pixi, recipe, {}, RecipeOptions())

    assert not errors

    pixi["feature"]["conda-rt"]["dependencies"]["pillow"] = "12.*"
    errors = validate_recipe(pixi, recipe, {}, RecipeOptions())
    assert any("pillow" in error for error in errors)


@pytest.mark.parametrize(
    ("recipe_constraint", "pixi_constraint"),
    [("urllib3>=2.5", ">=2.5"), ("urllib3=2.5", "=2.5")],
)
def test_recipe_parses_conda_constraints_without_spaces(
    recipe_constraint, pixi_constraint
):
    pixi = {"constraints": {"urllib3": pixi_constraint}}
    recipe = {"requirements": {"run_constraints": [recipe_constraint]}}

    assert not validate_recipe(pixi, recipe, {}, RecipeOptions())


def test_recipe_reads_conditional_run_constraints():
    pixi = {"constraints": {"filelock": ">=4.2.1"}}
    recipe = {
        "requirements": {
            "run": ["python >=3.12"],
            "run_constraints": [{"if": "win", "then": "filelock >=4.2.1"}],
        }
    }

    assert not validate_recipe(pixi, recipe, {}, RecipeOptions())


def test_recipe_accepts_inline_versions_but_rejects_versionless_dependencies():
    pixi = {
        "feature": {
            "conda-rt": {
                "dependencies": {
                    "pillow": {"version": "13.*", "channel": "conda-forge"}
                }
            }
        }
    }
    recipe = {"requirements": {"run_constraints": ["pillow >=13.0.0"]}}
    assert not validate_recipe(pixi, recipe, {}, RecipeOptions())
    pixi["feature"]["conda-rt"]["dependencies"]["pillow"] = {"path": "../pillow"}
    assert any(
        "pillow" in error
        for error in validate_recipe(pixi, recipe, {}, RecipeOptions())
    )


@pytest.mark.parametrize("section", ["root", "feature"])
def test_recipe_rejects_target_specific_direct_security_dependencies(section):
    pixi: dict = {"constraints": {"filelock": ">=4.2.1"}}
    target = {"win-64": {"dependencies": {"filelock": "*"}}}
    if section == "root":
        pixi["target"] = target
    else:
        pixi["feature"] = {"extra": {"target": target}}
    recipe = {"requirements": {"run_constraints": ["filelock >=4.2.1"]}}
    assert any(
        "not direct dependencies" in error
        for error in validate_recipe(pixi, recipe, {}, RecipeOptions())
    )


def test_recipe_applies_aliases_to_feature_dependencies():
    pixi = {
        "constraints": {"pytorch": ">=2.0"},
        "feature": {"extra": {"pypi-dependencies": {"torch": "*"}}},
    }
    recipe = {"requirements": {"run_constraints": ["pytorch >=2.0"]}}
    assert any(
        "not direct dependencies" in error
        for error in validate_recipe(
            pixi, recipe, {}, RecipeOptions(package_aliases=("torch=pytorch",))
        )
    )
