# aws_security_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class AWSSecurityRemediator(BaseRemediator):
    """
    Remediator for AWS security features.
    Enables or configures AWS security features like CloudTrail, GuardDuty, etc.
    """
    
    # List of supported AWS security features
    SUPPORTED_FEATURES = [
        'vpc_flow_logs', 
        'security_hub', 
        'guardduty', 
        'cloudtrail', 
        's3_public_access_block', 
        'inspector', 
        'password_policy', 
        'delete_default_vpcs', 
        'revoke_default_sg_rules', 
        'delete_default_nacl_rules'
    ]
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable or configure an AWS security feature.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - feature_name: Name of the security feature to enable/configure
                - enabled: Boolean value to enable/disable the feature
            
        Returns:
            Dictionary with execution results
        """
        # Extract parameters
        feature_name = action_params.get("feature_name")
        enabled = action_params.get("enabled", True)
        
        if not feature_name:
            return {
                "success": False,
                "message": "Feature name is required",
                "details": {"tenant": tenant}
            }
        
        if feature_name not in self.SUPPORTED_FEATURES:
            return {
                "success": False,
                "message": f"Unsupported feature: {feature_name}. Supported features: {', '.join(self.SUPPORTED_FEATURES)}",
                "details": {"tenant": tenant, "feature_name": feature_name}
            }
        
        logger.info(f"{'Enabling' if enabled else 'Disabling'} AWS security feature {feature_name}")
        
        # Get current AWS security features configuration
        aws_security = self.get_resources(tenant, "aws_security")
        
        # Map feature name to API field name
        feature_mapping = {
            'vpc_flow_logs': 'VpcFlowLogsEnabled',
            'security_hub': 'SecurityHubEnabled',
            'guardduty': 'GuardDutyEnabled',
            'cloudtrail': 'CloudTrailEnabled',
            's3_public_access_block': 'S3PublicAccessBlockEnabled',
            'inspector': 'InspectorEnabled',
            'password_policy': 'PasswordPolicyEnabled',
            'delete_default_vpcs': 'DeleteDefaultVpcs',
            'revoke_default_sg_rules': 'RevokeDefaultSgRules',
            'delete_default_nacl_rules': 'DeleteDefaultNaclRules'
        }
        
        api_field = feature_mapping.get(feature_name)
        if not api_field:
            return {
                "success": False,
                "message": f"API field mapping not found for feature: {feature_name}",
                "details": {"tenant": tenant, "feature_name": feature_name}
            }
        
        # Check if the feature is already in the desired state
        current_state = aws_security.get(api_field, False)
        if current_state == enabled:
            return {
                "success": True,
                "message": f"AWS security feature {feature_name} is already {'enabled' if enabled else 'disabled'}",
                "details": {"tenant": tenant, "feature_name": feature_name, "enabled": enabled}
            }
        
        # Prepare update payload
        update_payload = {api_field: enabled}
        
        # Update the AWS security feature
        try:
            self.duplo_client.post("v3/admin/systemSettings/awsAccountSecurityFeatures", update_payload)
            logger.info(f"Successfully {'enabled' if enabled else 'disabled'} AWS security feature {feature_name}")
            
            return {
                "success": True,
                "message": f"Successfully {'enabled' if enabled else 'disabled'} AWS security feature {feature_name}",
                "details": {"tenant": tenant, "feature_name": feature_name, "enabled": enabled}
            }
        except Exception as e:
            logger.error(f"Failed to update AWS security feature {feature_name}: {e}")
            return {
                "success": False,
                "message": f"Failed to update AWS security feature: {str(e)}",
                "details": {"tenant": tenant, "feature_name": feature_name, "error": str(e)}
            }