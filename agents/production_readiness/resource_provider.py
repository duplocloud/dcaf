# resource_provider.py
from typing import Dict, List, Any, Optional
from services.duplo_client import DuploClient
import logging

logger = logging.getLogger(__name__)

class ResourceProvider:
    """
    Provides resources from DuploCloud for checkers and remediators.
    This class centralizes the resource fetching logic.
    """
    
    def __init__(self, duplo_client: DuploClient):
        """
        Initialize the resource provider with a DuploClient instance.
        
        Args:
            duplo_client: DuploClient instance for API calls
        """
        self.duplo_client = duplo_client
        
    def get_resources(self, tenant_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all resources for a tenant from DuploCloud.
        
        Args:
            tenant_id: Tenant ID to fetch resources for
            
        Returns:
            Dictionary with resource types and their instances
        """
        logger.info(f"Fetching resources for tenant {tenant_id}")
        
        # Fetch all resources from DuploCloud
        raw_resources = {
            "rds": self.duplo_client.official_client.load("rds").list(),
            "ecache": self.duplo_client.get(f"subscriptions/{tenant_id}/GetEcacheInstances"),
            "k8s_deployments": self.duplo_client.official_client.load("service").list(),
            "s3": self.duplo_client.official_client.load("s3").list(),
            "asgs": self.duplo_client.official_client.load("asg").list(),
            "duplo_logging": self.duplo_client.get(f"admin/GetLoggingEnabledTenants"),
            "duplo_monitoring": self.duplo_client.get(f"admin/GetMonitoringConfigForTenant/default"),
            "duplo_alerting": self.duplo_client.get(f"v3/admin/tenant/{tenant_id}/metadata/enable_alerting"),
            "duplo_notification": self.duplo_client.get(f"subscriptions/{tenant_id}/GetTenantMonConfig"),
            "aws_security": self.duplo_client.get(f"v3/admin/systemSettings/awsAccountSecurity"),
            "system_settings": self.duplo_client.get(f"v3/admin/systemSettings/config"),
        }
        
        # Apply filters to exclude resources based on prefixes
        filtered_resources = self._filter_resources(raw_resources)
        
        return filtered_resources
    
    def get_resource_by_type(self, tenant_id: str, resource_type: str) -> List[Dict[str, Any]]:
        """
        Get resources of a specific type for a tenant.
        
        Args:
            tenant_id: Tenant ID to fetch resources for
            resource_type: Type of resource to fetch (e.g., 'rds', 's3', etc.)
            
        Returns:
            List of resources of the specified type
        """
        logger.info(f"Fetching {resource_type} resources for tenant {tenant_id}")
        
        if resource_type == "rds":
            return self.duplo_client.official_client.load("rds").list()
        elif resource_type == "ecache":
            return self.duplo_client.get(f"subscriptions/{tenant_id}/GetEcacheInstances")
        elif resource_type == "k8s_deployments":
            return self.duplo_client.official_client.load("service").list()
        elif resource_type == "s3":
            return self.duplo_client.official_client.load("s3").list()
        elif resource_type == "asgs":
            return self.duplo_client.official_client.load("asg").list()
        elif resource_type == "duplo_logging":
            return self.duplo_client.get(f"admin/GetLoggingEnabledTenants")
        elif resource_type == "duplo_monitoring":
            return self.duplo_client.get(f"admin/GetMonitoringConfigForTenant/default")
        elif resource_type == "duplo_alerting":
            return self.duplo_client.get(f"v3/admin/tenant/{tenant_id}/metadata/enable_alerting")
        elif resource_type == "duplo_notification":
            return self.duplo_client.get(f"subscriptions/{tenant_id}/GetTenantMonConfig")
        elif resource_type == "aws_security":
            return self.duplo_client.get(f"v3/admin/systemSettings/awsAccountSecurity")
        elif resource_type == "system_settings":
            return self.duplo_client.get(f"v3/admin/systemSettings/config")
        else:
            logger.warning(f"Unknown resource type: {resource_type}")
            return []
    
    def _filter_resources(self, resources: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Filter resources based on predefined rules.
        
        Args:
            resources: Dictionary of resources to filter
            
        Returns:
            Filtered resources dictionary
        """
        # Define prefixes to exclude for each resource type
        exclude_prefixes = {
            "k8s_deployments": ["filebeat-k8s-", "cadvisor-k8s-", "node-exporter-k8s-"],
            # "s3": ["duplo-", "log-", "backup-"],
            # "rds": [],
            # "ecache": [],
            # "asgs": []
        }
        
        # Apply filters to exclude resources based on prefixes
        filtered_resources = {}
        for resource_type, resources_list in resources.items():
            prefixes = exclude_prefixes.get(resource_type, [])
            if prefixes and resources_list:
                filtered_resources[resource_type] = self._filter_by_prefix(resources_list, prefixes)
            else:
                filtered_resources[resource_type] = resources_list
        
        return filtered_resources
    
    def _filter_by_prefix(self, resources: List[Dict[str, Any]], 
                         exclude_prefixes: List[str], 
                         name_field: str = "Name") -> List[Dict[str, Any]]:
        """
        Filter resources based on name prefixes to exclude.
        
        Args:
            resources: List of resources to filter
            exclude_prefixes: List of prefixes to exclude
            name_field: The field name that contains the resource name
            
        Returns:
            Filtered list of resources
        """
        if not resources or not exclude_prefixes:
            return resources
            
        original_count = len(resources)
        filtered_resources = [
            resource for resource in resources 
            if not any(str(resource.get(name_field, "")).startswith(prefix) for prefix in exclude_prefixes)
        ]
        
        filtered_count = original_count - len(filtered_resources)
        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} resources with excluded prefixes: {exclude_prefixes}")
            
        return filtered_resources
