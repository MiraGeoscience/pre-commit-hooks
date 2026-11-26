# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
#  Copyright (c) 2024-2026 Mira Geoscience Ltd.                                      '
#                                                                                   '
#  This file is part of mirageoscience.pre-commit-hooks package.                    '
#                                                                                   '
#  mirageoscience.pre-commit-hooks is distributed under the terms and conditions    '
#  of the MIT License (see LICENSE file at the root of this source code package).   '
# '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

"""Validate conda recipe constraints against the Pixi workspace.

**Known limitation:** unconditional dependency traversal can reject valid recipes with
conditional runtime dependencies. The check aims at covering simple use cases for now.

Conditional ``run_constraints`` entries are not supported by the Conda recipe
comparison because they are flattened to a single effective constraint rather than
one unconditional value. Use unconditional constraints or pass
``--ignore-constraints`` to skip this specific comparison.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import tomlkit
import yaml
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version


@dataclass(frozen=True)
class RecipeOptions:
    package_aliases: tuple[str, ...] = ()
    check_pytorch: bool = False
    ignore_constraints: bool = False


def _parse_constraint(value: str) -> tuple[str, str]:
    """Split a Conda requirement into its canonical package name and specifier."""
    match = re.match(r"^\s*([^\s<>=!~]+)\s*(.*?)\s*$", value)
    if not match or not match.group(2):
        raise ValueError(f"Invalid recipe run constraint: {value!r}")
    name = match.group(1).rsplit("::", 1)[-1]
    return canonicalize_name(name), match.group(2)


def _as_specifier_set(value: str) -> SpecifierSet:
    """Convert Conda-style version syntax to a packaging specifier set."""
    if value in ("", "*"):
        return SpecifierSet()
    specifiers = []
    for specifier in value.split(","):
        specifier = specifier.strip()
        conda_equality = re.fullmatch(r"=(\d[0-9A-Za-z.!+_-]*)", specifier)
        if conda_equality:
            version = conda_equality.group(1)
            specifier = f"=={version if version.endswith('.*') else f'{version}.*'}"
        if not any(operator in specifier for operator in "<>=!~"):
            specifier = f"=={specifier}"
        specifiers.append(specifier)
    return SpecifierSet(",".join(specifiers))


def _requirement_strings(values: object):
    """Yield unconditional requirement strings; reject conditional entries."""
    if values is None:
        return
    if isinstance(values, str):
        yield values
        return
    if isinstance(values, list):
        for value in values:
            yield from _requirement_strings(value)
        return
    if isinstance(values, dict):
        if "if" in values or "then" in values or "else" in values:
            raise ValueError(
                "Conditional recipe requirements are not supported by "
                "check-conda-recipe; pass --ignore-constraints to skip this check "
                "for conditional constraints, or use unconditional constraints."
            )
        raise ValueError(f"Invalid recipe requirement entry: {values!r}")
    raise ValueError(f"Invalid recipe requirement entry: {values!r}")


def _flatten_requirement_strings(values: object):
    """Yield requirement strings, including both branches of conditional entries."""
    if values is None:
        return
    if isinstance(values, str):
        yield values
        return
    if isinstance(values, list):
        for value in values:
            yield from _flatten_requirement_strings(value)
        return
    if isinstance(values, dict):
        if any(key in values for key in ("if", "then", "else")):
            for branch in ("then", "else"):
                yield from _flatten_requirement_strings(values.get(branch))
            return
        raise ValueError(f"Invalid recipe requirement entry: {values!r}")
    raise ValueError(f"Invalid recipe requirement entry: {values!r}")


def _requirement_package(value: str) -> str:
    """Return a canonical package name, ignoring any Conda channel prefix."""
    match = re.match(r"^(?:[^\s:]+::)?([a-zA-Z0-9_.-]+)", value.strip())
    if not match:
        raise ValueError(f"Invalid recipe run requirement: {value!r}")
    return canonicalize_name(match.group(1))


def _package_aliases(values: tuple[str, ...]) -> dict[str, str]:
    """Parse package alias mappings and canonicalize both sides."""
    aliases = {}
    for value in values:
        alias, separator, package = value.partition("=")
        if not separator or not alias or not package:
            raise ValueError(f"Invalid package alias {value!r}; expected alias=package")
        aliases[canonicalize_name(alias)] = canonicalize_name(package)
    return aliases


def _pixi_constraint_sources(pixi: dict, constrained_packages: set[str]) -> dict:
    """Collect Pixi constraint and feature sources for recipe-constrained packages."""
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
                    normalized in constrained_packages
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
    """Extract the version from a Pixi inline dependency table or scalar."""
    if isinstance(specifier, dict):
        return str(specifier.get("version", ""))
    return str(specifier)


def _minimum_version(specifier: str) -> Version | None:
    """Return the strongest lower bound represented by a specifier."""
    versions = []
    for item in _as_specifier_set(specifier):
        if item.operator in (">=", ">", "~="):
            versions.append(Version(item.version))
        elif item.operator == "==":
            versions.append(Version(item.version.removesuffix(".*")))
    return max(versions, default=None)


def _constraint_matches(recipe_specifier: str, pixi_specifier: str) -> bool:
    """Match exact specifiers or lower bounds with the same effective floor."""
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
    """Report package-set differences and incompatible Pixi constraint sources."""
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


def _recipe_transitivity_errors(
    run_requirement_entries: object,
    constrained_packages: set[str],
    options: RecipeOptions,
) -> list[str]:
    """Report constrained packages declared directly in the recipe's run section."""
    aliases = _package_aliases(options.package_aliases)
    security_packages = {
        aliases.get(package, package) for package in constrained_packages
    }
    dependencies = {
        _requirement_package(value)
        for value in _requirement_strings(run_requirement_entries)
    }
    dependencies = {aliases.get(package, package) for package in dependencies}
    direct_dependencies = security_packages & dependencies
    if not direct_dependencies:
        return []
    return [
        "Security-floor packages must remain transitive in recipe requirements: "
        f"{sorted(direct_dependencies)}"
    ]


