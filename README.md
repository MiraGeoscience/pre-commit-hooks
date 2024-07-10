# Pre-Commit Hooks

This repository provides a collection of pre-commit hooks to automate essential checks and streamline your development workflow. By utilizing these hooks, you can maintain code quality and consistency across your projects, fostering a more efficient and collaborative development environment.

## Included Hooks
- `check-copyright`: Checks for valid copyright statements in files.
- `prepare-commit-msg`: Will add the JIRA ID found in the branch name in case it is missing from the commit message.
- `check-commit-message`: Check if the branch name or the commit message starts with a reference to JIRA, and if the message meets the minimum required length for the summary line.

## Usage
Example of `.pre-commit-config.yamnl`:
```yaml
- repo: http://github.com/MiraGeoscience/pre-commit-hooks
  rev: <release>
  hooks:
  - id: check-copyright
  - id: prepare-commit-msg
  - id: check-commit-msg
```