# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                      '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version


@dataclass(frozen=True)
class RecipeOptions:
    constraints_features: tuple[str, ...] = ()
    security_floors: tuple[str, ...] = ()
    allowed_direct_pixi: tuple[str, ...] = ()
    required_feature_dependencies: tuple[str, ...] = ()
    package_aliases: tuple[str, ...] = ()
    check_pytorch: bool = False


def _parse_constraint(value: str) -> tuple[str, str]:
    name, separator, specifier = value.strip().partition(" ")
    if not separator or not specifier.strip():
        raise ValueError(f"Invalid recipe run constraint: {value!r}")
    return canonicalize_name(name), specifier.strip()


def _parse_floor(value: str) -> tuple[str, Version]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)>=([A-Za-z0-9_.+-]+)", value)
    if match is None:
        raise ValueError(f"Invalid security floor {value!r}; expected package>=version")
    return canonicalize_name(match.group(1)), Version(match.group(2))


def _as_specifier_set(value: str) -> SpecifierSet:
    specifiers = []
    for specifier in value.split(","):
        specifier = specifier.strip()
        if not any(operator in specifier for operator in "<>=!~"):
            specifier = f"=={specifier}"
        specifiers.append(specifier)
    return SpecifierSet(",".join(specifiers))


def _project_dependency_names(project: dict) -> set[str]:
    project_data = project.get("project", {})
    dependencies = list(project_data.get("dependencies", []))
    for optional_dependencies in project_data.get("optional-dependencies", {}).values():
        dependencies.extend(optional_dependencies)
    return {
        canonicalize_name(Requirement(dependency).name) for dependency in dependencies
    }


def _pixi_direct_dependencies(pixi: dict) -> set[str]:
    direct_dependencies = set()
    for section in (pixi, *pixi.get("feature", {}).values()):
        for dependency_type in ("dependencies", "pypi-dependencies"):
            direct_dependencies.update(
                canonicalize_name(name)
                for name in section.get(dependency_type, {})
            )
    return direct_dependencies


def _package_aliases(values: tuple[str, ...]) -> dict[str, str]:
    aliases = {}
    for value in values:
        alias, separator, package = value.partition("=")
        if not separator or not alias or not package:
            raise ValueError(f"Invalid package alias {value!r}; expected alias=package")
        aliases[canonicalize_name(alias)] = canonicalize_name(package)
    return aliases


def _feature_dependency(pixi: dict, feature: str, package: str) -> str | None:
    feature_data = pixi.get("feature", {}).get(feature, {})
    for dependency_type in ("dependencies", "pypi-dependencies", "constraints"):
        dependencies = feature_data.get(dependency_type, {})
        for name, specifier in dependencies.items():
            if canonicalize_name(name) == package:
                return str(specifier)
    return None


def _pixi_constraints(
    pixi: dict, recipe_constraints: dict[str, str], features: tuple[str, ...]
) -> dict[str, str]:
    constraints = {
        canonicalize_name(name): str(specifier)
        for name, specifier in pixi.get("constraints", {}).items()
    }
    for feature in features:
        for package in recipe_constraints:
            if package not in constraints:
                specifier = _feature_dependency(pixi, feature, package)
                if specifier is not None:
                    constraints[package] = specifier
    return constraints


def _constraint_errors(
    recipe_constraints: dict[str, str],
    pixi_constraints: dict[str, str],
    options: RecipeOptions,
) -> list[str]:
    errors = []
    floors = dict(_parse_floor(value) for value in options.security_floors)
    if recipe_constraints.keys() != pixi_constraints.keys():
        errors.append(
            "recipe.yaml run_constraints must match Pixi constraints; "
            f"recipe={sorted(recipe_constraints)}, Pixi={sorted(pixi_constraints)}"
        )
    for package, recipe_specifier in recipe_constraints.items():
        pixi_specifier = pixi_constraints.get(package)
        if pixi_specifier is None:
            continue
        if recipe_specifier == pixi_specifier:
            continue
        floor = floors.get(package)
        if floor is None:
            errors.append(
                f"{package}: recipe constraint {recipe_specifier!r} does not match "
                f"Pixi constraint {pixi_specifier!r}"
            )
            continue
        if (
            floor not in _as_specifier_set(recipe_specifier)
            or floor not in _as_specifier_set(pixi_specifier)
        ):
            errors.append(
                f"{package}: recipe and Pixi constraints must both include "
                f"security floor {floor}"
            )
    for package, floor in floors.items():
        recipe_specifier = recipe_constraints.get(package)
        pixi_specifier = pixi_constraints.get(package)
        if recipe_specifier is None or floor not in _as_specifier_set(recipe_specifier):
            errors.append(
                f"{package}: recipe run_constraints must include security floor {floor}"
            )
        if pixi_specifier is None or floor not in _as_specifier_set(pixi_specifier):
            errors.append(
                f"{package}: Pixi constraints must include security floor {floor}"
            )
    return errors


