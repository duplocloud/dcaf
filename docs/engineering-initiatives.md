# Engineering Improvement Initiatives

A living document that records *initiatives*—significant engineering improvements we plan or introduce. Each section explains **what** we’re adding, **why**, and the **scope of work** so contributors immediately understand the rationale and effort involved.

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

---

## 3. Centralised Logging Framework

### What is Centralised Logging?
A unified logging setup that funnels **all** application logs through the standard `logging` library, with a single bootstrap module (`src/utils/logger.py`). The helper supports human-friendly console output for development and structured JSON for production and CI, switchable via the `LOG_FORMAT` env var.

### Why are we adding it?
1. **Observability** – consistent, parseable logs accelerate debugging and monitoring.
2. **Best practices** – promotes idiomatic logging and removes ad-hoc `print()` calls.
3. **Flexibility** – format and verbosity can be tuned without code changes.
4. **Foundation for tracing** – central hook point for future correlation IDs and trace context.

### Expected Benefits
* Cleaner source code with idiomatic `logger.info(...)` etc.
* Ability to ingest logs into ELK/CloudWatch with minimal processing.
* Easy toggling between pretty console logs and machine-readable JSON.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Create `src/utils/logger.py` and configure root logger (console vs JSON). |  | ✅ |
| Import the helper in every entry-point (`main.py`, `src/cli.py`, agent scripts). |  | ✅ |
| Replace all `print()` calls with logger calls or redirect them to the logger. |  | ☐ |
| Expose `LOG_LEVEL` and `LOG_FORMAT` env vars; document defaults in README. |  | ☐ |
| Add guidance in docs on how to view JSON logs locally (`jq`, etc.). |  | ☐ |

---

## 4. Integrate MyPy for Static Type Checking

### What is MyPy?
[MyPy](https://mypy-lang.org/) is a static type checker for Python that analyses source code annotated with [PEP 484](https://peps.python.org/pep-0484/) type hints and reports type violations **without running the program**.

### Why are we adding it?
1. **Catch bugs earlier** – spot incompatible types, missing attributes, etc., during development and CI.
2. **Self-documenting code** – type annotations make APIs clearer for humans and IDEs.
3. **Refactor with confidence** – static analysis highlights code paths impacted by changes.
4. **Better tooling** – enables richer autocomplete and linting in editors.

### Expected Benefits
* Fewer runtime `TypeError`/`AttributeError` issues reaching production.
* Faster onboarding for new contributors thanks to explicit contracts.
* Increased overall code quality and consistency.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Add `mypy` to dev dependencies (`[project.optional-dependencies.dev]`). |  | ✅ |
| Create `mypy.ini` or `[tool.mypy]` section in `pyproject.toml` (strict-ish baseline). |  | ✅ |
| Run `mypy --install-types --non-interactive` and commit initial stub packages. |  | ☐ |
| Fix high-priority type errors; open follow-up issues for long-tail fixes. |  | ☐ |
| Add `mypy --strict` to CI pipeline after Ruff checks and before tests. |  | ☐ |
| Update developer docs with typing guidelines and ignore-pattern conventions. |  | ☐ |

---

## 5. Establish Automated Testing

### What is Automated Testing?
Automated testing uses frameworks like `pytest` to execute repeatable test suites and ensure the application behaves as expected.

### Why are we adding it?
1. **Bug prevention** – catch regressions before they reach production.
2. **Developer confidence** – enables safe refactoring with immediate feedback.
3. **Quality gate** – coverage thresholds enforce minimum test coverage.
4. **Executable documentation** – tests demonstrate intended behaviour for future contributors.

### Expected Benefits
* Higher code quality and fewer production incidents.
* Faster code-review cycles thanks to trustworthy automated checks.
* Shared understanding of application behaviour through readable tests.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Create `tests/` directory and initialise `pytest` with a root `conftest.py`. |  | ☐ |
| Require ≥ 80 % statement coverage (`pytest --cov --cov-fail-under=80`). |  | ☐ |
| Add layered fixture structure (root + feature-level `conftest.py`). |  | ☐ |
| Differentiate **unit** vs **integration** tests; mock external services (AWS, subprocess). |  | ☐ |
| Provide guidance in docs on writing and running tests locally. |  | ☐ |
| Incrementally increase coverage target (raise threshold as coverage improves). |  | ☐ |

## 6. Centralised Configuration & Secrets Management

### What is Centralised Configuration & Secrets Management?
A single `pydantic.BaseSettings` subclass (e.g. `src/config.py`) that holds **all** runtime configuration―regular env vars *and* sensitive secrets―with validation and typed access across the code-base.

### Why are we adding it?
1. **Single source of truth** – stop scattering `os.getenv()` calls; everything lives in one class.
2. **Early failure** – invalid/missing settings raise at startup, not in production.
3. **Security** – secrets can be hydrated from AWS Secrets Manager, SOPS or Vault without code changes.
4. **Developer ergonomics** – type-checked, auto-completed `settings.X` access everywhere.
5. **Documentation** – the settings schema becomes living docs for required environment variables.

### Expected Benefits
* Fewer runtime crashes due to missing env vars.
* Clear audit trail of which secrets are used where.
* Easier onboarding: `env.example` shows everything you need.
* Decouples secret storage mechanism from application code.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Add `pydantic` to runtime dependencies (`[project.dependencies]`). |  | ☐ |
| Create `src/config.py` with `Settings` class + `get_settings()` cache. |  | ☐ |
| Load `.env` in dev; ship `env.example`; keep `.env` in `.gitignore`. |  | ☐ |
| Replace scattered `os.getenv` calls with `settings.<var>` usages. |  | ☐ |
| Implement secret fetch hook (AWS Secrets Manager) inside `Settings`. |  | ☐ |
| Add CI step: `python -c 'from config import Settings; Settings()'` to validate config. |  | ☐ |
| Update README/docs with configuration & secret guidelines. |  | ☐ |

## 7. Metrics & Observability

### What is Metrics & Observability?
**Metrics** provide quantitative data (counters, gauges, histograms) about application behaviour, while **observability** layers this with structured logs and distributed traces to explain *why* events occur. Together they enable proactive monitoring, alerting, and debugging.

### Why are we adding it?
1. **Operational insight** – track latency, error rates, throughput, and resource utilisation.
2. **Faster incident response** – surface anomalies before they impact users.
3. **Data-driven decisions** – inform capacity planning and performance tuning.
4. **Foundation for SLOs** – enable reliability engineering practices.

### Expected Benefits
* Real-time dashboards for request rate, latency, and error ratios.
* Alerting on SLA/SLO breaches.
* Ability to trace slow or failing LLM/tool calls across services end-to-end.

### Scope of Work (MVP)
| Task | Owner | Status |
|------|-------|--------|
| Create `core/metrics.py` helper exposing `increment`, `gauge`, `histogram`, and `time` utilities (backed by Prometheus/StatsD). |  | ☐ |
| Add FastAPI middleware to record request latency, status code, and path labels. |  | ☐ |
| Expose `/metrics` endpoint for Prometheus scraping. |  | ☐ |
| Instrument LLM and external service integrations with metrics and OpenTelemetry spans. |  | ☐ |
| Add OpenTelemetry SDK with auto-instrumentation for HTTP/AWS calls. |  | ☐ |
| Provide Docker/Kubernetes examples (ServiceMonitor/PodMonitor) for scraping and tracing exporters. |  | ☐ |
| Document metrics & tracing setup in README and developer docs. |  | ☐ |
| Add CI smoke test ensuring `/metrics` returns 200 and valid format. |  | ☐ |

*Add future initiatives below using the same structure.* 