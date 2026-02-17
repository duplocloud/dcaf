# Skills Guide

This guide covers how to use skills with DCAF agents. Skills are reusable instruction sets that extend an agent's capabilities at runtime, loaded dynamically from platform context.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [How Skills Work](#how-skills-work)
4. [Platform Context Integration](#platform-context-integration)
5. [Storage and Caching](#storage-and-caching)
6. [Skill Formats](#skill-formats)
7. [Agent Integration](#agent-integration)
8. [Error Handling](#error-handling)
9. [Environment Configuration](#environment-configuration)
10. [Best Practices](#best-practices)

---

## Introduction

Skills are packaged instructions, reference documents, and scripts that agents can load at runtime. They are powered by [Agno's skills system](https://docs.agno.com/skills/loading-skills), which adds tools to the agent that allow it to retrieve skill instructions, reference materials, and execute scripts on demand.

### What Are Skills?

A skill is a directory containing a `SKILL.md` file with YAML frontmatter and markdown instructions. Skills can optionally include reference documents and executable scripts:

```
my-skill/
  SKILL.md          # Required - skill instructions with YAML frontmatter
  references/       # Optional - reference documents
    api-spec.md
  scripts/          # Optional - executable scripts
    deploy.sh
```

### When to Use Skills

Skills are useful when you want to:

- Give agents domain-specific instructions without modifying their system prompt
- Share reusable instruction sets across multiple agents
- Version and deploy agent capabilities independently of the agent code
- Load different skill sets based on the deployment context

---

## Quick Start

### 1. Create a Skill

Create a `SKILL.md` file:

```markdown
---
name: k8s-debug
description: Kubernetes debugging procedures
---

# Kubernetes Debugging

When debugging Kubernetes issues, follow these steps:

1. Check pod status with `kubectl get pods`
2. Review pod logs with `kubectl logs <pod>`
3. Describe the pod for events with `kubectl describe pod <pod>`
```

### 2. Host the Skill

Package your skill as either:

- A **zip file** containing `SKILL.md` and any supporting files
- A **markdown file** served directly from a URL

Host it at an accessible URL (e.g., an S3 bucket, internal HTTP server, or artifact registry).

### 3. Pass Skills via Platform Context

Include the `skills` array in your platform context when sending messages to the agent:

```json
{
  "role": "user",
  "content": "Debug why my pods are crashing",
  "platform_context": {
    "tenant_id": "my-tenant",
    "skills": [
      {
        "name": "k8s-debug",
        "version": "1.0.0",
        "url": "https://skills.example.com/k8s-debug/1.0.0/skill.zip"
      }
    ]
  }
}
```

The agent will automatically download, cache, and load the skill.

---

## How Skills Work

The skills system follows this flow:

```
Platform Context (skills array)
  │
  ▼
SkillManager.resolve_skills()
  │
  ├─ Check local cache: {storage}/skills/{name}/{version}/SKILL.md
  │   ├─ Found → use cached version
  │   └─ Not found → fetch from URL
  │       ├─ Detect format (zip or markdown)
  │       ├─ Download and validate
  │       ├─ Cache locally (atomic rename)
  │       └─ Use cached version
  │
  ▼
Agno Skills object (one LocalSkills loader per skill)
  │
  ▼
AgnoAgent(skills=...) → Agent gets skill tools automatically
```

Once loaded, the agent gains three built-in tools:

| Tool | Purpose |
|------|---------|
| `get_skill_instructions(skill_name)` | Retrieve the full skill instructions |
| `get_skill_reference(skill_name, path)` | Load a reference document from the skill |
| `get_skill_script(skill_name, path)` | Read or execute a script from the skill |

The agent's system prompt is also augmented with skill names and descriptions, so it can discover and use skills without being explicitly told about them.

---

## Platform Context Integration

Skills are passed as a top-level `skills` array in the platform context:

```python
platform_context = {
    "tenant_id": "production",
    "k8s_namespace": "web",
    "skills": [
        {
            "name": "k8s-debug",
            "version": "1.0.0",
            "url": "https://skills.example.com/k8s-debug-1.0.0.zip"
        },
        {
            "name": "aws-helper",
            "version": "2.1.0",
            "url": "https://skills.example.com/aws-helper.md"
        }
    ]
}
```

Each skill definition has three required fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the skill |
| `version` | string | Exact version string for cache lookup |
| `url` | string | URL to fetch the skill from if not cached |

You can pass multiple skills — the agent will load all of them.

---

## Storage and Caching

### Cache Layout

Skills are cached on the local filesystem at:

```
{PERSISTENT_VOLUME_STORAGE}/skills/{name}/{version}/
```

For example:

```
/data/skills/
  k8s-debug/
    1.0.0/
      SKILL.md
      scripts/
        check-pods.sh
    2.0.0/
      SKILL.md
  aws-helper/
    2.1.0/
      SKILL.md
```

### Cache Behavior

- **Cache-first**: If a skill version exists locally, it is always used without checking the remote URL
- **Immutable versions**: Once cached, a version is never re-downloaded. To deploy updates, publish under a new version string
- **Exact version matching**: Version `"1.0.0"` only matches `"1.0.0"` — there is no semantic version comparison

### Storage Path

The storage root is configured via the `PERSISTENT_VOLUME_STORAGE` environment variable:

```bash
export PERSISTENT_VOLUME_STORAGE=/mnt/shared-storage
```

If not set, it defaults to `/data`.

---

## Skill Formats

### Zip Files

Zip archives can contain `SKILL.md` plus any supporting files:

```
skill.zip
  ├── SKILL.md           # Required at zip root
  ├── references/
  │   └── api-spec.md
  └── scripts/
      └── deploy.sh
```

!!! warning "SKILL.md must be at the zip root"
    If `SKILL.md` is not found at the root of the zip archive, the skill will be rejected with an error log: `Expected SKILL.md file missing at folder root`.

### Markdown Files

A single markdown file served directly from a URL. It will be saved as `SKILL.md` in the cache directory:

```markdown
---
name: my-skill
description: A simple single-file skill
---

# My Skill Instructions

Do the thing.
```

### Format Detection

The format is detected automatically using this order of precedence:

1. **File extension in the URL**: `.zip` → zip archive; `.md`, `.txt`, `.markdown` → text file
2. **Content-Type header**: `application/zip` → zip archive; anything else → text file

---

## Agent Integration

Skills are resolved and loaded automatically by the `AgnoAdapter` when creating an agent. No code changes are needed in your agent — simply pass the `skills` array in the platform context.

### Under the Hood

The `AgnoAdapter._create_agent_async()` method:

1. Extracts the `skills` array from `platform_context`
2. Creates `SkillDefinition` value objects
3. Calls `SkillManager().resolve_skills()` to fetch/cache/load
4. Passes the resulting `Skills` object to `AgnoAgent(skills=...)`

```python
# This happens automatically — you don't need to write this code
agent = AgnoAgent(
    model=model,
    instructions=system_prompt,
    tools=tools,
    skills=resolved_skills,  # ← automatically populated from platform context
)
```

---

## Error Handling

The skills system is designed to be resilient. Skill failures never prevent the agent from starting.

| Scenario | Behavior |
|----------|----------|
| URL unreachable | Skill skipped, error logged, agent starts without it |
| HTTP error (4xx, 5xx) | Skill skipped, error logged |
| Invalid zip file | Skill skipped, error logged |
| Zip missing `SKILL.md` | Skill skipped, error logged |
| Download exceeds 50 MB | Skill skipped, error logged |
| Request timeout (>30s) | Skill skipped, error logged |
| All skills fail | Agent starts with no skills loaded |

Errors are logged at the `ERROR` level with full context (skill name, version, URL).

---

## Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PERSISTENT_VOLUME_STORAGE` | `/data` | Root directory for the skill cache |

This variable can point to any filesystem path — local disk, network-mounted volume, or container-mounted persistent storage.

---

## Best Practices

### Skill Design

- **Keep skills focused**: Each skill should cover one domain or workflow
- **Use YAML frontmatter**: Always include `name` and `description` in your `SKILL.md` frontmatter — Agno uses these for skill discovery
- **Include references**: Put supplementary documents in a `references/` directory within your skill
- **Version meaningfully**: Use version strings that communicate the nature of changes

### Deployment

- **Use immutable versions**: Never modify a published skill version. Publish a new version instead
- **Pre-warm caches**: For latency-sensitive deployments, pre-populate the skill cache on your persistent volume
- **Monitor skill loading**: Check agent logs for skill resolution failures at startup

### Security

- **Host skills on trusted infrastructure**: Skills are downloaded from the provided URLs — ensure these are internal or authenticated endpoints
- **Zip files are validated**: Path traversal attacks in zip archives are detected and rejected
- **Download size is limited**: Skills larger than 50 MB are rejected to prevent resource exhaustion
