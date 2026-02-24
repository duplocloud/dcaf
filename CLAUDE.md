# CLAUDE.md — DCAF Project Rules

## Overview

DCAF (DuploCloud Agent Framework) is a Python framework for building LLM-powered AI agents with tool calling, human-in-the-loop approval, and multi-provider support (Bedrock, Gemini, Anthropic, OpenAI, Ollama). Clean Architecture with domain-driven design in `dcaf/core/`.

## Architecture

```
dcaf/
├── core/           # NEW Clean Architecture API (recommended for all new work)
│   ├── agent.py         # Agent facade — main entry point
│   ├── server.py        # FastAPI server (serve())
│   ├── config.py        # Environment-driven configuration
│   ├── interceptors.py  # LLMRequest/LLMResponse pipeline
│   ├── tools.py         # @tool decorator and Tool class
│   ├── session.py       # Per-conversation state
│   ├── events.py        # Event subscription system
│   ├── models.py        # ChatMessage, PlatformContext DTOs
│   ├── primitives.py    # AgentResult, ToolResult, ToolApproval
│   ├── a2a/             # Agent-to-Agent protocol
│   ├── application/     # Business logic (services, DTOs, ports)
│   ├── domain/          # Entities, value objects, domain events
│   ├── adapters/        # Inbound (HTTP/WS) and outbound (LLM providers)
│   ├── infrastructure/  # Config and logging
│   ├── services/        # Skill manager, translator
│   └── testing/         # Builders, fakes, fixtures for tests
├── agents/         # LEGACY v1 agents (deprecated, do not extend)
├── llm/            # LEGACY v1 LLM wrappers (deprecated)
├── mcp/            # Model Context Protocol integration
├── schemas/        # V1 message schemas (dependency-free)
├── tools.py        # Shared @tool decorator (v1)
├── agent_server.py # FastAPI server (v1)
├── cli.py          # CLI entry point
└── channel_routing.py
```

## Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install everything (dev + docs + mcp)
pip install -e ".[all]"
```

## Running Tests

```bash
# Run all tests (verbose, short traceback — configured in pyproject.toml)
pytest

# Run specific test file
pytest tests/core/test_agent.py -v

# Run specific test class
pytest tests/core/test_agno_adapter.py::TestDefaultToolkit -v

# Run specific test method
pytest tests/core/test_agno_adapter.py::TestDefaultToolkit::test_build_default_toolkits_returns_five_toolkits -v

# Run tests matching a pattern
pytest -k "test_approval" -v

# Run with coverage
pytest --cov=dcaf tests/
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions are detected automatically.

**Known failures:** `tests/test_channel_routing.py` has 2 tests that require AWS credentials and will fail locally without them. These are pre-existing and unrelated to your changes.

## Code Quality Commands

```bash
# Lint
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format
ruff format .

# Format check (CI mode — fails if files need formatting)
ruff format --check .

# Type check
mypy dcaf/

# Architecture constraints
lint-imports

# Code health (radon)
python scripts/check_code_health.py
```

## Code Style

- **Formatter/Linter**: Ruff (line length 100, Python 3.11+, double quotes, 4-space indent)
- **Type checking**: MyPy — strict (`disallow_untyped_defs`) for `dcaf.core.*`, permissive for legacy
- **Pre-commit hooks** (via Prek): Ruff format → Ruff check --fix → MyPy
- **Imports**: isort via Ruff, `dcaf` is first-party

## Architectural Constraints (enforced by import-linter)

1. `dcaf.schemas` must not import from `dcaf.core`, `dcaf.agents`, or `dcaf.llm`
2. `dcaf.core` must not import from `dcaf.agents`
3. `dcaf.llm` must not import from `dcaf.core` or `dcaf.agents`

All new work should go in `dcaf/core/`. Do not add features to legacy modules.

## CI Quality Gates (all blocking except security)

| Check | Command | Blocking |
|-------|---------|----------|
| Lint & Format | `ruff check .` / `ruff format . --check` | Yes |
| Type Check | `mypy dcaf/` | Yes |
| Tests | `pytest` (Python 3.11/3.12/3.13) | Yes |
| Docs Build | `mkdocs build --strict` | Yes |
| Code Health | `python scripts/check_code_health.py` | Yes |
| Import Linter | `lint-imports` | Yes |
| Security | `pip-audit` / `vulture` | No |

## Code Health Thresholds (radon)

- Maintainability Index: minimum grade B
- Cyclomatic Complexity: grade C max per function
- SLOC per file: max 500 lines
- Aggregate complexity per file: max 160

## Safety Rails

- Never commit secrets, API keys, or credentials — use environment variables and `env.example`
- Tools with side effects must use `requires_approval=True`
- Do not modify generated files or legacy modules unless fixing bugs

## Commit Style

See `.claude/rules/git-commit.md` — Conventional Commits format with `Co-Authored-By` trailer. Run `pytest -v` before committing.

## Documentation

```bash
pip install -e ".[docs]"
mkdocs serve          # http://localhost:8000
mkdocs build --strict # Build and verify
```

Key docs: `docs/architecture.md`, `docs/engineering-handoff.md`, `docs/getting-started.md`
