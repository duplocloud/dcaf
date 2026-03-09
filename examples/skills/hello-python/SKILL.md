---
name: hello-python
description: A simple Python hello world skill demonstrating script execution
---

# Hello Python Skill

This skill demonstrates executing a Python script through the skills pipeline.

When the user asks you to run the hello world script or greet them:

1. Use `get_skill_script("hello-python", "hello.py", execute=True)` to execute the Python script
2. Report the output to the user

## Available Scripts

- `scripts/hello.py` - A simple Hello World script that prints a greeting
