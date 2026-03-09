# Code Health Metrics & Python Linting Report

A detailed reference of the tooling, rule sets, and thresholds used in this project for code quality enforcement. Intended for adoption by other projects.

## 1. Ruff — Linter & Formatter

**Version:** `>=0.15.0` (CI pins `0.15.0`)
**Target Python:** `3.14`
**Line length:** `88`

### Enabled Rule Sets

| Code | Rule Set | Purpose |
|------|----------|---------|
| `E` | pycodestyle errors | PEP 8 style errors |
| `W` | pycodestyle warnings | PEP 8 style warnings |
| `F` | pyflakes | Unused imports, undefined names, etc. |
| `I` | isort | Import sorting/ordering |
| `B` | flake8-bugbear | Common Python pitfalls and design issues |
| `C4` | flake8-comprehensions | Unnecessary list/dict/set comprehensions |
| `C901` | McCabe complexity | Cyclomatic complexity per function |
| `UP` | pyupgrade | Modernize syntax to target Python version |
| `S` | flake8-bandit | Security checks (hardcoded passwords, unsafe calls, etc.) |
| `PLR0911` | Pylint | Too many return statements |
| `PLR0912` | Pylint | Too many branches |
| `PLR0913` | Pylint | Too many arguments |
| `PLR0915` | Pylint | Too many statements |

### Ignored Rules (Global)

| Code | Reason |
|------|--------|
| `E501` | Line length handled by the formatter, not the linter |
| `B008` | Allows function calls in argument defaults (FastAPI `Depends()` pattern) |
| `B904` | `raise` without `from` inside `except` — often intentional |
| `B905` | `zip()` without `strict=` parameter |
| `S101` | Allows `assert` usage (used idiomatically for type narrowing) |

### Pylint Thresholds

| Setting | Value |
|---------|-------|
| `max-args` | **8** |
| `max-statements` | **50** |
| `max-branches` | **12** |
| `max-returns` | **6** |

### McCabe Complexity

| Setting | Value |
|---------|-------|
| `max-complexity` | **10** |

### Per-File Ignores

- **`tests/*`** — `B018`, `B017`, `PLR0913`, `S101`, `S105`, `S106` (allows asserts, "useless" expressions, many-arg fixtures, test credentials)
- **`migrations/*`** — `C901` (migrations are inherently complex)
- **`scripts/*`** — `C901` (utility scripts)
- ~30 specific source files have `PLR0913` or `PLR0911` suppressions (tracked as TODOs for refactoring)

### Formatter

Ruff is also the formatter (replaces Black). Settings:

- **Line length:** 88
- **Excluded:** `src/pa/_version.py` (auto-generated)

### How It Runs

- **Pre-commit:** `ruff format` (priority 10), then `ruff check --fix` (priority 20)
- **CI:** `ruff check src/ tests/` + `ruff format --check src/ tests/` (no auto-fix in CI — must be clean)

---

## 2. mypy — Static Type Checking

**Version:** `>=1.14.0`
**Target Python:** `3.14`

| Setting | Value | Notes |
|---------|-------|-------|
| `warn_return_any` | `true` | Warns when a function returns `Any` |
| `warn_unused_ignores` | `true` | Flags unnecessary `# type: ignore` comments |
| `disallow_untyped_defs` | `false` | Gradual typing — untyped function defs are allowed |
| `check_untyped_defs` | `true` | Still checks bodies of untyped functions |
| `ignore_missing_imports` | `false` | Globally strict; overridden per-module for third-party libs |
| `strict_optional` | `true` | `None` must be explicitly handled in Optional types |

**Excluded directories:** `vendor/`, `scripts/`, `migrations/`

**Per-module overrides:**

- ~30 third-party modules have `ignore_missing_imports = true` (no type stubs available)
- A handful of legacy test modules have `ignore_errors = true` (tracked for rewrite)

**How it runs:**

- **Pre-commit:** `mypy` on staged `.py` files (excluding vendor/scripts/migrations)
- **CI:** `uv run mypy --config-file pyproject.toml src/`

---

## 3. Radon — Code Health Metrics (via CI Script)

Powered by `scripts/check_code_health.py` and the `radon` library (`>=6.0.0`).

Runs as a **blocking CI gate** on every push to `dev`.

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| **Maintainability Index (MI)** | Minimum grade **B** | Fails if any file scores grade C or worse. Radon MI grades: A (20–100), B (10–19), C (0–9). |
| **Cyclomatic Complexity (CC)** | Max grade **C** | Fails on any individual function/method graded D or worse (complexity > 20). |
| **File SLOC** | Max **500** lines | Fails if any source file exceeds 500 source lines of code. |
| **Aggregate File CC** | Max **160** | Fails if the sum of all function complexities in a single file exceeds 160. |
| **Code Duplication** | Max **2.75%** | Per-area duplication threshold (uses `jscpd`). Each layer scanned independently. |

