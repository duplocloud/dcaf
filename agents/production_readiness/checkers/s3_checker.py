"""
S3 bucket checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class S3ProductionReadinessChecker(BaseChecker):
    """
    Checker for S3 bucket production readiness.
    """
    
    def check(self, tenant: str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check S3 Buckets for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: List of S3 bucket resources to check
            
        Returns:
            Dictionary with check results
        """
        s3_checks = [
            {
                'name': 'encryption',
                'attribute_path': ['DefaultEncryption'],
                'condition': lambda val: (val is not None, 
                    "Server-side encryption is enabled" if val is not None else 
                    "Server-side encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable server-side encryption"
            },
            {
                'name': 'public_access_block',
                'attribute_path': ['AllowPublicAccess'],
                'condition': lambda val: (val is False,
                    "Block public access is enabled" if val is False else
                    "Block public access is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable block public access"
            },
            {
                'name': 'versioning',
                'attribute_path': ['EnableVersioning'],
                'condition': lambda val: (val is True, 
                    "Versioning is enabled" if val is True else 
                    "Versioning is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable versioning for data protection"
            },
            {
                'name': 'logging',
                'attribute_path': ['EnableAccessLogs'],
                'condition': lambda val: (val is True, 
                    "Logging is enabled" if val is True else 
                    "Logging is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable logging to track bucket access"
            },
        ]

        return self._generic_resource_check(tenant, resources, s3_checks)
