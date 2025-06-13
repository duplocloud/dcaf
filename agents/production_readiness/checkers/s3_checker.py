# s3_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class S3ProductionReadinessChecker(BaseChecker):
    """Checker for S3 bucket production readiness"""
    
    def check(self, tenant: str, buckets: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Fetch S3 buckets if not provided
        if buckets is None:
            buckets = self.get_resources(tenant, "s3")
        """
        Check S3 buckets for production readiness
        
        Args:
            tenant: Tenant name or ID
            buckets: List of S3 buckets to check
            
        Returns:
            Dictionary with check results
        """
        # Define checks for S3 buckets
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

        return self._generic_resource_check(tenant, buckets, s3_checks)