def _required_feature_errors(pixi: dict, required: tuple[str, ...]) -> list[str]:
    errors = []
    required_dependencies = set()
    for value in required:
        feature, separator, package = value.partition(":")
        if not separator or not feature or not package:
            raise ValueError(
                f"Invalid required feature dependency {value!r}; "
                "expected feature:package"
            )
        required_dependencies.add((feature, canonicalize_name(package)))
    for feature, package in required_dependencies:
        if _feature_dependency(pixi, feature, package) is None:
            errors.append(
                f"Pixi feature {feature!r} must include dependency {package!r}"
            )
    return errors


def _transitivity_errors(
    pixi: dict,
    recipe: dict,
    project: dict,
    recipe_constraints: dict[str, str],
    options: RecipeOptions,
) -> list[str]:
    aliases = _package_aliases(options.package_aliases)
    security_packages = {
        aliases.get(package, package) for package in recipe_constraints
    }
    project_and_recipe_dependencies = _project_dependency_names(project)
    project_and_recipe_dependencies.update(
        canonicalize_name(
            value.split(maxsplit=1)[0].rsplit("::", 1)[-1]
        )
        for value in recipe["requirements"].get("run", [])
    )
    project_and_recipe_dependencies = {
        aliases.get(package, package) for package in project_and_recipe_dependencies
    }
    direct_security_dependencies = security_packages & project_and_recipe_dependencies
    errors = []
    if direct_security_dependencies:
        errors.append(
            "Security-floor packages must remain transitive in the published recipe "
            f"and project dependencies: {sorted(direct_security_dependencies)}"
        )
    allowed_pixi = {
        canonicalize_name(name) for name in options.allowed_direct_pixi
    }
    pixi_direct_dependencies = {
        aliases.get(package, package) for package in _pixi_direct_dependencies(pixi)
    }
    pixi_direct = security_packages & pixi_direct_dependencies
    disallowed_direct_pixi = pixi_direct - allowed_pixi
    if disallowed_direct_pixi:
        errors.append(
            "Security-floor packages must remain transitive Pixi dependencies: "
            f"{sorted(disallowed_direct_pixi)}"
        )
    return errors


def _pytorch_errors(recipe: dict) -> list[str]:
    packages = {
        canonicalize_name(value.split(maxsplit=1)[0].rsplit("::", 1)[-1])
        for value in recipe["requirements"].get("run", [])
    }
    pytorch_packages = sorted(
        package for package in packages if package.startswith("pytorch")
    )
    if not pytorch_packages:
        return []
    return [
        "recipe.yaml requirements.run must leave PyTorch backend selection "
        f"to the installer; found: {pytorch_packages}"
    ]


def validate_recipe(
    pixi: dict, recipe: dict, project: dict, options: RecipeOptions
) -> list[str]:
    recipe_constraints = dict(
        _parse_constraint(value)
        for value in recipe["requirements"].get("run_constraints", [])
    )
    pixi_constraints = _pixi_constraints(
        pixi, recipe_constraints, options.constraints_features
    )
    errors = _constraint_errors(recipe_constraints, pixi_constraints, options)
    errors.extend(_required_feature_errors(pixi, options.required_feature_dependencies))
    errors.extend(
        _transitivity_errors(pixi, recipe, project, recipe_constraints, options)
    )
    if options.check_pytorch:
        errors.extend(_pytorch_errors(recipe))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixi-file", type=Path, default=Path("pixi.toml"))
    parser.add_argument("--recipe-file", type=Path, default=Path("recipe.yaml"))
    parser.add_argument("--project-file", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--constraints-feature", action="append", default=[])
    parser.add_argument("--security-floor", action="append", default=[])
    parser.add_argument("--allow-direct-pixi", action="append", default=[])
    parser.add_argument("--require-feature-dependency", action="append", default=[])
    parser.add_argument("--package-alias", action="append", default=[])
    parser.add_argument("--check-pytorch", action="store_true")
    args = parser.parse_args()

    with args.pixi_file.open("rb") as file:
        pixi = tomllib.load(file)
    with args.recipe_file.open(encoding="utf-8") as file:
        recipe = yaml.safe_load(file)
    with args.project_file.open("rb") as file:
        project = tomllib.load(file)
    errors = validate_recipe(
        pixi,
        recipe,
        project,
        RecipeOptions(
            constraints_features=tuple(args.constraints_feature),
            security_floors=tuple(args.security_floor),
            allowed_direct_pixi=tuple(args.allow_direct_pixi),
            required_feature_dependencies=tuple(args.require_feature_dependency),
            package_aliases=tuple(args.package_alias),
            check_pytorch=args.check_pytorch,
        ),
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Recipe constraints match Pixi constraints and remain transitive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
