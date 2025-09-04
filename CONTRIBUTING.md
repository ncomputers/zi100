# Contributing

## Running checks locally

Install the project dependencies and tooling:

```bash
pip install -r requirements.txt
pip install pre-commit flake8 pytest uvicorn
pre-commit install
```

Then run all quality checks and tests:

```bash
pre-commit run --all-files
bash scripts/run_all_tests.sh
```

## Continuous Integration

The GitHub Actions workflow at `.github/workflows/ci.yaml` executes the same test script on every push and pull request.

## Issues and Pull Requests

Use the templates in `.github/ISSUE_TEMPLATE` when opening bug reports or feature requests. These templates request key details such as a summary, reproduction steps, and a checklist to ensure consistent submissions.

All pull requests should follow `.github/PULL_REQUEST_TEMPLATE.md` to provide a summary, testing notes, and a checklist before review.
