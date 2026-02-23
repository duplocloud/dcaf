# ADR-008: Skills Feature Design Decisions

## Status

Accepted

## Context

DCAF agents need the ability to load domain-specific instructions, reference materials, and scripts at runtime. These "skills" are defined externally and passed to agents via the platform context, allowing different deployments to configure different agent capabilities without code changes.

The skills system introduces several design challenges around caching, concurrency, error handling, content detection, and security that required explicit decisions.

## Decisions

### 1. Concurrent Access: Atomic Rename Pattern

**Problem:** Multiple agent instances could simultaneously try to download and cache the same skill. This is especially relevant when the cache is on shared network storage (e.g., an NFS mount or a Kubernetes PersistentVolume shared across pods).

**Considered alternatives:**

- **File-based locking** (`fcntl.flock` or lock files): Works on local disk but is unreliable on many network filesystems (NFS, CIFS)
- **Database-backed locking**: Adds an infrastructure dependency for a simple caching problem
- **Atomic rename** (chosen): Download to a uniquely-named temp directory, then atomically rename to the target path

**Decision:** Use the atomic rename pattern.

Each download goes to a uniquely-named temporary directory (`/tmp/skill_{name}_{random}/`). Once the download and extraction are complete, we atomically rename the temp directory to the target cache path. If two processes race:

1. Both download to separate temp directories
2. One `rename()` succeeds; the other gets an `OSError` (target already exists)
3. The "loser" deletes its temp directory and uses the existing cached version

This approach requires no locking, works on both local and network drives, and the final state is always correct because we trust local cached versions.

### 2. Error Handling: Skip and Continue

**Problem:** What happens when a skill URL is unreachable, returns corrupted data, or the zip file is malformed?

**Decision:** Skip the failing skill and continue loading the rest. The agent starts without the failed skill.

This prevents one bad skill URL from blocking the entire agent from functioning. All errors are logged at the `ERROR` level with full context (skill name, version, URL) so operators can diagnose issues.

Specific scenarios:

| Scenario | Behavior |
|----------|----------|
| URL unreachable or HTTP error | Log error, skip skill |
| Invalid zip file | Log error, clean up temp dir, skip skill |
| Zip missing `SKILL.md` at root | Log error: "Expected SKILL.md file missing at folder root", skip skill |
| Download exceeds 50 MB | Log error, skip skill |
| Request timeout (>30s) | Log error, skip skill |
| All skills fail to resolve | Agent starts with no skills |

### 3. Content Type Detection: Extension First, Then Header

**Problem:** Skill URLs can return either zip archives or markdown/text files. We need to determine which format we're dealing with to process the response correctly.

**Considered alternatives:**

- **Content-Type header only**: Unreliable — servers frequently misreport content types (e.g., returning `application/octet-stream` for markdown files)
- **File extension only**: Doesn't work for URLs without extensions (e.g., API endpoints)
- **Extension first, then Content-Type** (chosen): Most reliable approach

**Decision:** Check file extension in the URL first, fall back to the Content-Type response header.

```
1. URL ends in .zip           → treat as zip archive
2. URL ends in .md/.txt/.markdown → treat as text
3. Content-Type contains "zip" → treat as zip archive
4. Anything else              → treat as text (default)
```

### 4. Version Matching and Cache Trust

**Problem:** How should we compare version strings? And once a skill is cached locally, should we re-validate it against the remote source?

**Decision:**

- **Exact string matching** for versions. Version `"1.0.0"` only matches `"1.0.0"`. No semantic version comparison (e.g., `"1.0.0"` does not satisfy `"^1.0.0"`). This keeps the logic simple and predictable.

- **Always trust local cache.** If `{storage}/skills/{name}/{version}/SKILL.md` exists on disk, we use it without checking the remote URL. This means:
  - Once a version is cached, it's permanent for that version string
  - To deploy updates, publish under a new version string
  - This eliminates unnecessary network calls and makes the system resilient to remote outages

### 5. Security: Zip Path Traversal Protection

**Problem:** Skills are downloaded from URLs which could potentially serve malicious content. A crafted zip file could contain entries with `../` in the path (zip-slip attack), allowing files to be extracted outside the intended cache directory.

