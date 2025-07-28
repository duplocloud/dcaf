# Engineering Improvement Initiatives

A living document that records *initiatives*—significant engineering improvements we plan or introduce.  Each section explains **what** we’re adding, **why**, and the **scope of work** so contributors immediately understand the rationale and effort involved.

---

## 1. Adopt Ruff for Linting & Formatting

### What is Ruff?
[Ruff](https://docs.astral.sh/ruff/) is a super-fast linter and formatter for Python written in Rust. It implements the rule sets of Flake8, isort, pylint, pydocstyle and more, and ships an auto-formatter (`ruff format`).

### Why are we adding it?
1. **Code quality** – catches common bugs (unused vars, broad `except`, mutable defaults).
2. **Consistent style** – enforces import ordering, docstrings, whitespace, etc.
3. **Speed** – runs 10–100× faster than traditional Python linters, making it friction-free in pre-commit hooks and CI.
4. **All-in-one** – replaces separate tools (flake8 + isort) with a single dependency.

### Expected Benefits
* Cleaner, more maintainable codebase.
* Faster feedback during development and CI.
* Fewer style debates in code review—rules are clearly codified.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Add `ruff` to dev dependencies (`requirements-dev.txt` or `[project.optional-dependencies.dev]`). |  | ☐ |
| Create `[tool.ruff]` section in `pyproject.toml` (select rules E,F,I,D etc.; target Python 3.11). |  | ☐ |
| Run `ruff check --fix` and commit initial auto-fixes; open follow-up issues for remaining violations. |  | ☐ |
| Add `ruff check` and `ruff format --check` to CI pipeline before tests. |  | ☐ |
| Update developer docs / README with linting instructions (`pre-commit` optional). |  | ☐ |

---

## 2. Adopt `src/` Layout for First-Party Code

### What is the `src/` layout?
The `src/` layout moves all first-party Python packages under a dedicated top-level directory named `src` (e.g. `src/dab/`), keeping runtime code separate from project metadata files such as `pyproject.toml`, `Dockerfile`, and docs.

### Why are we adding it?
1. **Import safety** – prevents accidental imports from the working directory in tests and interactive sessions.
2. **Cleaner repo root** – reduces clutter by grouping source code in one place.
3. **Industry standard** – widely adopted in modern Python projects and natively supported by tools like `pytest`, `pip`, and `poetry`.
4. **Easier packaging** – simplifies configuration for wheels/sdist since packaging tools can point to `src/` without additional excludes.

### Expected Benefits
* Eliminates "works on my machine" issues caused by implicit `.` on `PYTHONPATH`.
* Makes repository structure clearer for new contributors.
* Simplifies Docker and CI contexts by excluding non-code files.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Move `dab/` to `src/` (`git mv dab src`). |  | ☐ |
| Update `PYTHONPATH` / Docker build arguments to include `src/`. |  | ☐ |
| Fix all import paths (run `ruff check --select I` or similar). |  | ☐ |
| Update tests and CI configurations to use new layout. |  | ☐ |
| Amend developer docs / README with new layout instructions. |  | ☐ |

*Add future initiatives below using the same structure.* 