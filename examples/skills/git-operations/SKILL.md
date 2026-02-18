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
