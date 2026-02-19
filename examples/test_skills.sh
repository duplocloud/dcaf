#!/bin/bash
# Test the skills example pipeline.
# Start the server first: python examples/skills_example.py

AGENT_PORT=8000
SKILL_PORT=8001

echo "=== Test 1: Git operations (plain SKILL.md) ==="
curl -s -X POST "http://localhost:${AGENT_PORT}/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"messages\": [{
        \"role\": \"user\",
        \"content\": \"Show me the recent git history\",
        \"platform_context\": {
          \"skills\": [{
            \"name\": \"git-operations\",
            \"version\": \"1.0.0\",
            \"url\": \"http://localhost:${SKILL_PORT}/git-operations/SKILL.md\"
          }]
        }
      }]
    }" | python -m json.tool 2>/dev/null || echo "(raw output above)"

echo ""
echo "=== Test 2: Python script (zip bundle) ==="
curl -s -X POST "http://localhost:${AGENT_PORT}/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"messages\": [{
        \"role\": \"user\",
        \"content\": \"Run the hello world Python script\",
        \"platform_context\": {
          \"skills\": [{
            \"name\": \"hello-python\",
            \"version\": \"1.0.0\",
            \"url\": \"http://localhost:${SKILL_PORT}/hello-python.zip\"
          }]
        }
      }]
    }" | python -m json.tool 2>/dev/null || echo "(raw output above)"
