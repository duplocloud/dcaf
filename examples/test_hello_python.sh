#!/usr/bin/env bash
# Test the hello-python zip skill.
# Requires: python examples/skills_example.py running in another terminal.

curl -s -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{
      "messages": [{
        "role": "user",
        "content": "Run the hello world Python script",
        "platform_context": {
          "skills": [{
            "name": "hello-python",
            "version": "1.0.2",
            "url": "http://localhost:8001/hello-python.zip"
          }]
        }
      }]
    }' | python -m json.tool
