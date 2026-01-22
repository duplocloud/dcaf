"""
GCP metadata detection for Vertex AI configuration.

This module provides a GCPMetadataManager class that handles auto-detection
of GCP project and location for Vertex AI model configuration.

The manager:
- Fetches metadata once per instance (lazy loading)
- Supports both google.auth.default() and GCP metadata service
- Is thread-safe and does not use global mutable state
"""

import logging
import os
import threading
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GCPMetadata:
    """Detected GCP metadata values."""

    project_id: str | None = None
    location: str | None = None


@dataclass
class GCPMetadataManager:
    """
    Manager for GCP metadata detection.

    Handles auto-detection of GCP project and location for Vertex AI.
    Thread-safe with lazy loading - metadata is fetched once on first access.

    Example:
        manager = GCPMetadataManager()
        project = manager.get_project()
        location = manager.get_location()

    The manager tries these sources in order:
    1. Environment variables (GOOGLE_CLOUD_PROJECT)
    2. google.auth.default() for Application Default Credentials
    3. GCP metadata service (when running on GCP)
    """

    _metadata: GCPMetadata = field(default_factory=GCPMetadata)
    _fetched: bool = field(default=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get_project(self) -> str | None:
        """
        Get GCP project ID.

        Checks environment variable first, then auto-detects if needed.

        Returns:
            Project ID or None if not detected
        """
        # Check env var first (may have been set externally)
        existing = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if existing:
            return existing

        # Ensure metadata has been fetched
        self._ensure_fetched()
        return self._metadata.project_id

    def get_location(self) -> str | None:
        """
        Get GCP location (region).

        Auto-detects from instance zone metadata.

        Returns:
            Location (e.g., "us-central1") or None if not detected
        """
        self._ensure_fetched()
        return self._metadata.location

    def _ensure_fetched(self) -> None:
        """Fetch metadata if not already done (thread-safe)."""
        if self._fetched:
            return

        with self._lock:
            # Double-check after acquiring lock
            if self._fetched:
                return
            self._fetch_metadata()
            self._fetched = True

    def _fetch_metadata(self) -> None:
        """
        Fetch GCP project and location from available sources.

        Tries google.auth.default() first, then falls back to metadata service.
        """
        logger.info("GCP auto-detect: Starting GCP metadata detection for Vertex AI")

        # Try google.auth.default() first for project ID
        self._try_auth_default()

        # Try metadata service for project (if not found via ADC) and location
        self._try_metadata_service()

        # Log summary
        if self._metadata.project_id and self._metadata.location:
            logger.info(
                f"GCP auto-detect: Complete - project={self._metadata.project_id}, "
                f"location={self._metadata.location}"
            )
        elif self._metadata.project_id:
            logger.info(
                f"GCP auto-detect: Partial - project={self._metadata.project_id}, "
                "location=not detected"
            )
        else:
            logger.error(
                "GCP auto-detect: FAILED - Could not detect project ID. "
                "Set GOOGLE_CLOUD_PROJECT env var."
            )

    def _try_auth_default(self) -> None:
        """Try to get project ID from google.auth.default()."""
        logger.info("GCP auto-detect: Attempting google.auth.default() for project ID...")
        try:
            import google.auth

            credentials, detected_project = google.auth.default()
            logger.info(
                f"GCP auto-detect: google.auth.default() returned project={detected_project}, "
                f"credentials={type(credentials).__name__}"
            )
            if detected_project:
                self._metadata.project_id = detected_project
                # Also set env var for other libraries that may need it
                os.environ["GOOGLE_CLOUD_PROJECT"] = detected_project
                logger.info(
                    f"GCP auto-detect: SUCCESS - Set GOOGLE_CLOUD_PROJECT={detected_project} (from ADC)"
                )
            else:
                logger.warning(
                    "GCP auto-detect: google.auth.default() returned credentials but no project ID"
                )
        except ImportError:
            logger.warning(
                "GCP auto-detect: google-auth package not installed, skipping ADC detection"
            )
        except Exception as e:
            logger.warning(f"GCP auto-detect: google.auth.default() failed: {type(e).__name__}: {e}")

    def _try_metadata_service(self) -> None:
        """Try to get project and location from GCP metadata service."""
        logger.info("GCP auto-detect: Attempting GCP metadata service...")
        try:
            import requests

            headers = {"Metadata-Flavor": "Google"}
            timeout = 2
            base_url = "http://metadata.google.internal/computeMetadata/v1"

            # Fetch project ID if not already found
            if not self._metadata.project_id:
                self._fetch_project_from_metadata(base_url, headers, timeout)

            # Fetch zone/location
            self._fetch_location_from_metadata(base_url, headers, timeout)

        except ImportError:
            logger.warning(
                "GCP auto-detect: requests package not installed, skipping metadata detection"
            )
        except Exception as e:
            logger.warning(f"GCP auto-detect: Metadata service error: {type(e).__name__}: {e}")

    def _fetch_project_from_metadata(
        self, base_url: str, headers: dict[str, str], timeout: int
    ) -> None:
        """Fetch project ID from metadata service."""
        import requests

        url = f"{base_url}/project/project-id"
        logger.info(f"GCP auto-detect: Fetching project ID from {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            logger.info(f"GCP auto-detect: Project metadata response status={resp.status_code}")
            if resp.ok:
                project_id = resp.text.strip()
                self._metadata.project_id = project_id
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
                logger.info(
                    f"GCP auto-detect: SUCCESS - Set GOOGLE_CLOUD_PROJECT={project_id} (from metadata)"
                )
            else:
                logger.warning(f"GCP auto-detect: Project metadata returned {resp.status_code}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(
                f"GCP auto-detect: Cannot connect to metadata service (not on GCP?): {e}"
            )
        except requests.exceptions.Timeout:
            logger.warning("GCP auto-detect: Metadata service timed out for project")

    def _fetch_location_from_metadata(
        self, base_url: str, headers: dict[str, str], timeout: int
    ) -> None:
        """Fetch location from metadata service (derived from zone)."""
        import requests

        url = f"{base_url}/instance/zone"
        logger.info(f"GCP auto-detect: Fetching zone from {url}")
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            logger.info(f"GCP auto-detect: Zone metadata response status={resp.status_code}")
            if resp.ok:
                # Zone format: "projects/123456/zones/us-central1-a"
                zone_raw = resp.text.strip()
                zone = zone_raw.split("/")[-1]
                location = "-".join(zone.split("-")[:-1])
                self._metadata.location = location
                logger.info(f"GCP auto-detect: Detected location={location} (from zone={zone})")
            else:
                logger.warning(f"GCP auto-detect: Zone metadata returned {resp.status_code}")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"GCP auto-detect: Cannot connect to metadata service for zone: {e}")
        except requests.exceptions.Timeout:
            logger.warning("GCP auto-detect: Metadata service timed out for zone")


# Default singleton instance for backward compatibility
# This allows existing code to continue working while new code can inject a custom manager
_default_manager: GCPMetadataManager | None = None
_default_manager_lock = threading.Lock()


def get_default_gcp_metadata_manager() -> GCPMetadataManager:
    """
    Get the default GCPMetadataManager singleton.

    For most use cases, this provides the same behavior as the previous
    global functions, but with proper encapsulation.

    Returns:
        The default GCPMetadataManager instance
    """
    global _default_manager
    if _default_manager is None:
        with _default_manager_lock:
            if _default_manager is None:
                _default_manager = GCPMetadataManager()
    return _default_manager
