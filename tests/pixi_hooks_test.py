# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                      '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

from mirageoscience.hooks.check_pixi_lock import LockOptions, validate_lock
from mirageoscience.hooks.check_recipe import RecipeOptions, validate_recipe


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
