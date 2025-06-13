# agent.py
import logging
import re
from typing import Dict, List, Any

from services.duplo_client import DuploClient
from .resource_provider import ResourceProvider
from .checkers.s3_checker import S3ProductionReadinessChecker
from .checkers.rds_checker import RDSProductionReadinessChecker
from .checkers.ecache_checker import ElastiCacheProductionReadinessChecker
from .checkers.k8s_checker import K8sDeploymentProductionReadinessChecker
from .checkers.duplo_features_checker import DuploFeaturesProductionReadinessChecker
from .checkers.aws_security_checker import AWSSecurityProductionReadinessChecker
from .checkers.system_settings_checker import SystemSettingsProductionReadinessChecker
from .checkers.asg_checker import ASGProductionReadinessChecker

# Import all remediator classes
from .remediators.fault_notification_remediator import FaultNotificationRemediator
from .remediators.duplo_logging_remediator import DuploLoggingRemediator
from .remediators.duplo_monitoring_remediator import DuploMonitoringRemediator
from .remediators.duplo_alerting_remediator import DuploAlertingRemediator
from .remediators.duplo_service_remediator import DuploServiceRemediator
from .remediators.aws_security_remediator import AWSSecurityRemediator
from .remediators.system_settings_remediator import SystemSettingsRemediator

logger = logging.getLogger(__name__)