def _pytorch_errors(requirements: dict) -> list[str]:
    """Report explicit PyTorch backend selection in run or run_constraints entries."""
    backend_specs = []
    for section in ("run", "run_constraints"):
        for value in _flatten_requirement_strings(requirements.get(section, [])):
            match = re.match(r"^(?:[^\s:]+::)?([a-zA-Z0-9_.-]+)(.*)$", value.strip())
            if not match:
                continue
            package = canonicalize_name(match.group(1))
            specifier = match.group(2)
            if package in {"pytorch-cpu", "pytorch-gpu", "pytorch-cuda", "cpuonly"} or (
                package in {"pytorch", "pytorch-mutex"}
                and re.search(r"cpu|cuda|gpu", specifier, re.IGNORECASE)
            ):
                backend_specs.append(f"{section}: {value}")
    if not backend_specs:
        return []
    return [
        "recipe.yaml requirements must leave PyTorch backend selection "
        f"to the installer; found: {backend_specs}"
    ]


def validate_recipe(pixi: dict, recipe: dict, options: RecipeOptions) -> list[str]:
    """Validate recipe constraints, transitivity, and optional PyTorch policy."""
    errors = []
    requirements = recipe.get("requirements", {})
    run_requirement_entries = requirements.get("run", [])
    run_constraint_requirement_entries = requirements.get("run_constraints", [])
    has_conditional_constraints = any(
        isinstance(value, dict) and any(key in value for key in ("if", "then", "else"))
        for value in run_constraint_requirement_entries
    )
    if has_conditional_constraints and not options.ignore_constraints:
        errors.append(
            "Conditional run_constraints are not supported by check-conda-recipe; "
            "use unconditional constraints or exclude this validation. Pass "
            "--ignore-constraints to skip this check for conditional constraints."
        )

    constrained_packages = {
        _requirement_package(value)
        for value in _flatten_requirement_strings(run_constraint_requirement_entries)
    }
    if not has_conditional_constraints:
        recipe_constraints = dict(
            _parse_constraint(value)
            for value in _requirement_strings(run_constraint_requirement_entries)
        )
        pixi_sources = _pixi_constraint_sources(pixi, set(recipe_constraints))
        errors.extend(_constraint_errors(recipe_constraints, pixi_sources))
    errors.extend(
        _recipe_transitivity_errors(
            run_requirement_entries, constrained_packages, options
        )
    )
    if options.check_pytorch:
        errors.extend(_pytorch_errors(requirements))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixi-file", type=Path, default=Path("pixi.toml"))
    parser.add_argument("--recipe-file", type=Path, default=Path("recipe.yaml"))
    parser.add_argument("--package-alias", action="append", default=[])
    parser.add_argument("--check-pytorch", action="store_true")
    parser.add_argument("--ignore-constraints", action="store_true")
    args = parser.parse_args()

    with args.pixi_file.open("rb") as file:
        pixi = tomlkit.load(file).unwrap()
    with args.recipe_file.open(encoding="utf-8") as file:
        recipe = yaml.safe_load(file)
    errors = validate_recipe(
        pixi,
        recipe,
        RecipeOptions(
            package_aliases=tuple(args.package_alias),
            check_pytorch=args.check_pytorch,
            ignore_constraints=args.ignore_constraints,
        ),
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Recipe constraints match Pixi constraints and remain transitive.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
