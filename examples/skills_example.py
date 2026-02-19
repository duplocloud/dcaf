"""
Example: Skills pipeline POC.

Demonstrates the full skills pipeline:
1. A local FastAPI server hosts skill files (SKILL.md and .zip bundles)
2. A curl request includes skill definitions in platform_context
3. SkillManager fetches and caches the skill (with zip extraction for bundles)
4. The agent uses skill tools to read instructions and execute scripts

Run with:
    python examples/skills_example.py

Then test with:

    # Git skill (plain SKILL.md):
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

    # Python skill (zip bundle with script):
    curl -X POST http://localhost:8000/api/chat \
        -H "Content-Type: application/json" \
        -d '{
          "messages": [{
            "role": "user",
            "content": "Run the hello world Python script",
            "platform_context": {
              "skills": [{
                "name": "hello-python",
                "version": "1.0.0",
                "url": "http://localhost:8001/hello-python.zip"
              }]
            }
          }]
        }'
"""

import os
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.parse import urlparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dotenv

dotenv.load_dotenv(override=True)

os.environ.setdefault("AWS_PROFILE", "test10")
os.environ.setdefault(
    "PERSISTENT_VOLUME_STORAGE", os.path.join(tempfile.gettempdir(), "dcaf")
)

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse  # noqa: E402
from starlette.types import ASGIApp, Receive, Scope, Send  # noqa: E402

from dcaf.core import Agent, serve  # noqa: E402
from dcaf.core.tools import tool  # noqa: E402

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
SKILL_SERVER_PORT = 8001
AGENT_SERVER_PORT = 8000


@tool(requires_approval=False, description="Run a git command and return its output")
def run_command(command: str) -> str:
    """Execute a git command. Only git commands are allowed for safety."""
    # NOTE: POC only. The startswith check is a basic guard.
    # For production, allowlist specific git subcommands and avoid shell=True.
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


def _build_skill_zip(skill_dir: str, zip_path: str) -> None:
    """Build a zip file from a skill directory.

    The zip contains SKILL.md and scripts/ at the root level,
    matching the structure expected by the SkillManager.
    """
    skill_path = Path(skill_dir)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in skill_path.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(skill_path))


class _NormalizePathMiddleware:
    """Strip absolute URIs to relative paths.

    When an HTTP client uses a proxy, it sends the full URL in the request
    line (e.g. ``GET http://host/path``).  This middleware normalises the
    ASGI scope so downstream routes see only ``/path``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith(("http://", "https://")):
                scope["path"] = urlparse(path).path
        await self.app(scope, receive, send)


def start_skill_server(directory: str, port: int) -> None:
    """Start a background FastAPI server to serve skill files."""
    app = FastAPI()
    app.add_middleware(_NormalizePathMiddleware)
    base = Path(directory)

    @app.get("/{file_path:path}")
    async def serve_skill(file_path: str) -> FileResponse:
        target = base / file_path
        if target.is_file():
            media_type = "application/zip" if target.suffix == ".zip" else "text/markdown"
            return FileResponse(target, media_type=media_type)
        return PlainTextResponse("Not found", status_code=404)

    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": "127.0.0.1", "port": port, "log_level": "warning"},
        daemon=True,
    )
    thread.start()


# Create the agent
agent = Agent(
    tools=[run_command],
    system_prompt=(
        "You are a helpful assistant that can run git commands and execute skill scripts. "
        "Use the run_command tool to execute git commands when asked "
        "about repository state, history, or changes. "
        "When skills are available, use the skill tools (get_skill_instructions, "
        "get_skill_script) to access and execute skill scripts."
    ),
)


if __name__ == "__main__":
    # Build the hello-python skill zip from its directory
    hello_skill_dir = os.path.join(SKILLS_DIR, "hello-python")
    hello_zip_path = os.path.join(SKILLS_DIR, "hello-python.zip")
    _build_skill_zip(hello_skill_dir, hello_zip_path)
    print(f"Built skill zip: {hello_zip_path}")

    # Start the skill file server
    start_skill_server(SKILLS_DIR, SKILL_SERVER_PORT)

    print("=" * 60)
    print("DCAF Skills Example")
    print("=" * 60)
    print(f"\nSkill server running at http://127.0.0.1:{SKILL_SERVER_PORT}")
    print(f"  Serving: {SKILLS_DIR}")
    print(f"\nAgent server starting at http://127.0.0.1:{AGENT_SERVER_PORT}")
    print("\nTest with:")
    print(f"""
    # Test 1: Git operations (plain SKILL.md)
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

    # Test 2: Python script execution (zip bundle)
    curl -X POST http://localhost:{AGENT_SERVER_PORT}/api/chat \\
        -H "Content-Type: application/json" \\
        -d '{{
          "messages": [{{
            "role": "user",
            "content": "Run the hello world Python script",
            "platform_context": {{
              "skills": [{{
                "name": "hello-python",
                "version": "1.0.0",
                "url": "http://localhost:{SKILL_SERVER_PORT}/hello-python.zip"
              }}]
            }}
          }}]
        }}'
    """)
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Start the DCAF agent server (blocking)
    serve(agent, port=AGENT_SERVER_PORT)
