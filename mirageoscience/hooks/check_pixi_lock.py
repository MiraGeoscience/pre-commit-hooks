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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import tomlkit
import yaml
from packaging.utils import canonicalize_name


DEFAULT_GIT_URL_PREFIXES = ("git+https://github.com/MiraGeoscience/",)
PYPI_INDEX = "https://pypi.org/simple"


@dataclass(frozen=True)
class LockOptions:
    pypi_feature: str | tuple[str, ...]
    conda_feature: str | tuple[str, ...] | None = None
    strict_pypi: bool = False
    pypi_index_feature: str | None = None
    validate_pypi_sources: bool = False
    git_url_prefixes: tuple[str, ...] = DEFAULT_GIT_URL_PREFIXES
    artifact_source_roots: tuple[str, ...] = ()


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
    pixi: dict, feature_name: str, dependency_type: str, platform: str
) -> set[str]:
    """Resolve feature dependencies, including matching platform-target overrides."""
    try:
        feature = pixi["feature"][feature_name]
    except KeyError as error:
        raise ValueError(f"Pixi feature {feature_name!r} is not defined") from error
    targets = feature.get("target", {})
    if dependency_type not in feature and not any(
        dependency_type in target for target in targets.values()
    ):
        raise ValueError(
            f"Pixi feature {feature_name!r} has no {dependency_type!r} table"
        )
    dependencies = dict(feature.get(dependency_type, {}))
    subdir = platform
    for candidate in pixi.get("workspace", {}).get("platforms", []):
        if isinstance(candidate, dict) and candidate.get("name") == platform:
            subdir = candidate.get("platform", platform)
            break
    family = subdir.split("-", 1)[0]
    for selector, target in targets.items():
        pattern = re.escape(selector).replace(r"\*", ".*")
        if (
            re.fullmatch(pattern, platform)
            or selector == family
            or (selector == "unix" and family in {"linux", "osx"})
        ):
            dependencies.update(target.get(dependency_type, {}))
    return {canonicalize_name(name) for name in dependencies}


def _pypi_features(options: LockOptions) -> tuple[str, ...]:
    """Normalize configured PyPI features to a tuple."""
    if isinstance(options.pypi_feature, str):
        return (options.pypi_feature,)
    return options.pypi_feature


def _conda_features(options: LockOptions) -> tuple[str, ...]:
    """Normalize configured Conda features to a tuple."""
    if options.conda_feature is None:
        return ()
    if isinstance(options.conda_feature, str):
        return (options.conda_feature,)
    return options.conda_feature


def _environment_features(environment: object) -> set[str]:
    """Normalize a Pixi environment definition to its feature-name set."""
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
    """Extract canonical package names from PyPI or Conda lock entries."""
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


def _pypi_options(pixi: dict, feature_name: str | None) -> dict:
    """Merge PyPI options in top-level, workspace, then feature precedence."""
    options = dict(pixi.get("pypi-options", {}))
    options.update(pixi.get("workspace", {}).get("pypi-options", {}))
    if feature_name is not None:
        options.update(
            pixi.get("feature", {}).get(feature_name, {}).get("pypi-options", {})
        )
    return options


def _index_urls(pixi: dict, feature_name: str | None) -> set[str]:
    """Return configured PyPI index URLs without trailing slashes."""
    options = _pypi_options(pixi, feature_name)
    urls = set()
    if url := options.get("index-url"):
        urls.add(url.rstrip("/"))
    urls.update(url.rstrip("/") for url in options.get("extra-index-urls", []))
    return urls


def _expectations(
    pixi: dict, options: LockOptions, platform: str, features: set[str]
) -> LockExpectations:
    """Build platform-specific package and artifact-source expectations."""
    pypi_features = _pypi_features(options)
    pypi_packages = set()
    for feature_name in pypi_features:
        feature_packages = _feature_dependencies(
            pixi, feature_name, "pypi-dependencies", platform
        )
        if feature_name in features:
            pypi_packages.update(feature_packages)
    conda_packages = set()
    for feature_name in _conda_features(options):
        feature_packages = _feature_dependencies(
            pixi, feature_name, "dependencies", platform
        )
        if feature_name in features:
            conda_packages.update(feature_packages)
    index_features = (
        (
            (options.pypi_index_feature,)
            if options.pypi_index_feature in features
            else ()
        )
        if options.pypi_index_feature
        else tuple(
            feature_name for feature_name in pypi_features if feature_name in features
        )
    )
    index_urls = set()
    if options.validate_pypi_sources:
        if index_features:
            for feature_name in index_features:
                index_urls.update(_index_urls(pixi, feature_name))
        else:
            index_urls = _index_urls(pixi, None)
    source_indexes = set(index_urls)
    has_default_index = (
        not index_features and not _pypi_options(pixi, None).get("index-url")
    ) or any(
        not _pypi_options(pixi, feature_name).get("index-url")
        for feature_name in index_features
    )
    if options.validate_pypi_sources and has_default_index:
        source_indexes.add(PYPI_INDEX)
    source_roots = {
        f"{url.removesuffix('/simple').rstrip('/')}/" for url in source_indexes
    }
    if PYPI_INDEX in source_indexes:
        source_roots.add("https://files.pythonhosted.org/")
    source_roots.update(
        f"{root.rstrip('/')}/" for root in options.artifact_source_roots
    )
    return LockExpectations(pypi_packages, conda_packages, index_urls, source_roots)


