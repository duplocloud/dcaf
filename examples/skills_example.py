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
