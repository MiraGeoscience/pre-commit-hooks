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
from urllib.parse import unquote, urlsplit

import yaml
from packaging.utils import canonicalize_name


@dataclass(frozen=True)
class LockOptions:
    pypi_feature: str
    conda_feature: str | None = None
    strict_pypi: bool = False
    pypi_index_feature: str | None = None
    validate_pypi_sources: bool = False
    git_url_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LockExpectations:
    pypi_packages: set[str]
    conda_packages: set[str]
    index_urls: set[str]
    source_roots: set[str]


@dataclass(frozen=True)
class LockContext:
    options: LockOptions
    expectations: LockExpectations
    packages_by_url: dict[str, str]


def _feature_dependencies(
    pixi: dict, feature_name: str, dependency_type: str
) -> set[str]:
    try:
        dependencies = pixi["feature"][feature_name][dependency_type]
    except KeyError as error:
        raise ValueError(
            f"Pixi feature {feature_name!r} has no {dependency_type!r} table"
        ) from error
    return {canonicalize_name(name) for name in dependencies}


def _environment_features(environment: object) -> set[str]:
    if isinstance(environment, dict):
        features = environment.get("features", [])
    else:
        features = environment
    if not isinstance(features, list):
        raise ValueError(f"Invalid Pixi environment feature list: {features!r}")
    return set(features)


def _locked_names(
    entries: list[dict], packages_by_url: dict[str, str], source: str
) -> set[str]:
    names = set()
    for entry in entries:
        url = entry.get(source)
        if url is None:
            continue
        if source == "pypi":
            name = packages_by_url.get(url)
            if name is None:
                raise ValueError(f"Pixi lock package URL is not defined: {url}")
        else:
            filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            for suffix in (".tar.bz2", ".conda"):
                if filename.endswith(suffix):
                    filename = filename[: -len(suffix)]
                    break
            package_parts = filename.rsplit("-", 2)
            if len(package_parts) != 3:
                raise ValueError(f"Cannot determine Conda package name from {url}")
            name = package_parts[0]
        names.add(canonicalize_name(name))
    return names


def _index_urls(pixi: dict, feature_name: str) -> set[str]:
    options = pixi["feature"][feature_name].get("pypi-options", {})
    urls = set()
    for key in ("index-url",):
        if url := options.get(key):
            urls.add(url.rstrip("/"))
    urls.update(url.rstrip("/") for url in options.get("extra-index-urls", []))
    return urls


def _expectations(pixi: dict, options: LockOptions) -> LockExpectations:
    pypi_packages = _feature_dependencies(
        pixi, options.pypi_feature, "pypi-dependencies"
    )
    conda_packages = (
        _feature_dependencies(pixi, options.conda_feature, "dependencies")
        if options.conda_feature
        else set()
    )
    index_feature = options.pypi_index_feature or options.pypi_feature
    index_urls = (
        _index_urls(pixi, index_feature) if options.validate_pypi_sources else set()
    )
    source_roots = {
        f"{url.removesuffix('/simple').rstrip('/')}/" for url in index_urls
    }
    return LockExpectations(pypi_packages, conda_packages, index_urls, source_roots)


def _source_errors(
    label: str,
    entries: list[dict],
    environment_lock: dict,
    expected_pypi: set[str],
    context: LockContext,
) -> list[str]:
    options = context.options
    expectations = context.expectations
    if not options.validate_pypi_sources or not expected_pypi:
        return []

    errors = []
    missing_indexes = expectations.index_urls - set(environment_lock.get("indexes", []))
    if missing_indexes:
        errors.append(f"{label}: missing configured PyPI indexes {sorted(missing_indexes)}")
    for entry in entries:
        url = entry.get("pypi")
        if url is None:
            continue
        if url.startswith("git+"):
            if not any(url.startswith(prefix) for prefix in options.git_url_prefixes):
                errors.append(f"{label}: unexpected Git source {url}")
        elif not any(url.startswith(root) for root in expectations.source_roots):
            errors.append(f"{label}: unexpected PyPI source {url}")
    return errors


