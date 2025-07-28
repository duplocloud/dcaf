# Best Practices Cheat-Sheet

> This document summarizes the key engineering conventions we follow so they can be reused across services.

---

## 1  Logging

### 1.1  Single bootstrap
Ensure a single helper (e.g. `core/utils/logger.py`) sets handlers, format, and level. All entry-points simply call `configure_logging()`.

### 1.2  Module-level loggers
Use
```python
import logging
logger = logging.getLogger(__name__)
```
so records carry the import path.

### 1.3  Structured + human formats
* **Local/dev** – colourised console output.
* **Prod/CI** – JSON / key-value for machine parsing.
* Select via an env var, e.g. `LOG_FORMAT=pretty | json`.

### 1.4  Context propagation
Inject request-ID, user-ID, etc. in a FastAPI middleware and add them to the `extra` dict of every log record. Attach the same handler to third-party loggers (`uvicorn`, `sqlalchemy`).

### 1.5  Granular levels & no `print()`
* DEBUG – developer data
* INFO  – state changes
* WARNING – recoverable issues
* ERROR – failures
* CRITICAL – shutdown

`print()` is disallowed by lint rules.

### 1.6  Shutdown & handler hygiene
Call `logging.shutdown()` on exit; tests clear handlers to avoid duplicate output when pytest reloads modules.

---

## 2  Python Testing

### 2.1  Pytest everywhere
* Coverage gate ≥ 80 percent (`pytest --cov`).
* Async code marked with `pytest.mark.asyncio`.

### 2.2  Directory layout
```
project/
└── tests/
    ├── conftest.py      # shared fixtures
    ├── helpers/ fakes/  # test doubles
    └── <feature>/tests/ # mirrors src layout
```

### 2.3  Layered fixtures
* Session-scoped expensive fixtures in root `conftest.py`.
* Feature-specific `conftest.py` files can extend/override.
* Use `autouse=True` for ubiquitous patches (env vars, logging).

### 2.4  Unit vs integration
* **Unit** – patch external boundaries (`pytest-mock`).
* **Integration** – FastAPI test client, in-memory DB/fakes, **never** connect to real external services.

### 2.5  Dependency injection
Services accept collaborators (interfaces) via the constructor so tests can supply mocks/fakes.

### 2.6  Naming & docs
`test_<function>_<scenario>()`; non-trivial tests start with a docstring explaining *given/when/then*.

### 2.7  Parameterisation & edge cases
Use `@pytest.mark.parametrize` for success + error paths. Store edge-case fixtures (empty list, large payload) in helper modules.

### 2.8  CI sequence
`ruff check → ruff format → pytest --cov → mypy (optional)`; pipeline fails on any error.

### 2.9  Ruff configuration
Configure Ruff via `[tool.ruff]` in `pyproject.toml` (or `ruff.toml`).
Enable the rule sets you care about (E, F, I, D, etc.) and run
`ruff check` in CI. Use `ruff format` locally/in CI to automatically
apply stylistic fixes.

### 2.10  Source code layout – the “src” pattern
Using a top-level `src/` directory for your importable package is the recommended default because it:
* Forces you to install the package (`pip install -e .`) before it can be imported, preventing the *“works only from repo root”* trap.
* Makes the boundary between **production code** and everything else (tests, build scripts, docs) obvious; many tools (pytest, ruff, coverage) now recognise and respect this pattern out-of-the-box.

Alternative names are acceptable – e.g. a library whose import name and folder are the same (`myproject/myproject/…`) or descriptive service folders in a monorepo – **if** you update `pyproject.toml`/setuptools `packages.find` and your tooling configuration accordingly.

Rule of thumb: when in doubt, pick the `src/` layout to minimise configuration and maximise familiarity for new contributors.

---

## 3  Frontend Testing (React)

1. **Jest + React Testing Library** – each component has a sibling `__tests__` folder. Render via `render(<Component />)` and assert on text/ARIA roles.
2. **MSW** mocks HTTP in unit tests. No real network traffic.
3. **Playwright** E2E specs live in `e2e/`; they run after unit tests.

---

## 4  Metrics & Observability

* A thin wrapper (`core/metrics.py`) around Prometheus/StatsD: `increment()` and `time()` helpers keep business code vendor-neutral.
* FastAPI middleware captures latency & status; expose at `/metrics`.

---

## 5  How to Apply in a New Project

1. Copy `configure_logging()` & env‐based format switch.
2. Enforce `logging.getLogger(__name__)` pattern.
3. Mirror the `tests/` tree and add a root `conftest.py`.
4. Add CI steps: lint → format → tests + coverage.
5. Introduce DI so services are swappable.
6. Add the metrics wrapper and FastAPI middleware early.

---

*Last updated: <!-- YYYY-MM-DD -->*
