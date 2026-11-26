# MiraGeoscience.Pre-Commit Hooks

This repository provides a collection of pre-commit hooks to automate essential
checks and streamline your development workflow. By utilizing these hooks, you
can maintain code quality and consistency across your projects, fostering a more
efficient and collaborative development environment.

## Included Hooks

### `check-copyright`
Checks for valid copyright statements in files.

### `check-pixi-lock`
Checks locked Conda and PyPI sources against Pixi workspace features.
`--strict-pypi` requires the lock to contain exactly the packages declared by
the selected PyPI features; otherwise transitive PyPI dependencies are allowed
while the feature packages are still checked.

By default, this hook reads `pixi.toml` and `pixi.lock` from the repository root.
Use `--pypi-feature` for each feature that declares packages under
`[feature.<name>.pypi-dependencies]`; the default is `mira-pypi`. Repeat the
option when PyPI dependencies are split across features, for example
`--pypi-feature=mira-pypi --pypi-feature=vendor-pypi`.

Repeat the optional `--conda-feature` for each feature whose packages under
`[feature.<name>.dependencies]` must stay Conda-sourced, for example
`--conda-feature=conda-base --conda-feature=conda-runtime`. This enables a
source-separation check: in environments where the selected features are
enabled, those packages must be present in the Conda lock and not the PyPI
lock, while packages from the selected PyPI features must be present in the
PyPI lock and not the Conda lock. Do not select the same package in both
categories; this check rejects that overlap, even though Pixi itself resolves
such a conflict in favour of Conda. If omitted, the hook does not check the
source of feature-declared Conda dependencies.

By default, the hook checks expected package membership and Conda-versus-PyPI
lock placement, but does not validate PyPI index URLs or package download
origins. Enable `--validate-pypi-sources` for those checks. The repeatable
`--artifact-source-root` option is only used with this flag to permit download
locations outside an index's URL. For example, if a locked wheel is downloaded from
`https://artifacts.example.com/python-wheels/package-1.0.whl`, allow that artifact
location with:

```yaml
args:
  - --validate-pypi-sources
  - --artifact-source-root=https://artifacts.example.com/python-wheels
```

The root is the allowed artifact URL prefix, not the PyPI index URL; repeat the option
for additional artifact locations.

PyPI's standard artifact host is allowed automatically.
If index configuration lives in a separate feature, `--pypi-index-feature` selects that
feature's `pypi-options`; the feature must be enabled in the environment to apply its
indexes. Otherwise, workspace-level options or the default PyPI index are used. Git
sources from `git+https://github.com/MiraGeoscience/` are allowed by default; repeat
`--git-url-prefix` to configure allowed Git URL prefixes.

### `check-recipe`
Checks recipe `run_constraints` against Pixi constraints, discovers matching
feature constraints from `pixi.toml`, verifies constrained packages are not
also direct dependencies in recipe `run`, and optionally checks that the recipe
leaves PyTorch backend selection to the installer.

By default, this hook reads `recipe.yaml` and `pixi.toml` from the repository root.

Dependency consistency is checked by `pip check` during recipe builds; this hook
focuses on ensuring recipe and Pixi constraints agree.

Conditional `run_constraints` are not supported by the recipe validation; use
unconditional constraints or pass `--ignore-constraints` to skip this specific
constraint comparison.

Recipe security floors and their Pixi source are inferred from `recipe.yaml` and
`pixi.toml`.

Only enable the optional PyTorch check with `--check-pytorch` when required.

**Known limitation:** unconditional dependency traversal can reject valid recipes with
conditional runtime dependencies. The check aims at covering simple use-cases for now.

### `prepare-commit-msg`
Adds the JIRA ID found in the branch name in case it is missing from the commit message.

### `check-commit-message`
Checks that the branch name or the commit message starts with a reference to JIRA,
and if the message meets the minimum required length for the summary line. Also checks
that the JIRA ID in the commit message is consistent with the one extracted from the
branch name (if any).

## Usage

Example of `.pre-commit-config.yamnl`:

```yaml
repos:
-  repo: http://github.com/MiraGeoscience/pre-commit-hooks
   rev: <release>
   hooks:
   -  id: check-copyright
      types: [text]
      files: (^LICENSE|^README(|-dev).rst|\.py|\.pyi)$
      exclude: (^\.|^docs/)
   -  id: check-pixi-lock
      args: [--pypi-feature=mira-pypi, --strict-pypi]
   -  id: check-recipe
      args: [--check-pytorch]
   -  id: prepare-commit-msg
   -  id: check-commit-msg
```

## License

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
