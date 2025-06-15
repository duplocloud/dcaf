"""
AWS security features checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class AWSSecurityProductionReadinessChecker(BaseChecker):
    """
    Checker for AWS security features production readiness.
    """
    
    def check(self, tenant: str, resources: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check AWS security features for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: Dictionary containing AWS security features configuration
            
        Returns:
            Dictionary with check results
        """
        # Convert the dictionary to a list with a single item for the generic checker
        resource_list = [resources] if resources else []
        
        aws_security_checks = [
            {
                'name': 'vpc_flow_logs',
                'attribute_path': ['VpcFlowLogs'],
                'condition': lambda val: (val is True, 
                    "VPC Flow Logs are enabled" if val is True else 
                    "VPC Flow Logs are not enabled"),
                'severity': 'critical',
                'recommendation': "Enable VPC Flow Logs for network traffic monitoring"
            },
            {
                'name': 'security_hub',
                'attribute_path': ['SecurityHub'],
                'condition': lambda val: (val is True, 
                    "Security Hub is enabled" if val is True else 
                    "Security Hub is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Security Hub for security monitoring"
            },
            {
                'name': 'guardduty',
                'attribute_path': ['GuardDuty'],
                'condition': lambda val: (val is True, 
                    "GuardDuty is enabled" if val is True else 
                    "GuardDuty is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable GuardDuty for threat detection"
            },
            {
                'name': 'cloudtrail',
                'attribute_path': ['CloudTrail'],
                'condition': lambda val: (val is True, 
                    "CloudTrail is enabled" if val is True else 
                    "CloudTrail is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable CloudTrail for API activity logging"
            },
            {
                'name': 's3_public_access_block',
                'attribute_path': ['S3PublicAccessBlock'],
                'condition': lambda val: (val is True, 
                    "S3 Public Access Block is enabled" if val is True else 
                    "S3 Public Access Block is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable S3 Public Access Block to prevent public access"
            },
            {
                'name': 'inspector',
                'attribute_path': ['Inspector'],
                'condition': lambda val: (val is True, 
                    "Inspector is enabled" if val is True else 
                    "Inspector is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable Inspector for vulnerability assessment"
            },
            {
                'name': 'password_policy',
                'attribute_path': ['PasswordPolicy'],
                'condition': lambda val: (val is True, 
                    "Password Policy is configured" if val is True else 
                    "Password Policy is not configured"),
                'severity': 'warning',
                'recommendation': "Configure Password Policy for IAM users"
            }
        ]

        return self._generic_resource_check(tenant, resource_list, aws_security_checks)