**Scan path:** `src/pa/`
**Excluded:** `vendor/`, `migrations/`, `scripts/`, `tests/`, `__pycache__/`

The script supports CLI overrides:

```bash
python scripts/check_code_health.py                       # all checks
python scripts/check_code_health.py --check mi cc sloc    # specific checks only
python scripts/check_code_health.py --sloc-max 400        # override SLOC threshold
python scripts/check_code_health.py --agg-cc-max 120      # override aggregate CC
python scripts/check_code_health.py --dup-max 2.0         # override duplication %
```

---

## 4. import-linter — Architectural Dependency Enforcement

**Version:** `>=2.0`

Enforces a layered architecture through import contracts:

| Contract | Type | Rule |
|----------|------|------|
| Core cannot import Butler API | `forbidden` | `pa.core` cannot import from `pa.butler_api` |
| Core cannot import SAQ | `forbidden` | `pa.core` cannot import from `pa.saq` |
| Layered architecture | `layers` | `pa.butler_api` → `pa.saq` → `pa.core` (higher can import lower, not vice versa) |

---

## 5. Additional Security & Quality Tools (CI)

| Tool | Purpose | Status |
|------|---------|--------|
| **pip-audit** | Dependency vulnerability scanning | `continue-on-error: true` (non-blocking, triaging findings) |
| **vulture** (`--min-confidence 80`) | Dead code detection | `continue-on-error: true` (non-blocking, whitelist pending) |

---

## 6. Test Coverage

**Tool:** `pytest-cov` / `coverage`

| Setting | Value |
|---------|-------|
| **Source paths** | `pa/saq`, `pa/core`, `pa/butler_api` |
| **Omitted** | `tests/*`, `migrations/*`, `scripts/*` |
| **CI test command** | `pytest tests/ -v --tb=short -x -m "not integration"` |

**Excluded from coverage reporting:**

- `pragma: no cover`
- `__repr__` methods
- Debug/settings guard blocks
- `Protocol` classes
- `@abstractmethod` methods

---

## 7. Pre-commit Hook Execution Order

Managed by **prek** (installed via `uv tool install prek`). Hooks run on every commit in priority order:

| Priority | Hook | Command | Files |
|----------|------|---------|-------|
| 10 | Ruff Format | `uv run ruff format` | `*.py` (excl. vendor, migrations) |
| 20 | Ruff Check | `uv run ruff check --fix` | `*.py` (excl. vendor, migrations) |
| 30 | MyPy | `uv run mypy` | `*.py` (excl. vendor, scripts, migrations) |
| 40 | ESLint | `npm run lint:fix` | UI `*.{js,jsx,ts,tsx}` |
| 40 | Prettier | `npx prettier --write` | UI `*.{js,jsx,ts,tsx,css}` |

---

## 8. CI Pipeline Integration

All checks run as separate jobs in the GitHub Actions CI pipeline (`.github/workflows/ci.yml`):

```
migration-check → lint → type-check → code-health → security → test → build-and-push
```

- **Lint, type-check, code-health, security, and test** run on `dev` pushes only
- **Main branch** skips validation (already passed on `dev`) and promotes the tested image directly

---

## Summary for Adoption

To replicate this setup in another project, you need:

1. **`ruff`** — single tool for both formatting and linting, configured in `pyproject.toml` under `[tool.ruff]`
2. **`mypy`** — type checking with gradual adoption (`disallow_untyped_defs = false`, `check_untyped_defs = true`)
3. **`radon`** — maintainability index, cyclomatic complexity, SLOC metrics via a CI health script
4. **`jscpd`** (Node.js) — copy-paste / code duplication detection
5. **`import-linter`** — architectural layer enforcement
6. **`prek`** — pre-commit hook runner (`uv tool install prek`)
7. **(Optional)** `pip-audit` + `vulture` — dependency vulnerability scanning and dead code detection

### Minimal `pyproject.toml` Snippet

```toml
[tool.ruff]
target-version = "py314"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "C901", "UP", "S", "PLR0911", "PLR0912", "PLR0913", "PLR0915"]
ignore = ["E501", "B008", "B904", "B905", "S101"]

[tool.ruff.lint.pylint]
max-args = 8
max-statements = 50
max-branches = 12
max-returns = 6

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.mypy]
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = false
check_untyped_defs = true
ignore_missing_imports = false
strict_optional = true
```
