# Releasing

Checklist for the maintainer. Nothing in this repo publishes automatically.

1. Bump `__version__` in `mentat_wiki/__init__.py` if needed, and replace `Unreleased` in the
   CHANGELOG heading with the release date.
2. Regenerate the demo vault if the schema changed: `python scripts/make_demo_vault.py`.
3. Push `main` and confirm the CI workflow is green on ubuntu, windows and macos (Python 3.10 and
   3.13), including the `package` job (`scripts/check_dist.py` and `scripts/smoke.py`).
4. Build: `python -m build` (or `uv build`), then `python scripts/check_dist.py dist` and
   `python scripts/smoke.py dist` locally.
5. Upload to TestPyPI first, install from it in a clean venv, run `mentat-wiki --version` and
   `mentat-wiki init <dir>`.
6. Upload to PyPI, tag `vX.Y.Z`, create the GitHub release with the CHANGELOG section.

README links are absolute GitHub URLs so they also work on the PyPI project page.
