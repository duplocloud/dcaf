# Gap Analysis Checklist

---

## 1. Logging
- [x] Centralised logging bootstrap helper (e.g. `src/utils/logger.py`) imported by every entry-point.
- [x] Replace all `print()` calls (or proxy them) with module-level loggers (`logger = get_logger(__name__)`).
- [x] Support env-driven format switch: pretty console (dev) vs JSON/structured (prod/CI) via `LOG_FORMAT`.
- [x] Propagate request/user IDs via FastAPI middleware; attach same handler to third-party loggers.
- [x] Ensure graceful shutdown (`logging.shutdown()`) and provide helper to clear handlers in tests.

## 2. Testing & CI
- [ ] Create `tests/` directory with pytest; require ≥ 80 % coverage.
- [ ] Add layered fixture structure (`conftest.py` root + feature-level files).
- [ ] Differentiate unit vs integration tests; mock external services.
- [ ] Add CI pipeline steps: `ruff check → ruff format → pytest --cov → mypy`.
- [ ] Increase dependency injection (wrap subprocess/AWS calls) for easier mocking.
- [x] Configure Ruff in `pyproject.toml` (`[tool.ruff]`) — still need to fix existing lint offences.

## 3. Metrics & Observability
- [ ] Implement thin wrapper (`core/metrics.py`) around Prometheus/StatsD helpers (`increment`, `time`).
- [ ] Add FastAPI middleware to record latency/status and expose `/metrics` endpoint.
- [ ] Integrate distributed tracing (OpenTelemetry) for LLM calls & external interactions.

## 4. Container & Deployment
- [ ] Harden Dockerfile: multi-stage build, run as non-root user, pin `kubectl`/`helm` versions, clean apt cache.
- [ ] Add image vulnerability scanning and SCA in CI (e.g. Grype, Trivy).

## 5. Dependency & Type Management
- [ ] Consolidate dependency management: declare runtime + dev dependencies in `pyproject.toml` (PEP 621) and generate a lock file (`requirements.txt` or `poetry.lock`) automatically; avoid maintaining two divergent lists.
- [ ] Enable Dependabot / Renovate for automated updates.
- [ ] Add `mypy` configuration and fix current type issues.

## 6. Configuration & Secrets
- [x] Create Pydantic `Settings` class to centralise & validate env vars.
- [ ] Ensure secrets do not leak: keep `.env` in `.gitignore`, integrate AWS Secrets Manager or SOPS.

## 7. API Error Handling
- [ ] Implement structured Problem Details (RFC 7807) responses; avoid exposing raw tracebacks when `LOG_LEVEL` ≠ DEBUG.

## 8. CLI Improvements
- [ ] Replace `print()` statements in CLI with proper logging.
- [ ] Add retries/back-off logic and enriched error messages around subprocess calls.