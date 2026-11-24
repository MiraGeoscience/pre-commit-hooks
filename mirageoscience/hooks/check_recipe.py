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
    package_aliases: tuple[str, ...] = ()
    check_pytorch: bool = False


def _parse_constraint(value: str) -> tuple[str, str]:
    name, separator, specifier = value.strip().partition(" ")
    if not separator or not specifier.strip():
        raise ValueError(f"Invalid recipe run constraint: {value!r}")
    return canonicalize_name(name), specifier.strip()


def _as_specifier_set(value: str) -> SpecifierSet:
    if value in ("", "*"):
        return SpecifierSet()
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


def _package_aliases(values: tuple[str, ...]) -> dict[str, str]:
    aliases = {}
    for value in values:
        alias, separator, package = value.partition("=")
        if not separator or not alias or not package:
            raise ValueError(f"Invalid package alias {value!r}; expected alias=package")
        aliases[canonicalize_name(alias)] = canonicalize_name(package)
    return aliases


def _pixi_constraint_sources(pixi: dict, recipe_packages: set[str]) -> dict:
    sources: dict[str, list[tuple[str, str]]] = {}
    for package, specifier in pixi.get("constraints", {}).items():
        sources.setdefault(canonicalize_name(package), []).append(
            (_pixi_version(specifier), "workspace constraint")
        )

    top_level_packages = set(sources)
    for feature_name, feature in pixi.get("feature", {}).items():
        for section in ("dependencies", "pypi-dependencies", "constraints"):
            for package, specifier in feature.get(section, {}).items():
                normalized = canonicalize_name(package)
                if (
                    normalized in recipe_packages
                    and normalized not in top_level_packages
                ):
                    sources.setdefault(normalized, []).append(
                        (
                            _pixi_version(specifier),
                            f"feature {feature_name!r} {section}",
                        )
                    )
    return sources


def _pixi_version(specifier: object) -> str:
    if isinstance(specifier, dict):
        return str(specifier.get("version", ""))
    return str(specifier)


def _minimum_version(specifier: str) -> Version | None:
    versions = []
    for item in _as_specifier_set(specifier):
        if item.operator in (">=", ">", "~="):
            versions.append(Version(item.version))
        elif item.operator == "==":
            versions.append(Version(item.version.removesuffix(".*")))
    return max(versions, default=None)


def _constraint_matches(recipe_specifier: str, pixi_specifier: str) -> bool:
    recipe_set = _as_specifier_set(recipe_specifier)
    pixi_set = _as_specifier_set(pixi_specifier)
    if recipe_set == pixi_set:
        return True
    if any(item.operator not in (">=", ">") for item in recipe_set):
        return False
    recipe_floor = _minimum_version(recipe_specifier)
    pixi_floor = _minimum_version(pixi_specifier)
    return (
        recipe_floor is not None
        and recipe_floor == pixi_floor
        and recipe_floor in pixi_set
    )


def _constraint_errors(
    recipe_constraints: dict[str, str], pixi_sources: dict[str, list[tuple[str, str]]]
) -> list[str]:
    errors = []
    if recipe_constraints.keys() != pixi_sources.keys():
        errors.append(
            "recipe.yaml run_constraints must match Pixi constraints; "
            f"recipe={sorted(recipe_constraints)}, Pixi={sorted(pixi_sources)}"
        )
    for package, recipe_specifier in recipe_constraints.items():
        sources = pixi_sources.get(package)
        if not sources:
            continue
        for pixi_specifier, source in sources:
            if _constraint_matches(recipe_specifier, pixi_specifier):
                continue
            errors.append(
                f"{package}: recipe constraint {recipe_specifier!r} is not "
                f"consistent with {source} {pixi_specifier!r}"
            )
    return errors


def _pixi_direct_dependencies(pixi: dict) -> tuple[set[str], dict[str, set[str]]]:
    root: set[str] = set()
    features: dict[str, set[str]] = {}

    def dependencies(section: dict) -> set[str]:
        tables = [section, *section.get("target", {}).values()]
        return {
            canonicalize_name(name)
            for table in tables
            for dependency_type in ("dependencies", "pypi-dependencies")
            for name in table.get(dependency_type, {})
        }

    root.update(dependencies(pixi))
    for feature_name, feature in pixi.get("feature", {}).items():
        features[feature_name] = dependencies(feature)
    return root, features


def _published_transitivity_errors(
    recipe: dict,
    project: dict,
    security_packages: set[str],
    aliases: dict[str, str],
) -> list[str]:
    dependencies = _project_dependency_names(project)
    dependencies.update(
        canonicalize_name(value.split(maxsplit=1)[0].rsplit("::", 1)[-1])
        for value in recipe["requirements"].get("run", [])
    )
    dependencies = {aliases.get(package, package) for package in dependencies}
    direct_dependencies = security_packages & dependencies
    if not direct_dependencies:
        return []
    return [
        "Security-floor packages must remain transitive in the published recipe "
        f"and project dependencies: {sorted(direct_dependencies)}"
    ]


def _pixi_transitivity_errors(
    pixi: dict, security_packages: set[str], aliases: dict[str, str]
) -> list[str]:
    root_dependencies, feature_dependencies = _pixi_direct_dependencies(pixi)
    root_dependencies = {aliases.get(package, package) for package in root_dependencies}
    top_level_constraints = {
        aliases.get(canonicalize_name(package), canonicalize_name(package))
        for package in pixi.get("constraints", {})
    }
    direct_root_security = security_packages & root_dependencies
    direct_feature_dependencies = {
        aliases.get(package, package)
        for packages in feature_dependencies.values()
        for package in packages
    }
    direct_feature_security = security_packages & direct_feature_dependencies
    invalid_feature_security = direct_feature_security & top_level_constraints
    invalid_pixi_security = direct_root_security | invalid_feature_security
    if not invalid_pixi_security:
        return []
    return [
        "Security-floor packages must remain Pixi constraints, not direct "
        f"dependencies: {sorted(invalid_pixi_security)}"
    ]


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
    return _published_transitivity_errors(
        recipe, project, security_packages, aliases
    ) + _pixi_transitivity_errors(pixi, security_packages, aliases)


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
    pixi_sources = _pixi_constraint_sources(pixi, set(recipe_constraints))
    errors = _constraint_errors(recipe_constraints, pixi_sources)
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
