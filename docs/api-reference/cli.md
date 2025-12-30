# CLI API Reference

The DCAF Command Line Interface provides utilities for managing AWS credentials, Docker images, and agent deployments.

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Commands](#commands)
4. [Environment Variables](#environment-variables)
5. [Examples](#examples)

---

## Overview

The `dcaf` CLI provides tools for:

- **AWS credential management** - Update `.env` files with fresh credentials
- **Docker builds** - Build and push images to Amazon ECR
- **Agent deployment** - Deploy agents to DuploCloud (coming soon)

### Installation

When you install DCAF, the CLI is automatically available:

```bash
# Install DCAF
pip install git+https://github.com/duplocloud/service-desk-agents.git

# Verify installation
dcaf --help
```

---

## Installation

### Requirements

- **Python 3.9+**
- **AWS CLI** (for ECR commands)
- **Docker** (for build/push commands)
- **duplo-jit** (for DuploCloud credential management)

### Installing duplo-jit

```bash
# See DuploCloud documentation for installation
# https://docs.duplocloud.com/docs/overview/use-cases/jit-access
```

---

## Commands

### dcaf --help

Display available commands.

```bash
dcaf --help
```

Output:
```
usage: dcaf [-h] {env-update-aws-creds,docker-build-push-ecr,deploy-agent} ...

DuploCloud Agent Builder CLI

positional arguments:
  {env-update-aws-creds,docker-build-push-ecr,deploy-agent}
                        Available commands

optional arguments:
  -h, --help            show this help message and exit
```

---

### dcaf env-update-aws-creds

Update AWS credentials in the `.env` file using DuploCloud JIT access.

```bash
dcaf env-update-aws-creds [--tenant TENANT] [--host HOST]
```

#### Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--tenant` | `DUPLO_TENANT` | DuploCloud tenant name |
| `--host` | `DUPLO_HOST` | DuploCloud host URL |

#### Behavior

1. Calls `duplo-jit aws` to fetch temporary credentials
2. Parses the JSON response
3. Updates or creates `.env` file with:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SESSION_TOKEN`

#### Requirements

- `duplo-jit` must be installed and configured
- Interactive authentication may be required

#### Examples

```bash
# Using command line arguments
dcaf env-update-aws-creds --tenant=my-tenant --host=https://my-duplo.duplocloud.net

# Using environment variables
export DUPLO_TENANT=my-tenant
export DUPLO_HOST=https://my-duplo.duplocloud.net
dcaf env-update-aws-creds

# Mixed usage (env vars with override)
export DUPLO_HOST=https://my-duplo.duplocloud.net
dcaf env-update-aws-creds --tenant=different-tenant
```

#### Output

```
Using tenant: my-tenant
Using host: https://my-duplo.duplocloud.net
Fetching AWS credentials using duplo-jit...
Updating existing .env file...
✅ AWS credentials updated in /path/to/project/.env
⚠️  Make sure .env is in your .gitignore!
```

#### Error Handling

```bash
# Missing tenant
Error: Tenant not specified. Set DUPLO_TENANT env var or use --tenant flag

# Missing host
Error: Host not specified. Set DUPLO_HOST env var or use --host flag

# duplo-jit not installed
Error: duplo-jit is not installed or not in PATH
Please install duplo-jit: https://docs.duplocloud.com/docs/overview/use-cases/jit-access
```

---

### dcaf docker-build-push-ecr

Build a Docker image and push it to Amazon ECR.

```bash
dcaf docker-build-push-ecr TAG [--repo-name NAME] [--registry URI] [--aws-profile PROFILE] [--region REGION] [--dockerfile PATH]
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `TAG` | Yes | Image tag (e.g., `latest`, `v1.0.0`) |

#### Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `--repo-name` | `ECR_REPOSITORY_NAME` | - | ECR repository name |
| `--registry` | `ECR_REGISTRY` | - | ECR registry URI |
| `--aws-profile` | - | - | AWS profile to use |
| `--region` | `AWS_DEFAULT_REGION` | `us-east-1` | AWS region |
| `--dockerfile` | - | `Dockerfile` | Path to Dockerfile |

#### Steps

1. **Authenticate** - `aws ecr get-login-password | docker login`
2. **Build** - `docker build -t repo:tag -f Dockerfile .`
3. **Tag** - `docker tag repo:tag registry/repo:tag`
4. **Push** - `docker push registry/repo:tag`

#### Requirements

- Docker installed and running
- AWS CLI configured
- ECR repository exists

#### Examples

```bash
# Using all command line arguments
dcaf docker-build-push-ecr v1.0.0 \
  --repo-name=my-agent \
  --registry=123456789012.dkr.ecr.us-east-1.amazonaws.com \
  --region=us-east-1

# Using environment variables
export ECR_REPOSITORY_NAME=my-agent
export ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com
export AWS_DEFAULT_REGION=us-east-1
dcaf docker-build-push-ecr latest

# With AWS profile
dcaf docker-build-push-ecr v2.0.0 \
  --repo-name=my-agent \
  --registry=123456789012.dkr.ecr.us-east-1.amazonaws.com \
  --aws-profile=production

# Custom Dockerfile
dcaf docker-build-push-ecr latest \
  --repo-name=my-agent \
  --registry=123456789012.dkr.ecr.us-east-1.amazonaws.com \
  --dockerfile=Dockerfile.prod
```

#### Output

```
[1/4] Authenticating Docker to ECR registry...
Running: aws ecr get-login-password --region us-east-1  | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
✓ Successfully authenticated to ECR

[2/4] Building Docker image...
Running: docker build -t my-agent:v1.0.0 -f Dockerfile .
✓ Successfully built my-agent:v1.0.0

[3/4] Tagging image for ECR...
Running: docker tag my-agent:v1.0.0 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-agent:v1.0.0
✓ Tagged as 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-agent:v1.0.0

[4/4] Pushing to ECR...
Running: docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-agent:v1.0.0

✅ Successfully pushed 123456789012.dkr.ecr.us-east-1.amazonaws.com/my-agent:v1.0.0
```

---

### dcaf deploy-agent

Deploy an agent to DuploCloud.

```bash
dcaf deploy-agent AGENT_NAME [--token TOKEN]
```

> **Note:** This command is not yet fully implemented.

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `AGENT_NAME` | Yes | Name of the agent to deploy |

#### Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--token` | `DUPLO_TOKEN` | DuploCloud API token |

#### Example

```bash
dcaf deploy-agent my-k8s-agent --token=eyJ...
```

---

## Environment Variables

### Summary

| Variable | Command | Description |
|----------|---------|-------------|
| `DUPLO_TENANT` | `env-update-aws-creds` | DuploCloud tenant name |
| `DUPLO_HOST` | `env-update-aws-creds` | DuploCloud host URL |
| `DUPLO_TOKEN` | `deploy-agent` | DuploCloud API token |
| `ECR_REPOSITORY_NAME` | `docker-build-push-ecr` | ECR repository name |
| `ECR_REGISTRY` | `docker-build-push-ecr` | ECR registry URI |
| `AWS_DEFAULT_REGION` | `docker-build-push-ecr` | AWS region |

### Example .env File

```bash
# DuploCloud Configuration
DUPLO_HOST=https://my-duplo.duplocloud.net
DUPLO_TENANT=production
DUPLO_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# AWS Configuration (auto-updated by dcaf env-update-aws-creds)
AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AWS_SESSION_TOKEN="FwoGZXIvYXdzEBY..."
AWS_DEFAULT_REGION=us-east-1

# ECR Configuration
ECR_REPOSITORY_NAME=my-agent
ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com

# Bedrock Configuration
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-sonnet-20240620-v1:0
```

---

## Examples

### Example 1: Complete Deployment Workflow

```bash
#!/bin/bash
# deploy.sh - Complete deployment script

set -e

# Load environment
source .env

# 1. Refresh AWS credentials
echo "Refreshing AWS credentials..."
dcaf env-update-aws-creds \
  --tenant=$DUPLO_TENANT \
  --host=$DUPLO_HOST

# Reload .env with new credentials
source .env

# 2. Build and push Docker image
VERSION=$(git describe --tags --always)
echo "Building version: $VERSION"

dcaf docker-build-push-ecr $VERSION \
  --repo-name=$ECR_REPOSITORY_NAME \
  --registry=$ECR_REGISTRY \
  --region=$AWS_DEFAULT_REGION

# 3. Deploy (when implemented)
# dcaf deploy-agent my-agent --token=$DUPLO_TOKEN

echo "Deployment complete!"
```

### Example 2: CI/CD Integration

```yaml
# .github/workflows/deploy.yml
name: Deploy Agent

on:
  push:
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install DCAF
        run: pip install git+https://github.com/duplocloud/service-desk-agents.git
      
      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Build and Push
        env:
          ECR_REPOSITORY_NAME: my-agent
          ECR_REGISTRY: ${{ secrets.ECR_REGISTRY }}
        run: |
          VERSION=${GITHUB_REF#refs/tags/}
          dcaf docker-build-push-ecr $VERSION
```

### Example 3: Local Development Workflow

```bash
# Terminal 1: Set up credentials
export DUPLO_HOST=https://dev.duplocloud.net
export DUPLO_TENANT=dev-tenant
dcaf env-update-aws-creds

# Terminal 2: Run the agent locally
source .env
python main.py

# Terminal 3: Test the agent
curl -X POST http://localhost:8000/api/sendMessage \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

### Example 4: Multi-Environment Setup

```bash
# .env.development
DUPLO_HOST=https://dev.duplocloud.net
DUPLO_TENANT=dev-tenant
ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com
ECR_REPOSITORY_NAME=my-agent-dev

# .env.production
DUPLO_HOST=https://prod.duplocloud.net
DUPLO_TENANT=prod-tenant
ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com
ECR_REPOSITORY_NAME=my-agent-prod

# Deploy to development
cp .env.development .env
dcaf env-update-aws-creds
dcaf docker-build-push-ecr dev-$(git rev-parse --short HEAD)

# Deploy to production
cp .env.production .env
dcaf env-update-aws-creds
dcaf docker-build-push-ecr $(git describe --tags)
```

---

## Troubleshooting

### duplo-jit Not Found

```bash
Error: duplo-jit is not installed or not in PATH
```

**Solution:**
1. Install duplo-jit from [DuploCloud documentation](https://docs.duplocloud.com/docs/overview/use-cases/jit-access)
2. Ensure it's in your PATH: `which duplo-jit`

### Docker Not Running

```bash
Error: Docker is not installed or not in PATH
```

**Solution:**
1. Install Docker: https://docs.docker.com/get-docker/
2. Start Docker daemon
3. Verify: `docker --version`

### ECR Authentication Failed

```bash
Error authenticating to ECR: ...
```

**Solution:**
1. Verify AWS credentials are valid
2. Check ECR repository exists
3. Ensure IAM permissions include `ecr:GetAuthorizationToken`

### Credential Parsing Error

```bash
Error parsing duplo-jit output: ...
```

**Solution:**
1. Ensure duplo-jit is properly configured
2. Try running `duplo-jit aws --tenant=xxx --host=xxx` directly
3. Check for authentication issues

---

## See Also

- [Getting Started](../getting-started.md)
- [DuploCloud JIT Access Documentation](https://docs.duplocloud.com/docs/overview/use-cases/jit-access)
- [AWS ECR User Guide](https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html)

