# Skills Example Application Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a minimal POC that demonstrates the full skills pipeline end-to-end: skill hosted via HTTP, fetched/cached by SkillManager, loaded into the agent, and a tool that executes shell commands from the skill's instructions.

**Architecture:** A local HTTP server hosts a git-operations SKILL.md file. The DCAF agent server receives curl requests with `platform_context.skills` pointing at the local server. The AgnoAdapter's existing `_resolve_skills()` flow fetches, caches, and loads the skill. A `run_command` tool lets the agent execute git commands described in the skill.

**Tech Stack:** Python 3.11+, DCAF core (Agent, serve, @tool), Python's http.server for skill hosting

---

## Task 1: Create the git-operations SKILL.md

**Files:**
- Create: `examples/skills/git-operations/SKILL.md`

**Step 1: Create the skill file**

Create `examples/skills/git-operations/SKILL.md` with this content:

```markdown
---
name: git-operations
description: Run git commands to inspect repository state
---

# Git Operations Skill

You have access to the `run_command` tool which can execute git commands.

When the user asks about git repository state, use `run_command` with the appropriate git command.

## Available Commands

- `git status` - Show working tree status (modified files, staged changes)
- `git log --oneline -10` - Show the 10 most recent commits
- `git diff --stat` - Show a summary of uncommitted changes
- `git branch -a` - List all branches (local and remote)
- `git remote -v` - Show configured remotes

## Guidelines

- Always use `run_command` to execute commands - never fabricate output
- If a command fails, report the error to the user
- Keep responses concise and focused on the command output
```

**Step 2: Verify file exists**

Run: `cat examples/skills/git-operations/SKILL.md`
Expected: The skill markdown content above

**Step 3: Commit**

```bash
git add examples/skills/git-operations/SKILL.md
git commit -m "feat: add git-operations skill file for skills example"
```

---

## Task 2: Create the skills example server

**Files:**
- Create: `examples/skills_example.py`

**Step 1: Create the example server**

Create `examples/skills_example.py`:

```python
"""
Example: Skills pipeline POC.

Demonstrates the full skills pipeline:
1. A local HTTP server hosts a SKILL.md file
2. A curl request includes skill definitions in platform_context
3. SkillManager fetches and caches the skill
4. The agent uses a run_command tool to execute skill instructions

Run with:
    python examples/skills_example.py

Then test with:
    curl -X POST http://localhost:8000/api/chat \
        -H "Content-Type: application/json" \
        -d '{
          "messages": [{
            "role": "user",
            "content": "Show me the recent git history",
            "platform_context": {
              "skills": [{
                "name": "git-operations",
                "version": "1.0.0",
                "url": "http://localhost:8001/git-operations/SKILL.md"
              }]
            }
          }]
        }'
"""

import os
import subprocess
import sys
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dotenv

dotenv.load_dotenv(override=True)

from dcaf.core import Agent, serve  # noqa: E402
from dcaf.tools import tool  # noqa: E402

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
SKILL_SERVER_PORT = 8001
AGENT_SERVER_PORT = 8000


@tool(requires_approval=False, description="Run a git command and return its output")
def run_command(command: str) -> str:
    """Execute a git command. Only git commands are allowed for safety."""
    if not command.strip().startswith("git"):
        return "Error: Only git commands are allowed"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += result.stderr
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"


def start_skill_server(directory: str, port: int) -> HTTPServer:
    """Start a background HTTP server to serve skill files."""
    handler = partial(SimpleHTTPRequestHandler, directory=directory)
    server = HTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# Create the agent
agent = Agent(
    tools=[run_command],
    system_prompt=(
        "You are a helpful assistant that can run git commands. "
        "Use the run_command tool to execute git commands when asked "
        "about repository state, history, or changes."
    ),
)


if __name__ == "__main__":
    # Start the skill file server
    skill_server = start_skill_server(SKILLS_DIR, SKILL_SERVER_PORT)

    print("=" * 60)
    print("DCAF Skills Example")
    print("=" * 60)
    print(f"\nSkill server running at http://0.0.0.0:{SKILL_SERVER_PORT}")
    print(f"  Serving: {SKILLS_DIR}")
    print(f"\nAgent server starting at http://0.0.0.0:{AGENT_SERVER_PORT}")
    print("\nTest with:")
    print(f"""
    curl -X POST http://localhost:{AGENT_SERVER_PORT}/api/chat \\
        -H "Content-Type: application/json" \\
        -d '{{
          "messages": [{{
            "role": "user",
            "content": "Show me the recent git history",
            "platform_context": {{
              "skills": [{{
                "name": "git-operations",
                "version": "1.0.0",
                "url": "http://localhost:{SKILL_SERVER_PORT}/git-operations/SKILL.md"
              }}]
            }}
          }}]
        }}'
    """)
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Start the DCAF agent server (blocking)
    serve(agent, port=AGENT_SERVER_PORT)
```

**Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('examples/skills_example.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add examples/skills_example.py
git commit -m "feat: add skills pipeline example server"
```

---

## Task 3: Smoke test the full pipeline

**Step 1: Start the example server**

Run: `cd /Users/chuckconway/Projects/dcaf && python examples/skills_example.py &`
Expected: Server starts, prints the banner with skill server on 8001 and agent on 8000

**Step 2: Verify skill file is served**

Run: `curl -s http://localhost:8001/git-operations/SKILL.md | head -5`
Expected: The first 5 lines of the SKILL.md file (the frontmatter)

**Step 3: Send a chat request with skills in platform_context**

Run:
```bash
curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{
      "messages": [{
        "role": "user",
        "content": "What is the git status of this repo?",
        "platform_context": {
          "skills": [{
            "name": "git-operations",
            "version": "1.0.0",
            "url": "http://localhost:8001/git-operations/SKILL.md"
          }]
        }
      }]
    }'
```
Expected: JSON response with the agent's answer containing git status output

**Step 4: Verify skill was cached**

Run: `ls -la /data/skills/git-operations/1.0.0/SKILL.md 2>/dev/null || ls -la $PERSISTENT_VOLUME_STORAGE/skills/git-operations/1.0.0/SKILL.md 2>/dev/null || echo "Check storage path"`
Expected: The cached SKILL.md file exists

**Step 5: Stop the server**

Run: `kill %1` (or Ctrl+C if in foreground)

**Step 6: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: adjust skills example after smoke test"
```
