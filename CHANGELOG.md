# Changelog

All notable changes to DCAF will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Google Vertex AI Support**: Added support for Google Vertex AI with service account authentication, enabling deployment on GKE with Workload Identity.
  - New `Agent` parameters: `vertexai`, `google_project_id`, `google_location`
  - New environment variables: `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
  - Updated `_create_google_model()` in the Agno adapter to support Vertex AI configuration
  - Documentation updated in `docs/guides/working-with-gemini.md`

- **GCP Metadata Auto-Detection**: When running on GCP (GKE, GCE, Cloud Run), automatically fetches project ID and location from the metadata service.
  - Sets `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` environment variables automatically
  - Only fetches once per process, caches in env vars
  - Explicit configuration always takes priority over auto-detected values
  - Fails silently when not running on GCP

- **Automatic Vertex AI Mode**: When using `provider="google"` without an API key, Vertex AI mode is now automatic.
  - No need to set `vertexai=True` or `GOOGLE_GENAI_USE_VERTEXAI=true`
  - Just set `provider="google"` and deploy to GCP - it just works!
  - If you provide an API key, Google AI Studio mode is used instead

- **AgentMessage convenience methods**: Added methods to simplify HelpDesk and API integrations.
  - `Agent.chat()`: New method that returns `AgentMessage` directly (wire format ready for JSON serialization)
  - `AgentResponse.to_message()`: Converts an `AgentResponse` to `AgentMessage` for API responses

### Removed

- **`high_risk_tools` parameter**: Removed the `high_risk_tools` parameter from `Agent`, `CoreConfig`, and `ApprovalPolicy`. Tool approval is now controlled solely via the `@tool(requires_approval=True)` decorator.
  - Removed from `dcaf/core/agent.py`
  - Removed from `dcaf/core/infrastructure/config.py`
  - Removed from `dcaf/core/domain/services/approval_policy.py`
  - Updated documentation across multiple files

### Changed

- Simplified `_check_requires_approval()` method in `Agent` class
- Simplified `ApprovalPolicy.check()` method to only check tool-level `requires_approval` flag
