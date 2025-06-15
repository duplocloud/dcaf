"""
AWS security features remediator for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any
from .base_remediator import BaseRemediator

logger = logging.getLogger(__name__)

class AWSSecurityRemediator(BaseRemediator):
    """
    Remediator for AWS security features production readiness issues.
    """
    
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate AWS security features production readiness issues.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters in the format "feature_name:true/false"
            
        Returns:
            String with the result of the remediation action
        """
        # Parse feature name and value
        parts = params.split(":", 1)
        if len(parts) < 2:
            return f"Invalid parameters: {params}. Format should be 'feature_name:true/false'"
            
        feature_name = parts[0].strip()
        feature_value_str = parts[1].strip().lower()
        
        # Convert value to boolean
        if feature_value_str == "true":
            feature_value = True
        elif feature_value_str == "false":
            feature_value = False
        else:
            return f"Invalid value: {feature_value_str}. Must be 'true' or 'false'"
            
        # Validate feature name
        valid_features = [
            "vpc_flow_logs", "security_hub", "guardduty", "cloudtrail", 
            "s3_public_access_block", "inspector", "password_policy",
            "delete_default_vpcs", "revoke_default_sg_rules", "delete_default_nacl_rules"
        ]
        
        if feature_name not in valid_features:
            return f"Invalid feature: {feature_name}. Valid features are: {', '.join(valid_features)}"
            
        try:
            # Map feature name to API field name
            feature_map = {
                "vpc_flow_logs": "VpcFlowLogs",
                "security_hub": "SecurityHub",
                "guardduty": "GuardDuty",
                "cloudtrail": "CloudTrail",
                "s3_public_access_block": "S3PublicAccessBlock",
                "inspector": "Inspector",
                "password_policy": "PasswordPolicy",
                "delete_default_vpcs": "DeleteDefaultVpcs",
                "revoke_default_sg_rules": "RevokeDefaultSgRules",
                "delete_default_nacl_rules": "DeleteDefaultNaclRules"
            }
            
            api_field = feature_map.get(feature_name)
            if not api_field:
                return f"Feature mapping not found for: {feature_name}"
                
            # Prepare payload
            payload = {
                api_field: feature_value
            }
            
            # Call API to update security feature
            self.duplo_client.post("v3/admin/systemSettings/awsAccountSecurityFeatures", payload)
            
            return f"Successfully {'enabled' if feature_value else 'disabled'} AWS security feature: {feature_name}"
            
        except Exception as e:
            logger.error(f"Error updating AWS security feature: {str(e)}")
            return f"Failed to update AWS security feature: {str(e)}"
