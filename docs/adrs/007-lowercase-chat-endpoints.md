# ADR-007: Lowercase Chat Endpoint Naming

**Status**: Accepted  
**Date**: 2024-12-22  
**Deciders**: Engineering Team

## Context

The original API endpoints used camelCase naming:
- `POST /api/sendMessage`
- `POST /api/sendMessageStream`

We need to establish a naming convention for the DCAF Core API endpoints that:
1. Avoids future compatibility issues
2. Accurately describes the operation
3. Follows REST best practices

## Decision

Adopt lowercase, hyphenated endpoint names:
- `POST /api/chat` (replaces `/api/sendMessage`)
- `POST /api/chat-stream` (replaces `/api/sendMessageStream`)

Legacy endpoints are preserved for backwards compatibility but marked as deprecated.

## Rationale

### 1. Future-Proofing for Encryption/Security

If we later need to enable case-sensitive URL matching (e.g., for encrypted tokens, signed URLs, or security middleware), mixed-case endpoints become a liability.

**Problem scenario:**
```
# Original endpoint
POST /api/sendMessage

# With case-sensitive matching enabled, these would be DIFFERENT endpoints:
POST /api/sendmessage  ← 404
POST /api/SendMessage  ← 404
POST /api/SENDMESSAGE  ← 404
```

A customer using `sendmessage` (all lowercase) in their integration would experience a breaking change when case-sensitivity is enabled.

**Solution:**
By starting with all lowercase (`/api/chat`), we avoid this entire class of issues. Lowercase URLs are:
- Case-insensitive by default on most servers
- Still work correctly when case-sensitivity is enabled
- Consistent regardless of client behavior

### 2. Semantic Accuracy

The original name `sendMessage` is misleading:

| Name | Implies | Reality |
|------|---------|---------|
| `sendMessage` | Agent sends a message | Agent **receives** a message and **responds** |
| `chat` | Bidirectional conversation | ✅ Accurately describes the interaction |

The agent doesn't "send" messages—it receives them from the helpdesk middleware and responds. The term "chat" correctly conveys:
- A conversation is happening
- Messages flow both directions
- The user and agent are participants

### 3. REST Best Practices

RESTful API conventions favor:
- Lowercase paths
- Hyphen-separated words (not camelCase)
- Nouns over verbs (resources, not actions)

| Convention | Example |
|------------|---------|
| ❌ camelCase | `/api/sendMessage` |
| ❌ Verb-first | `/api/sendMessage` |
| ✅ Lowercase | `/api/chat` |
| ✅ Hyphenated | `/api/chat-stream` |
| ✅ Noun/resource | `/api/chat` |

## Consequences

### Positive

- **No future breaking changes** from case-sensitivity requirements
- **Clearer semantics** for developers integrating with the API
- **Follows standards** that developers expect
- **Backwards compatible** via legacy endpoint aliases

### Negative

- **Two endpoints per function** (during transition period)
- **Documentation overhead** to explain deprecation

### Migration Path

1. New integrations should use `/api/chat` and `/api/chat-stream`
2. Existing integrations continue working with `/api/sendMessage` and `/api/sendMessageStream`
3. Legacy endpoints will be removed in a future major version (with ample warning)

## Endpoints Summary

| New (Preferred) | Legacy (Deprecated) | Description |
|-----------------|---------------------|-------------|
| `GET /health` | — | Health check |
| `POST /api/chat` | `POST /api/sendMessage` | Synchronous chat |
| `POST /api/chat-stream` | `POST /api/sendMessageStream` | Streaming chat |

## Related

- [REST API Naming Conventions](https://restfulapi.net/resource-naming/)
- [URI Case Sensitivity (RFC 3986)](https://www.rfc-editor.org/rfc/rfc3986#section-6.2.2.1)
