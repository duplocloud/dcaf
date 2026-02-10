---
name: commit
description: Commit and push changes with automatic version bump. Prek handles formatting and linting automatically.
---

# Commit and Push Skill

Commit staged changes and push to the remote repository. Prek pre-commit hooks automatically run formatting (ruff format), linting (ruff check), type checking (mypy), and UI linting (ESLint/Prettier) when you commit.

## Usage

```
/commit [message]
```

If no message is provided, generate one based on the changes.

## What Happens Automatically

When you run `git commit`, prek automatically:
1. Formats Python code with `ruff format`
2. Lints Python code with `ruff check --fix`
3. Type checks staged Python files with `mypy`
4. Lints/formats UI files with ESLint and Prettier (if UI files are staged)

If any check fails, the commit is blocked until you fix the issues.

## Instructions

Follow these steps in order.

### Step 1: Check Status

```bash
git status
git diff --stat
```

Review what files have changed.

### Step 2: Bump Version

Increment the patch version in `pyproject.toml`:

```bash
CURRENT=$(grep -E "^version = \"" pyproject.toml | sed 's/version = "\(.*\)"/\1/')
IFS="." read -r MAJOR MINOR PATCH <<< "$CURRENT"
PATCH=$((PATCH + 1))
NEW="$MAJOR.$MINOR.$PATCH"
sed -i "" "s/^version = \"$CURRENT\"/version = \"$NEW\"/" pyproject.toml
echo "Version bumped: $CURRENT -> $NEW"
```

### Step 3: Stage All Changes

```bash
git add -A
```

### Step 4: Generate Commit Message

If no message was provided, analyze the changes and create one:
- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Keep the first line under 72 characters
- Add body if changes are complex

Guidelines:
- New files = `feat:` or `chore:`
- Modified files = `fix:`, `refactor:`, or `feat:`
- Deleted files = `chore:` or `refactor:`

### Step 5: Commit

```bash
git commit -m "type: description"
```

Prek hooks will run automatically. If they fail, fix the issues and try again.

### Step 6: Push

```bash
git push origin HEAD
```

## Example

With a message:
```
/commit fix: resolve migration chain issue
```

Without a message (Claude generates one):
```
/commit
```

## Commit Message Guidelines

- Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Keep the first line under 72 characters
- Add body if changes are complex
- End commit message with: `Co-Authored-By: Claude <noreply@anthropic.com>`

## Worktree Workflow

When working in a git worktree, commit and push to the worktree's branch, then create a PR targeting `dev`:

```bash
git push origin HEAD
gh pr create --base dev --fill
```

## Troubleshooting

If prek hooks fail:
- **ruff format/check**: Fix the reported Python issues, then `git add` and commit again
- **mypy**: Fix type errors in the staged files
- **ESLint/Prettier**: Fix UI issues in `src/pa/butler_ui/`

To skip hooks (use sparingly):
```bash
git commit --no-verify -m "message"
```
