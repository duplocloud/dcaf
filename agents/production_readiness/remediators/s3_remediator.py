"""
S3 bucket remediator for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any, List
from .base_remediator import BaseRemediator

logger = logging.getLogger(__name__)

class S3Remediator(BaseRemediator):
    """
    Remediator for S3 bucket production readiness issues.
    """
    
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate S3 bucket production readiness issues.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters in the format "bucket_name:setting=value"
            
        Returns:
            String with the result of the remediation action
        """
        # Parse bucket name and settings
        parts = params.split(":", 1)
        if len(parts) < 2:
            return f"Invalid parameters: {params}. Format should be 'bucket_name:setting=value'"
            
        bucket_name = parts[0].strip()
        settings_str = parts[1].strip()
        settings = self._parse_params(settings_str)
        
        # Get tenant ID
        tenant_id = self._get_tenant_id(tenant)
        if not tenant_id:
            return f"Tenant not found: {tenant}"
            
        # Create JSON patch operations
        patch_operations = self._create_patch_operations(settings)
        if not patch_operations:
            return "No valid settings provided for update"
            
        try:
            # Apply patch to S3 bucket
            endpoint = f"v3/subscriptions/{tenant_id}/aws/s3/{bucket_name}"
            self.duplo_client.official_client.jsonpatch(endpoint, patch_operations)
            
            # Format the applied settings for the response
            settings_applied = []
            for setting, value in settings.items():
                settings_applied.append(f"{setting}={value}")
                
            return f"Successfully updated S3 bucket '{bucket_name}' with settings: {', '.join(settings_applied)}"
            
        except Exception as e:
            logger.error(f"Error updating S3 bucket: {str(e)}")
            return f"Failed to update S3 bucket: {str(e)}"
    
    def _create_patch_operations(self, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create JSON patch operations for S3 bucket settings.
        
        Args:
            settings: Dictionary of settings to update
            
        Returns:
            List of JSON patch operations
        """
        patch_operations = []
        
        # Map settings to JSON patch paths
        settings_map = {
            "versioning": "/EnableVersioning",
            "logging": "/EnableAccessLogs",
            "encryption": "/DefaultEncryption",
            "public_access": "/AllowPublicAccess"
        }
        
        # Handle encryption specially
        if "encryption" in settings and settings["encryption"] is True:
            patch_operations.append({
                "op": "replace",
                "path": settings_map["encryption"],
                "value": "AES256"
            })
            
        # Handle other boolean settings
        for setting, path in settings_map.items():
            if setting in settings and setting != "encryption":
                # For public_access, we need to invert the value since AllowPublicAccess is the opposite
                if setting == "public_access":
                    patch_operations.append({
                        "op": "replace",
                        "path": path,
                        "value": not settings[setting]
                    })
                else:
                    patch_operations.append({
                        "op": "replace",
                        "path": path,
                        "value": settings[setting]
                    })
                    
        return patch_operations