class ProductionReadinessAgent:
    """
    Production Readiness Agent that orchestrates checkers and remediators
    to evaluate and improve the production readiness of DuploCloud resources.
    """
    
    def __init__(self, duplo_client: DuploClient):
        """
        Initialize the Production Readiness Agent.
        
        Args:
            duplo_client: DuploClient instance for API interactions
        """
        self.duplo_client = duplo_client
        self.resource_provider = ResourceProvider(duplo_client)
        
        # Initialize all checkers
        self.checkers = {
            "s3": S3ProductionReadinessChecker(duplo_client, self.resource_provider),
            "rds": RDSProductionReadinessChecker(duplo_client, self.resource_provider),
            "elasticache": ElastiCacheProductionReadinessChecker(duplo_client, self.resource_provider),
            "k8s": K8sDeploymentProductionReadinessChecker(duplo_client, self.resource_provider),
            "duplo_features": DuploFeaturesProductionReadinessChecker(duplo_client, self.resource_provider),
            "aws_security": AWSSecurityProductionReadinessChecker(duplo_client, self.resource_provider),
            "system_settings": SystemSettingsProductionReadinessChecker(duplo_client, self.resource_provider),
            "asg": ASGProductionReadinessChecker(duplo_client, self.resource_provider)
        }
        
        # Initialize all remediators
        self.remediators = {
            "enable_duplo_logging": DuploLoggingRemediator(duplo_client, self.resource_provider),
            "enable_duplo_monitoring": DuploMonitoringRemediator(duplo_client, self.resource_provider),
            "enable_duplo_alerting": DuploAlertingRemediator(duplo_client, self.resource_provider),
            "update_duplo_service": DuploServiceRemediator(duplo_client, self.resource_provider),
            "enable_aws_security_feature": AWSSecurityRemediator(duplo_client, self.resource_provider),
            "update_duplo_system_setting": SystemSettingsRemediator(duplo_client, self.resource_provider),
            "enable_fault_notification": FaultNotificationRemediator(duplo_client, self.resource_provider)
        }
    
    def check_production_readiness(self, tenant: str) -> Dict[str, Any]:
        """
        Check the production readiness of resources in a tenant.
        
        Args:
            tenant: Tenant name or ID
            
        Returns:
            Dictionary with production readiness check results
        """
        logger.info(f"Checking production readiness for tenant {tenant}")
        
        # Collect results from all checkers
        results = {}
        
        # Run S3 checks
        s3_results = self.checkers["s3"].check(tenant)
        if s3_results:
            results["s3_buckets"] = s3_results
        
        # Run RDS checks
        rds_results = self.checkers["rds"].check(tenant)
        if rds_results:
            results["rds_instances"] = rds_results
        
        # Run ElastiCache checks
        elasticache_results = self.checkers["elasticache"].check(tenant)
        if elasticache_results:
            results["elasticache_clusters"] = elasticache_results
        
        # Run K8s Deployment checks
        k8s_results = self.checkers["k8s"].check(tenant)
        if k8s_results:
            results["k8s_deployments"] = k8s_results
        
        # Run DuploCloud Features checks
        duplo_features_results = self.checkers["duplo_features"].check(tenant)
        if duplo_features_results:
            results["duplo_features"] = duplo_features_results
        
        # Run AWS security checks
        aws_security_results = self.checkers["aws_security"].check(tenant)
        if aws_security_results:
            results["aws_security_features"] = aws_security_results
            
        # Run system settings checks
        system_settings_results = self.checkers["system_settings"].check(tenant)
        if system_settings_results:
            results["system_settings"] = system_settings_results
            
        # Run ASG checks
        asg_results = self.checkers["asg"].check(tenant)
        if asg_results:
            results["auto_scaling_groups"] = asg_results
        
        # Add tenant name to results
        results["tenant"] = tenant
        
        return results
    
    def execute_remediation(self, tenant: str, action: str, approved: bool = False) -> Dict[str, Any]:
        """
        Execute a remediation action.
        
        Args:
            tenant: Tenant name or ID
            action: Remediation action string in the format "action_type:param1:param2:..."
            approved: Whether the action has been approved by the user
            
        Returns:
            Dictionary with remediation execution results
        """
        if not approved:
            return {
                "success": False,
                "message": "Remediation action not approved",
                "details": {"tenant": tenant, "action": action}
            }
        
        # Parse the action string
        action_parts = action.split(":")
        action_type = action_parts[0]
        
        if action_type not in self.remediators:
            return {
                "success": False,
                "message": f"Unsupported remediation action type: {action_type}",
                "details": {"tenant": tenant, "action_type": action_type}
            }
        
        # Parse action parameters
        action_params = self._parse_action_params(action_parts[1:])
        
        # Execute the remediation action
        logger.info(f"Executing remediation action {action_type} for tenant {tenant}")
        return self.remediators[action_type].execute(tenant, action_params)
    
    def _parse_action_params(self, param_parts: List[str]) -> Dict[str, Any]:
        """
        Parse action parameters from the action string.
        
        Args:
            param_parts: List of parameter parts from the action string
            
        Returns:
            Dictionary of parsed parameters
        """
        params = {}
        
        for part in param_parts:
            # Check if the part contains a key-value pair
            if "=" in part:
                key, value = part.split("=", 1)
                # Try to convert value to appropriate type
                if value.lower() == "true":
                    params[key] = True
                elif value.lower() == "false":
                    params[key] = False
                elif value.isdigit():
                    params[key] = int(value)
                elif value.replace(".", "", 1).isdigit() and value.count(".") == 1:
                    params[key] = float(value)
                else:
                    params[key] = value
            else:
                # For simple parameters without values, use as feature name or setting
                if len(param_parts) == 1:
                    params["feature_name"] = part
                elif len(param_parts) == 2:
                    if param_parts[1].lower() in ["true", "false"]:
                        params["feature_name"] = part
                        params["enabled"] = param_parts[1].lower() == "true"
                    else:
                        params["setting_name"] = part
                        params["value"] = param_parts[1]
        
        return params
    
    def extract_remediation_actions(self, llm_response: str) -> List[str]:
        """
        Extract remediation actions from an LLM response.
        
        Args:
            llm_response: Response from the LLM containing remediation actions
            
        Returns:
            List of remediation action strings
        """
        # Extract actions from code blocks
        actions = []
        
        # Look for code blocks with remediation actions
        code_block_pattern = r"```(?:remediation)?\s*(.*?)```"
        code_blocks = re.findall(code_block_pattern, llm_response, re.DOTALL)
        
        for block in code_blocks:
            # Extract individual actions from the code block
            for line in block.strip().split("\n"):
                line = line.strip()
                if line and ":" in line and not line.startswith("#"):
                    actions.append(line)
        
        return actions
    