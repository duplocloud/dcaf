# Agno Toolkits Guide

This guide covers how to use native Agno toolkits with DCAF agents, giving your agents instant access to 100+ pre-built integrations — databases, APIs, search engines, and more.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Popular Toolkits](#popular-toolkits)
4. [Combining with DCAF Tools](#combining-with-dcaf-tools)
5. [Combining with MCP Tools](#combining-with-mcp-tools)
6. [Configuration](#configuration)
7. [Best Practices](#best-practices)

---

## Introduction

[Agno](https://docs.agno.com/) is the underlying LLM framework that DCAF uses. Agno ships with a large library of **Toolkits** — pre-built integrations for databases, APIs, search engines, file systems, and more.

DCAF lets you pass any native Agno toolkit directly to `Agent(tools=[...])`. They work alongside DCAF tools and MCP tools with no conversion or wrapping needed.

### When to Use Agno Toolkits

| Scenario | Recommended Approach |
|----------|---------------------|
| Pre-built integration exists (database, API, search) | Agno toolkit |
| Custom business logic with approval workflows | [DCAF tool](./building-tools.md) |
| External MCP server | [MCP tool](./mcp-tools.md) |
| Mix of all three | Combine them in one agent |

---

## Quick Start

### Installation

Agno toolkits are included with DCAF. Some toolkits require additional packages for their specific integration — install them as needed:

```bash
# Example: DuckDB toolkit
pip install duckdb

# Example: Wikipedia toolkit
pip install wikipedia
```

### Basic Usage

```python
from agno.tools.duckdb import DuckDbTools
from dcaf.core import Agent, serve

agent = Agent(
    tools=[DuckDbTools()],
    system_prompt="You are a data analyst. Use DuckDB to answer questions.",
)

serve(agent, port=8000)
```

That's it. The toolkit is passed directly to the underlying Agno agent — no conversion or configuration needed.

### Async Usage

```python
from agno.tools.wikipedia import WikipediaTools
from dcaf.core import Agent

agent = Agent(
    tools=[WikipediaTools()],
    system_prompt="You are a research assistant.",
)

async def main():
    result = await agent.arun("Tell me about the history of Python programming")
    print(result.text)
```

---

## Popular Toolkits

Here are some commonly used Agno toolkits. For the full list, see the [Agno documentation](https://docs.agno.com/).

### Databases

```python
from agno.tools.duckdb import DuckDbTools
from agno.tools.postgres import PostgresTools
from agno.tools.sql import SqlTools
from agno.tools.neo4j import Neo4jTools

# DuckDB — in-process analytical database
agent = Agent(tools=[DuckDbTools()])

# PostgreSQL — connect to an existing database
agent = Agent(tools=[PostgresTools(
    db_url="postgresql://user:pass@localhost:5432/mydb"
)])

# Neo4j — graph database
agent = Agent(tools=[Neo4jTools(
    url="bolt://localhost:7687",
    user="neo4j",
    password="password",
)])
```

### Search & Research

```python
from agno.tools.arxiv import ArxivTools
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.wikipedia import WikipediaTools
from agno.tools.hackernews import HackerNewsTools

agent = Agent(tools=[
    DuckDuckGoTools(),
    WikipediaTools(),
])
```

### File & Code

```python
from agno.tools.file import FileTools
from agno.tools.python import PythonTools
from agno.tools.shell import ShellTools
from agno.tools.csv_toolkit import CsvTools

agent = Agent(tools=[
    FileTools(),
    PythonTools(),
])
```

### External Services

```python
from agno.tools.github import GithubTools
from agno.tools.slack import SlackTools
from agno.tools.jira import JiraTools
from agno.tools.gmail import GmailTools

agent = Agent(tools=[
    GithubTools(),
    SlackTools(),
])
```

---

## Combining with DCAF Tools

Agno toolkits work alongside native DCAF tools in the same agent. Use DCAF tools when you need features like approval workflows or platform context injection.

```python
from agno.tools.duckdb import DuckDbTools
from dcaf.core import Agent, serve
from dcaf.tools import tool

# Native DCAF tool with approval required
@tool(requires_approval=True, description="Drop a database table")
def drop_table(table_name: str) -> str:
    return f"Dropped table: {table_name}"

# DCAF tool with platform context
@tool(description="Get current tenant info")
def get_tenant(platform_context: dict) -> str:
    tenant = platform_context.get("tenant_name", "unknown")
    return f"Current tenant: {tenant}"

# Combine Agno toolkit + DCAF tools
agent = Agent(
    tools=[
        DuckDbTools(),   # Agno toolkit — passed through directly
        drop_table,      # DCAF tool — converted with approval support
        get_tenant,      # DCAF tool — converted with context injection
    ],
    system_prompt="You are a data analyst with tenant-aware access.",
)

serve(agent, port=8000)
```

### How It Works

When you pass tools to `Agent(tools=[...])`, DCAF automatically detects the type of each tool:

| Tool Type | Detection | Handling |
|-----------|-----------|----------|
| DCAF `Tool` | Created with `@tool()` decorator | Converted to Agno format with approval/context support |
| Agno `Toolkit` | Instance of `agno.tools.toolkit.Toolkit` | Passed through directly to Agno agent |
| DCAF `MCPTool` | Instance of `dcaf.mcp.MCPTool` | Underlying Agno toolkit extracted and passed through |

---

## Combining with MCP Tools

You can mix all three tool types — Agno toolkits, DCAF tools, and MCP tools — in a single agent:

```python
from agno.tools.duckdb import DuckDbTools
from dcaf.core import Agent, serve
from dcaf.mcp import MCPTool
from dcaf.tools import tool

# Agno toolkit
duckdb = DuckDbTools()

# DCAF tool
@tool(requires_approval=True, description="Execute a dangerous query")
def dangerous_query(sql: str) -> str:
    return f"Executed: {sql}"

# MCP tool
mcp_search = MCPTool(
    url="http://localhost:9000/mcp",
    transport="streamable-http",
)

agent = Agent(
    tools=[duckdb, dangerous_query, mcp_search],
    system_prompt="You are a data analyst with search capabilities.",
)

serve(agent, port=8000)
```

---

## Configuration

### Toolkit-Specific Options

Each Agno toolkit accepts its own configuration. Refer to the toolkit's constructor for available options:

```python
from agno.tools.duckdb import DuckDbTools

# DuckDB with specific settings
duckdb = DuckDbTools(
    db_path="/tmp/analytics.db",  # Persistent database file
    run_queries=True,             # Allow query execution
    inspect_queries=True,         # Show query plans
)
```

```python
from agno.tools.python import PythonTools

# Python with sandboxed execution
python = PythonTools(
    run_code=True,
    pip_install=False,  # Disable pip installs
)
```

### Environment Variables

Many toolkits read credentials from environment variables:

```bash
# GitHub
export GITHUB_TOKEN=ghp_...

# Slack
export SLACK_TOKEN=xoxb-...

# Neo4j
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
```

---

## Best Practices

### 1. Install Required Dependencies

Each toolkit may require additional packages. If you get an `ImportError`, install the missing package:

```bash
# Check the toolkit's documentation or error message
pip install duckdb    # for DuckDbTools
pip install neo4j     # for Neo4jTools
pip install wikipedia # for WikipediaTools
```

### 2. Use DCAF Tools for Approval Workflows

Agno toolkits don't support DCAF's approval system. If a tool performs destructive operations, wrap it as a DCAF tool instead:

```python
# Agno toolkit — no approval support
agent = Agent(tools=[DuckDbTools()])  # All queries execute immediately

# DCAF tool — with approval
@tool(requires_approval=True, description="Execute SQL query")
def execute_sql(query: str) -> str:
    # Only runs after user approves
    ...
```

### 3. Use DCAF Tools for Platform Context

Agno toolkits don't receive DCAF platform context. If you need tenant-aware behavior, use a DCAF tool:

```python
@tool(description="Query tenant database")
def query_tenant_db(query: str, platform_context: dict) -> str:
    tenant = platform_context.get("tenant_name")
    db_url = get_db_url_for_tenant(tenant)
    ...
```

### 4. Scope Toolkit Capabilities

Some toolkits are powerful. Limit their capabilities when possible:

```python
# Limit what PythonTools can do
python = PythonTools(
    run_code=True,
    pip_install=False,   # Don't allow package installation
)

# Limit shell access
shell = ShellTools()  # Consider if you really need this
```

---

## See Also

- [Building Tools Guide](./building-tools.md) — Creating native DCAF tools with approval and context
- [MCP Tools Guide](./mcp-tools.md) — Connecting to external MCP servers
- [Custom Agents Guide](./custom-agents.md) — Building complex agent workflows
- [Agno Documentation](https://docs.agno.com/) — Full Agno toolkit reference
