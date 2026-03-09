# CLI/GUI Contract Fixtures

This directory contains authoritative JSON fixtures that define the contract between the Python CLI and Swift GUI.

## Purpose

1. **Single source of truth**: These fixtures represent the exact JSON format the CLI emits.
2. **Shared test data**: Both Python and Swift tests decode these fixtures to ensure compatibility.
3. **Change detection**: If the CLI output format changes, tests will fail and force a review.

## Files

| File | Description |
|------|-------------|
| `config.show.v1.json` | Output of `fix-my-claw config show --json` |
| `status.v1.json` | Output of `fix-my-claw status --json` |
| `check.v1.json` | Output of `fix-my-claw check --json` |
| `repair.v1.json` | Output of `fix-my-claw repair --json` |
| `service.status.v1.json` | Output of `fix-my-claw service status --json` |

## Versioning

- All fixtures include `api_version` at the top level.
- Version format: `"major.minor"` (e.g., `"1.0"`)
- **Major version bump**: Breaking changes (field removal, type changes)
- **Minor version bump**: Additive changes (new optional fields)

## Update Rules

When modifying fixtures:

1. **Run Python tests** to regenerate: `pytest tests/test_contracts.py --update-fixtures`
2. **Update Swift tests** to match new fixture content
3. **Bump version** if structure changes
4. **Document changes** in commit message

## Do NOT

- Do not edit fixtures manually for cosmetic changes
- Do not remove fields without a major version bump
- Do not add fixture-specific test data (use test code for edge cases)