def _allowed_git_source(url: str, prefixes: tuple[str, ...]) -> bool:
    """Check an allowed Git URL prefix and reject unsafe path segments."""
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        return False
    try:
        parsed = urlsplit(url)
        path = parsed.path
        while True:
            decoded = unquote(path)
            if decoded == path:
                break
            if decoded.count("/") != path.count("/"):
                return False
            path = decoded
        if (
            "\\" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or any(segment in {".", ".."} for segment in path.split("/"))
        ):
            return False
        return any(
            url.startswith(prefix)
            and parsed.scheme == urlsplit(prefix).scheme
            and parsed.netloc == urlsplit(prefix).netloc
            for prefix in prefixes
        )
    except ValueError:
        return False


def _source_errors(
    label: str,
    entries: list[dict],
    environment_lock: dict,
    pypi_feature_enabled: bool,
    context: LockContext,
) -> list[str]:
    """Report missing indexes and PyPI or Git sources outside allowed roots."""
    options = context.options
    expectations = context.expectations
    if not options.validate_pypi_sources or not pypi_feature_enabled:
        return []

    errors = []
    missing_indexes = expectations.index_urls - set(environment_lock.get("indexes", []))
    if missing_indexes:
        errors.append(
            f"{label}: missing configured PyPI indexes {sorted(missing_indexes)}"
        )
    for entry in entries:
        url = entry.get("pypi")
        if url is None:
            continue
        if url.startswith("git+"):
            if not _allowed_git_source(url, options.git_url_prefixes):
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
    """Check locked PyPI packages, using exact or minimum membership policy."""
    options = context.options
    expectations = context.expectations
    pypi_features = _pypi_features(options)
    pypi_feature_enabled = any(feature in features for feature in pypi_features)
    pypi_names = _locked_names(entries, context.packages_by_url, "pypi")
    expected_pypi = expectations.pypi_packages
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
        if not pypi_feature_enabled and pypi_names:
            feature_label = (
                f"the {pypi_features[0]!r} feature"
                if len(pypi_features) == 1
                else f"any of the {pypi_features!r} features"
            )
            errors.append(
                f"{label}: PyPI packages are locked without {feature_label}: "
                f"{sorted(pypi_names)}"
            )
    errors.extend(
        _source_errors(label, entries, environment_lock, pypi_feature_enabled, context)
    )
    return errors


def _conda_errors(
    label: str,
    pypi_names: set[str],
    conda_names: set[str],
    context: LockContext,
) -> list[str]:
    """Check expected packages are locked from their configured package source."""
    expected_conda = context.expectations.conda_packages
    expected_pypi = context.expectations.pypi_packages
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
    """Validate locked package names and sources for one platform."""
    pypi_names = _locked_names(entries, context.packages_by_url, "pypi")
    conda_names = _locked_names(entries, context.packages_by_url, "conda")
    return _pypi_errors(
        label, entries, environment_lock, features, context
    ) + _conda_errors(label, pypi_names, conda_names, context)


def _validate_environment(
    pixi: dict,
    environment_name: str,
    environment_lock: dict,
    options: LockOptions,
    packages_by_url: dict[str, str],
) -> list[str]:
    """Validate every locked platform for one Pixi environment."""
    environment_config = pixi.get("environments", {}).get(environment_name)
    if environment_config is None:
        if environment_name != "default":
            return [f"{environment_name}: missing Pixi environment definition"]
        environment_config = []
    features = _environment_features(environment_config)
    errors = []
    for platform, entries in environment_lock["packages"].items():
        label = f"{environment_name}/{platform}"
        platform_context = LockContext(
            options, _expectations(pixi, options, platform, features), packages_by_url
        )
        errors.extend(
            _validate_platform(
                label,
                entries,
                environment_lock,
                features,
                platform_context,
            )
        )
    return errors


def validate_lock(pixi: dict, lock: dict, options: LockOptions) -> list[str]:
    """Validate all lock environments against the Pixi feature configuration."""
    packages_by_url = {
        package["pypi"]: package["name"]
        for package in lock["packages"]
        if "pypi" in package
    }
    errors = []
    for environment_name, environment_lock in lock["environments"].items():
        errors.extend(
            _validate_environment(
                pixi,
                environment_name,
                environment_lock,
                options,
                packages_by_url,
            )
        )
    return errors


def main() -> int:
    """Load CLI inputs, validate the lock, and return the process status."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pixi-file", type=Path, default=Path("pixi.toml"))
    parser.add_argument("--lock-file", type=Path, default=Path("pixi.lock"))
    parser.add_argument("--pypi-feature", action="append")
    parser.add_argument("--conda-feature", action="append")
    parser.add_argument("--strict-pypi", action="store_true")
    parser.add_argument("--pypi-index-feature")
    parser.add_argument("--validate-pypi-sources", action="store_true")
    parser.add_argument("--git-url-prefix", action="append")
    parser.add_argument("--artifact-source-root", action="append", default=[])
    args = parser.parse_args()

    try:
        with args.pixi_file.open("rb") as file:
            pixi = tomlkit.load(file).unwrap()
        with args.lock_file.open(encoding="utf-8") as file:
            lock = yaml.safe_load(file)
        errors = validate_lock(
            pixi,
            lock,
            LockOptions(
                pypi_feature=tuple(args.pypi_feature or ["mira-pypi"]),
                conda_feature=tuple(args.conda_feature or []),
                strict_pypi=args.strict_pypi,
                pypi_index_feature=args.pypi_index_feature,
                validate_pypi_sources=args.validate_pypi_sources,
                artifact_source_roots=tuple(args.artifact_source_root),
                git_url_prefixes=(
                    tuple(args.git_url_prefix)
                    if args.git_url_prefix is not None
                    else DEFAULT_GIT_URL_PREFIXES
                ),
            ),
        )
    except (
        ValueError,
        KeyError,
        TypeError,
        tomlkit.exceptions.ParseError,
        yaml.YAMLError,
    ) as error:
        print(f"Invalid Pixi lock configuration: {error}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Pixi lock package sources match the configured features.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