def _pypi_errors(
    label: str,
    entries: list[dict],
    environment_lock: dict,
    features: set[str],
    context: LockContext,
) -> list[str]:
    options = context.options
    expectations = context.expectations
    pypi_names = _locked_names(entries, context.packages_by_url, "pypi")
    expected_pypi = (
        expectations.pypi_packages if options.pypi_feature in features else set()
    )
    errors = []
    if options.strict_pypi:
        if pypi_names != expected_pypi:
            errors.append(
                f"{label}: expected exactly PyPI packages {sorted(expected_pypi)}, "
                f"found {sorted(pypi_names)}"
            )
    else:
        missing_pypi = expected_pypi - pypi_names
        if missing_pypi:
            errors.append(f"{label}: missing PyPI packages {sorted(missing_pypi)}")
        if options.pypi_feature not in features and pypi_names:
            errors.append(
                f"{label}: PyPI packages are locked without the "
                f"{options.pypi_feature!r} feature: {sorted(pypi_names)}"
            )
    errors.extend(_source_errors(label, entries, environment_lock, expected_pypi, context))
    return errors


def _conda_errors(
    label: str,
    pypi_names: set[str],
    conda_names: set[str],
    features: set[str],
    context: LockContext,
) -> list[str]:
    options = context.options
    expected_conda = (
        context.expectations.conda_packages
        if options.conda_feature and options.conda_feature in features
        else set()
    )
    expected_pypi = (
        context.expectations.pypi_packages
        if options.pypi_feature in features
        else set()
    )
    errors = []
    missing_conda = expected_conda - conda_names
    if missing_conda:
        errors.append(f"{label}: missing Conda packages {sorted(missing_conda)}")
    wrong_pypi_source = expected_conda & pypi_names
    if wrong_pypi_source:
        errors.append(
            f"{label}: Conda feature packages locked from PyPI "
            f"{sorted(wrong_pypi_source)}"
        )
    wrong_conda_source = expected_pypi & conda_names
    if wrong_conda_source:
        errors.append(
            f"{label}: PyPI feature packages locked from Conda "
            f"{sorted(wrong_conda_source)}"
        )
    return errors


def _validate_platform(
    label: str,
    entries: list[dict],
    environment_lock: dict,
    features: set[str],
    context: LockContext,
) -> list[str]:
    pypi_names = _locked_names(entries, context.packages_by_url, "pypi")
    conda_names = _locked_names(entries, context.packages_by_url, "conda")
    return _pypi_errors(
        label, entries, environment_lock, features, context
    ) + _conda_errors(label, pypi_names, conda_names, features, context)


def _validate_environment(
    pixi: dict,
    environment_name: str,
    environment_lock: dict,
    context: LockContext,
) -> list[str]:
    environment_config = pixi["environments"].get(environment_name)
    if environment_config is None:
        return [f"{environment_name}: missing Pixi environment definition"]
    features = _environment_features(environment_config)
    errors = []
    for platform, entries in environment_lock["packages"].items():
        label = f"{environment_name}/{platform}"
        errors.extend(
            _validate_platform(
                label,
                entries,
                environment_lock,
                features,
                context,
            )
        )
    return errors


def validate_lock(pixi: dict, lock: dict, options: LockOptions) -> list[str]:
    packages_by_url = {
        package["pypi"]: package["name"]
        for package in lock["packages"]
        if "pypi" in package
    }
    context = LockContext(options, _expectations(pixi, options), packages_by_url)
    errors = []
    for environment_name, environment_lock in lock["environments"].items():
        errors.extend(
            _validate_environment(
                pixi,
                environment_name,
                environment_lock,
                context,
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixi-file", type=Path, default=Path("pixi.toml"))
    parser.add_argument("--lock-file", type=Path, default=Path("pixi.lock"))
    parser.add_argument("--pypi-feature", default="mira-pypi")
    parser.add_argument("--conda-feature")
    parser.add_argument("--strict-pypi", action="store_true")
    parser.add_argument("--pypi-index-feature")
    parser.add_argument("--validate-pypi-sources", action="store_true")
    parser.add_argument("--git-url-prefix", action="append", default=[])
    args = parser.parse_args()

    with args.pixi_file.open("rb") as file:
        pixi = tomllib.load(file)
    with args.lock_file.open(encoding="utf-8") as file:
        lock = yaml.safe_load(file)
    errors = validate_lock(
        pixi,
        lock,
        LockOptions(
            pypi_feature=args.pypi_feature,
            conda_feature=args.conda_feature,
            strict_pypi=args.strict_pypi,
            pypi_index_feature=args.pypi_index_feature,
            validate_pypi_sources=args.validate_pypi_sources,
            git_url_prefixes=tuple(args.git_url_prefix),
        ),
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Pixi lock package sources match the configured features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
