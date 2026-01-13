# Changelog

All notable changes to DCAF will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Google Vertex AI Support**: The Google provider now exclusively uses Vertex AI with service account authentication, enabling zero-config deployment on GKE with Workload Identity.
  - New `Agent` parameters: `google_project_id`, `google_location` (both optional, auto-detected on GCP)
  - Optional environment variables: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
  - Just set `provider="google"` and deploy to GCP - it just works!

- **GCP Auto-Detection**: When running on GCP (GKE, GCE, Cloud Run), automatically detects project ID and location:
  - Uses `google.auth.default()` for project ID (works with Workload Identity)
  - Falls back to GCP metadata service for project ID and zone/location
  - Defaults location to `us-central1` if not detected
  - Only fetches once per process, caches in env vars

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