**Decision:** Validate every zip member path before extraction. Each path is resolved and checked to ensure it stays within the target directory. If any path attempts traversal, the entire skill is rejected.

Additionally:
- Downloads are limited to 50 MB to prevent resource exhaustion
- HTTP requests have a 30-second timeout
- `SKILL.md` must exist at the zip root or the skill is rejected

### 6. Agno SDK Upgrade (2.3.21 → 2.5.2)

**Problem:** The project pinned Agno to v2.3.21 to avoid a known bug in v2.3.26 (related to handling `[]` in tool call parameters). However, the `agno.skills` module (`Skills`, `LocalSkills`) was added after v2.3.21.

**Decision:** Upgrade to Agno v2.5.2. The full test suite (430+ tests) was run to verify no regressions from the old bug. All existing tests pass.

### 7. Storage Layout and Environment Variable

**Decision:** Skills are cached at `{PERSISTENT_VOLUME_STORAGE}/skills/{name}/{version}/`.

The `PERSISTENT_VOLUME_STORAGE` environment variable defaults to `/data`. It uses no `DCAF_` prefix because it is a general-purpose storage path that may be shared with other services on the same infrastructure.

The storage root is resolved in priority order: constructor argument → `PERSISTENT_VOLUME_STORAGE` env var → `/data` built-in default.

```
/data/                              # PERSISTENT_VOLUME_STORAGE
  skills/
    k8s-debug/
      1.0.0/
        SKILL.md
        scripts/check-pods.sh
      2.0.0/
        SKILL.md
    aws-helper/
      2.1.0/
        SKILL.md
```

### 8. External Platform Format Translation

**Problem:** The DuploCloud platform delivers skills in a PascalCase format (`Format`, `Name`, `Version`, `IsActive`, `SkillMd`, `FileStoreSignedUrl`) that differs from the internal DCAF wire format (`name`, `version`, `url`).

**Decision:** A thin translation layer (`skill_translator.py`) detects the format by checking for the presence of the `Format` key and converts PascalCase entries to internal `SkillDefinition` objects. Both formats can coexist in the same request.

Two external formats are supported:

- **`SkillMd`** — inline markdown content embedded directly in the request. Written to the local cache on every request to ensure freshness. No URL fetch needed.
- **`Package`** — zip archive downloaded from a `FileStoreSignedUrl` (typically a pre-signed S3 URL). Follows the same fetch-and-cache pipeline as the URL-based internal format.

Inactive skills (`"IsActive": false`) are silently skipped by the translation layer.

### 9. Zip Root Auto-Elevation

**Problem:** Tools like macOS Finder wrap zip contents in a top-level folder (e.g., `my-skill/SKILL.md`). Requiring `SKILL.md` strictly at the zip root would reject these common archives.

**Decision:** If `SKILL.md` is not at the zip root, the extractor looks exactly one directory level deep. If a single subdirectory contains `SKILL.md`, its contents are promoted to the root (elevated). `__MACOSX` metadata directories are removed during elevation. If `SKILL.md` is not found at root or one level deep, the skill is rejected.

This strictly limits the elevation depth to one level to avoid ambiguity when a zip contains multiple subdirectories.

## Consequences

### Positive

- **Resilient**: Skill failures never prevent agent startup
- **Concurrent-safe**: Atomic rename works on local and network storage without locking
- **Secure**: Zip path traversal, size limits, and timeouts protect against malicious inputs
- **Simple caching**: Immutable versions with exact string matching — no cache invalidation complexity
- **Zero-config for agents**: Skills are loaded automatically from platform context

### Negative

- **No cache invalidation**: If a bad skill version is cached, the only fix is to delete it from the filesystem or publish a new version
- **No pre-fetching**: Skills are fetched on first use, which adds latency to the first request. Operators can pre-warm caches to mitigate this
- **50 MB limit**: Large skill packages (with extensive reference materials) may need to be split into multiple skills

### Risks

- **Network storage performance**: Atomic rename on slow network filesystems could add latency
- **Disk space**: Without automatic cleanup, old skill versions accumulate indefinitely
