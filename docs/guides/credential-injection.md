# Credential Injection

DCAF's `CredentialManager` centralises all cloud credential handling — Kubernetes kubeconfigs, AWS keys, and GCP service-account JSON files — so individual agents never have to decode, write, or clean up credential material themselves.

---

## How It Works

When a request arrives the `AgentService` passes the `PlatformContext` through a `CredentialManager` before calling the runtime:

1. **K8s scopes** — builds a merged kubeconfig (one context per scope), writes it to a temp file, and adds `kubeconfig_path` to the context dict the agent receives.
2. **AWS scopes** — builds per-scope env dicts (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION`).
3. **GCP scopes** — writes per-scope service-account JSON key files, builds per-scope env dicts (`GOOGLE_APPLICATION_CREDENTIALS`).
4. **Cleanup** — all temp files are deleted after the request completes (async context manager).

The agent runtime receives an enhanced `platform_context` dict containing `kubeconfig_path` (if applicable) and can call `PreparedCredentials.get_subprocess_env(scope_name)` to get a ready-to-use env dict for subprocess calls.

---

## Scopes Wire Format

Credentials arrive in `platform_context.scopes` as a list of scope objects matching Pranav's credential selector payload:

```json
{
  "messages": [{
    "role": "user",
    "content": "list pods",
    "platform_context": {
      "scopes": [
        {
          "ProviderInfo": {
            "Type": "eks",
            "Name": "prod-cluster",
            "AccountId": "https://prod-k8s-api.example.com"
          },
          "Credential": {
            "Data": {
              "token": "eyJ...",
              "base64certdata": "LS0tLS1CRUdJTi..."
            }
          }
        }
      ]
    }
  }]
}
```

### Supported Types

| `ProviderInfo.Type` | Category | What CredentialManager produces |
|---------------------|----------|----------------------------------|
| `eks` | Kubernetes | merged kubeconfig → `kubeconfig_path` |
| `gke` | Kubernetes | merged kubeconfig → `kubeconfig_path` |
| `kubernetes` | Kubernetes | merged kubeconfig → `kubeconfig_path` |
| `aws` | AWS | per-scope env dict with `AWS_*` vars |
| `gcp` | GCP | per-scope JSON key file → `GOOGLE_APPLICATION_CREDENTIALS` |

### Credential.Data Fields

**K8s scopes (eks / gke / kubernetes):**

| Field | Description |
|-------|-------------|
| `token` | Bearer token for the cluster API server |
| `base64certdata` | Base64-encoded cluster CA certificate |

**AWS scopes:**

| Field | Description |
|-------|-------------|
| `access_key` | AWS access key ID |
| `secret_key` | AWS secret access key |
| `session_token` | STS session token (required for temporary/JIT credentials) |
| `region` | AWS region (e.g. `us-east-1`) |

**GCP scopes:**

| Field | Description |
|-------|-------------|
| `service_account_json` | Full service-account JSON key as a string |

---

## Multi-Scope Requests

A single request can include multiple scopes of different types. All scopes are processed; K8s scopes are merged into a single kubeconfig with one context per scope.

```json
"scopes": [
  {
    "ProviderInfo": {"Type": "eks", "Name": "prod-cluster", "AccountId": "https://..."},
    "Credential": {"Data": {"token": "eyJ...", "base64certdata": "LS0t..."}}
  },
  {
    "ProviderInfo": {"Type": "aws", "Name": "prod-aws", "AccountId": "123456789012"},
    "Credential": {"Data": {"access_key": "AKIA...", "secret_key": "...", "region": "us-east-1"}}
  }
]
```

---

## Legacy Base64 Kubeconfig

Callers that haven't migrated to scopes can still pass a single base64-encoded kubeconfig directly:

```json
"platform_context": {
  "kubeconfig": "<base64-encoded kubeconfig YAML>"
}
```

`CredentialManager` decodes it and writes a temp file. The `kubeconfig_path` key is added to `platform_context` exactly as with scopes. Both paths clean up the temp file after the request.

> **Note:** If both `kubeconfig_path` (pre-populated by an upstream pass) and `kubeconfig` (base64) are present, `kubeconfig_path` takes precedence and no temp file is written.

---

## AWS Explicit Credentials (ModelFactory)

When AWS credentials are passed via environment variables (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`), `ModelFactory._create_bedrock_model()` creates an explicit `aioboto3.Session` with those credentials. This supports DuploCloud JIT (short-lived STS) credentials:

```bash
AWS_ACCESS_KEY_ID=ASIA3XIJPJFD...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...          # required for STS/JIT credentials
AWS_REGION=us-east-1
```

The three credential resolution paths, in priority order:

| Priority | Condition | Behaviour |
|----------|-----------|-----------|
| 1 | `AWS_PROFILE` set | Named profile session |
| 2 | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` set | Explicit session with those credentials |
| 3 | Neither | Default IAM / credential chain (EC2 instance role, ECS task role, etc.) |

---

## Local Development (`DCAF_IS_LOCAL`)

In production, credentials are injected at runtime via scopes. In local development, set `DCAF_IS_LOCAL=true` so DCAF expects credentials from the environment instead:

```bash
DCAF_IS_LOCAL=true
AWS_PROFILE=my-local-profile
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

See [Environment Configuration](environment-configuration.md#dcaf_is_local) for details.

---

## Security Notes

- `CredentialManager` **never mutates `os.environ`** — credentials flow via subprocess env dicts and explicit SDK session objects, keeping concurrent async requests isolated.
- Temp files are always cleaned up in `CredentialManager.__aexit__`, even if the request raises an exception.
- Do not log raw credential values; debug logging only records key names, not values.
