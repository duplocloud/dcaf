# Documentation Versioning

DCAF uses [Mike](https://github.com/jimporter/mike) for documentation versioning. This allows multiple versions of documentation to coexist, so users on older versions can still access relevant docs.

---

## How It Works

Mike deploys each version to a subdirectory on GitHub Pages:

```
https://duplocloud.github.io/dcaf/          → Redirects to latest
https://duplocloud.github.io/dcaf/latest/   → Current stable version
https://duplocloud.github.io/dcaf/2.0/      → Version 2.0 docs
https://duplocloud.github.io/dcaf/1.0/      → Version 1.0 docs
```

A version selector dropdown appears in the header, allowing users to switch between versions.

---

## Commands

### Deploy a New Version

```bash
# Deploy version 1.0 as the latest
mike deploy 1.0 latest --update-aliases

# Later, deploy version 2.0 as the new latest
mike deploy 2.0 latest --update-aliases
```

The `--update-aliases` flag moves the `latest` alias to point to the new version.

### Deploy Without Changing Latest

```bash
# Deploy a patch version without making it latest
mike deploy 1.1

# Deploy a beta version
mike deploy 2.0-beta
```

### List Deployed Versions

```bash
mike list
```

Output:
```
1.0
2.0 [latest]
```

### Set an Alias

```bash
# Make 2.0 the "stable" alias
mike alias 2.0 stable

# Make 1.0 the "legacy" alias
mike alias 1.0 legacy
```

### Delete a Version

```bash
mike delete 1.0-beta
```

### Serve Locally

```bash
# Preview versioned docs locally
mike serve

# Opens at http://localhost:8000
```

---

## Versioning Workflow

### Initial Release

```bash
# First time deploying docs
mike deploy 0.1.0 latest --update-aliases --push
```

### Minor/Patch Updates

For documentation fixes that apply to the current version:

```bash
# Just rebuild and redeploy the current version
mike deploy 2.0 latest --update-aliases --push
```

### Major Version Release

When releasing a new major version:

```bash
# Deploy new version and update latest alias
mike deploy 3.0 latest --update-aliases --push

# Old versions (1.0, 2.0) remain accessible
```

### Maintaining Old Versions

To update docs for an older version:

```bash
# Checkout the old version's branch/tag
git checkout v1.0

# Deploy to that version slot
mike deploy 1.0 --push

# Switch back
git checkout main
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/docs.yml
name: Deploy Docs

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for mike
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -r requirements-docs.txt
      
      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      
      - name: Deploy docs
        run: |
          # For tagged releases, deploy that version
          if [[ "$GITHUB_REF" == refs/tags/v* ]]; then
            VERSION=${GITHUB_REF#refs/tags/v}
            mike deploy $VERSION latest --update-aliases --push
          else
            # For main branch, deploy as 'dev'
            mike deploy dev --push
          fi
```

---

## Best Practices

1. **Use semantic versioning**: Match your doc versions to your code versions (1.0, 2.0, etc.)

2. **Keep `latest` updated**: Always point `latest` to the current stable version

3. **Don't delete old versions hastily**: Users may still be on older versions

4. **Use aliases**: Create meaningful aliases like `stable`, `legacy`, `dev`

5. **Document breaking changes**: When updating docs, note what changed between versions

---

## Configuration

Mike is configured in `mkdocs.yml`:

```yaml
extra:
  version:
    provider: mike
    default: latest  # Default version when accessing root URL
```

This enables the version selector in the Material theme header.

