# aws_security_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class AWSSecurityProductionReadinessChecker(BaseChecker):
    """Checker for AWS security features production readiness"""
    
    def check(self, tenant: str) -> Dict[str, Any]:
        """
        Check AWS security features for production readiness
        
        Args:
            tenant: Tenant name or ID
            
        Returns:
            Dictionary with check results
        """
        # Fetch AWS security features
        aws_security = self.get_resources(tenant, "aws_security")
        system_settings = self.get_resources(tenant, "system_settings")
        
        # Define checks for AWS security features
        security_checks = [
            {
                'name': 'cloudtrail_enabled',
                'attribute_path': ['CloudTrailEnabled'],
                'condition': lambda val: (val is True, 
                                         "CloudTrail is enabled" if val is True else 
                                         "CloudTrail is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable CloudTrail for AWS API activity logging"
            },
            {
                'name': 'guardduty_enabled',
                'attribute_path': ['GuardDutyEnabled'],
                'condition': lambda val: (val is True, 
                                         "GuardDuty is enabled" if val is True else 
                                         "GuardDuty is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable GuardDuty for threat detection"
            },
            {
                'name': 'security_hub_enabled',
                'attribute_path': ['SecurityHubEnabled'],
                'condition': lambda val: (val is True, 
                                         "Security Hub is enabled" if val is True else 
                                         "Security Hub is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable Security Hub for security findings aggregation"
            },
            {
                'name': 'config_enabled',
                'attribute_path': ['ConfigEnabled'],
                'condition': lambda val: (val is True, 
                                         "AWS Config is enabled" if val is True else 
                                         "AWS Config is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable AWS Config for configuration monitoring"
            },
            {
                'name': 'inspector_enabled',
                'attribute_path': ['InspectorEnabled'],
                'condition': lambda val: (val is True, 
                                         "Inspector is enabled" if val is True else 
                                         "Inspector is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable Inspector for vulnerability assessment"
            },
            {
                'name': 'default_encryption',
                'attribute_path': ['DefaultEncryption'],
                'condition': lambda val: (val is True, 
                                         "Default encryption is enabled" if val is True else 
                                         "Default encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable default encryption for all resources"
            },
            {
                'name': 'imdsv2_required',
                'attribute_path': ['ImdsV2Required'],
                'condition': lambda val: (val is True, 
                                         "IMDSv2 is required" if val is True else 
                                         "IMDSv2 is not required"),
                'severity': 'critical',
                'recommendation': "Require IMDSv2 for EC2 instance metadata service"
            }
        ]
        
        # Run the checks
        results = {}
        passed_checks = 0
        total_checks = len(security_checks)
        
        for check in security_checks:
            check_name = check['name']
            attribute_path = check['attribute_path']
            condition = check['condition']
            severity = check['severity']
            recommendation = check['recommendation']
            
            # Extract attribute value from AWS security config
            value = aws_security
            for path in attribute_path:
                if isinstance(value, dict) and path in value:
                    value = value[path]
                else:
                    value = None
                    break
            
            # Evaluate condition
            passed, message = condition(value)
            
            # Store result
            results[check_name] = {
                'name': check_name,
                'passed': passed,
                'severity': severity,
                'message': message,
                'recommendation': recommendation if not passed else ""
            }
            
            if passed:
                passed_checks += 1
        
        # Calculate score
        score = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
        
        return {
            "resource_type": "aws_security",
            "tenant": tenant,
            "results": results,
            "score": score,
            "passed": score >= 75,  # Pass if at least 75% of checks pass
            "message": f"AWS security check: {passed_checks}/{total_checks} checks passed"
        }