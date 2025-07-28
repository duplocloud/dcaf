# Service-Desk Agents – Logging Guide

This guide explains **how to work with the centralised logging framework** that was introduced in Initiative #3. It covers:

1. Enabling the logger in your code
2. Switching between *pretty* console logs and *structured* JSON logs
3. Controlling verbosity
4. Viewing & filtering logs locally
5. Special considerations for entry-points (`uvicorn`, CLI scripts, etc.)

---

## 1  Quick Start

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Hello from the logging guide!")
```

Running the above will emit something like:

```
2025-07-28 12:34:56 | INFO | my_module | Hello from the logging guide!
```

## 2  Configuration via Environment Variables

| Variable        | Default  | Accepted Values                 | Description |
|-----------------|----------|---------------------------------|-------------|
| `LOG_FORMAT`    | console  | `console`, `json`               | Output style. Use `json` for machine-readable logs. |
| `LOG_LEVEL`     | INFO     | `DEBUG`, `INFO`, `WARNING`, …   | Minimum severity that will be emitted. |
| `UVICORN_LOG_LEVEL` | WARNING | Any standard log level        | Overrides noisy `uvicorn.access` logs. |

### 2.1  Example – JSON Logs

```bash
# Emit JSON logs at DEBUG verbosity
LOG_FORMAT=json LOG_LEVEL=DEBUG python main.py | jq .
```

Sample structured log entry:

```json
{
  "timestamp": "2025-07-28T12:35:01.123Z",
  "level": "INFO",
  "name": "my_module",
  "message": "Hello from the logging guide!"
}
```

## 3  Entry-Points & Bootstrapping

The helper is imported **once** at the top of every entry-point so that *all* subsequent modules inherit the same configuration:

* `main.py` – initialises logger before starting `uvicorn`.
* `src/cli.py` – overrides built-in `print()` to route through the logger.
* Agents running as scripts (e.g. `tool_calling_agent_boilerplate.py`) – same pattern.

> ⚠️  If you create a new entry-point, import `get_logger()` as early as possible **before** other modules that might log.

## 4  Replacing `print()`

`print()` is discouraged. Use the appropriate severity instead:

* `logger.debug()` – noisy internal details
* `logger.info()`  – normal operational messages
* `logger.warning()` – unexpected but recoverable events
* `logger.error()` – errors that may require attention

The existing CLI still contains a `print` proxy that forwards to `logger.info()` so older code paths continue to work.

## 5  Local Filtering & Troubleshooting

*Pretty console* output can be grepped normally:

```bash
grep "| ERROR |" app.log
```

For *JSON* logs, leverage `jq`:

```bash
jq -c 'select(.level == "ERROR")' app.log
```

## 6  Extending the Logger (Future Roadmap)

The helper is designed to be extended for:

* Request/trace correlation IDs via log-context
* Distributed tracing exporters (OpenTelemetry)
* Metrics side-effects (e.g., increment error counters)

Contributions welcome – see `docs/engineering-initiatives.md`.

## 7  Code Style & Linting (Ruff)

Ruff provides linting, import ordering, and formatting in a **single fast tool**.

### 7.1  Installation (dev-only extras)

```bash
pip install -e '.[dev]'
```

This installs Ruff and any other developer-only helpers defined in the `dev` extras group of `pyproject.toml`.

### 7.2  Checking the codebase

```bash
ruff check .
```

Runs all enabled rule sets (E, F, I, B) and exits with a non-zero status if violations are found.

### 7.3  Auto-formatting

```bash
ruff format .
```

Rewrites files in-place, unifying what Black and isort used to handle.

### 7.4  Configuration snippets

Ruff is configured in `pyproject.toml`.

```toml
[tool.ruff]
line-length = 120
preview = true

[tool.ruff.lint]
select = ["E", "F", "I", "B"]
```

Adjust these if the team agrees on different conventions.

### 7.5  CI pipeline hook

Add the following to your CI steps _before_ running tests:

```bash
ruff check .            # fail fast on lint
ruff format --check .   # ensure files are already formatted
```

This keeps `main` free of style regressions.

---

Made with ☕ by the Service-Desk Agents team. 