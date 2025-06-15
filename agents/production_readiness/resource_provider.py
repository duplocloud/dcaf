"""
Resource provider for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ResourceProvider:
    """
    Provider for fetching DuploCloud resources for production readiness checks.
    """
    
    def __init__(self, duplo_client):
        """
        Initialize the resource provider with a DuploClient instance.
        
        Args:
            duplo_client: An instance of DuploClient for API calls
        """
        self.duplo_client = duplo_client
    
    def get_tenant_resources(self, tenant: str) -> Dict[str, Any]:
        """
        Get all resources for a tenant.
        
        Args:
            tenant: Tenant name or ID
            
        Returns:
            Dictionary with all tenant resources
        """
        tenant_id = self._get_tenant_id(tenant)
        if not tenant_id:
            return {}
            
        return {
            "services": self.get_services(tenant_id),
            "s3_buckets": self.get_s3_buckets(tenant_id),
            "rds_instances": self.get_rds_instances(tenant_id),
            "elasticache_clusters": self.get_elasticache_clusters(tenant_id),
            "dynamodb_tables": self.get_dynamodb_tables(tenant_id),
            "efs_filesystems": self.get_efs_filesystems(tenant_id),
            "aws_security_features": self.get_aws_security_features(),
            "system_settings": self.get_system_settings(),
            "duplo_features": self.get_duplo_features(tenant_id)
        }
    
    def get_services(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get Kubernetes/DuploCloud services for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of service resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/k8s/native/services") or []
        except Exception as e:
            logger.error(f"Error getting services: {str(e)}")
            return []
    
    def get_s3_buckets(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get S3 buckets for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of S3 bucket resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/aws/s3") or []
        except Exception as e:
            logger.error(f"Error getting S3 buckets: {str(e)}")
            return []
    
    def get_rds_instances(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get RDS instances for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of RDS instance resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/aws/rds") or []
        except Exception as e:
            logger.error(f"Error getting RDS instances: {str(e)}")
            return []
    
    def get_elasticache_clusters(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get ElastiCache clusters for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of ElastiCache cluster resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/aws/elasticache") or []
        except Exception as e:
            logger.error(f"Error getting ElastiCache clusters: {str(e)}")
            return []
    
    def get_dynamodb_tables(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get DynamoDB tables for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of DynamoDB table resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/aws/dynamodb") or []
        except Exception as e:
            logger.error(f"Error getting DynamoDB tables: {str(e)}")
            return []
    
    def get_efs_filesystems(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Get EFS filesystems for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            List of EFS filesystem resources
        """
        try:
            return self.duplo_client.get(f"v3/subscriptions/{tenant_id}/aws/efs") or []
        except Exception as e:
            logger.error(f"Error getting EFS filesystems: {str(e)}")
            return []
    
    def get_aws_security_features(self) -> Dict[str, Any]:
        """
        Get AWS security features configuration.
        
        Returns:
            Dictionary with AWS security features configuration
        """
        try:
            return self.duplo_client.get("v3/admin/systemSettings/awsAccountSecurityFeatures") or {}
        except Exception as e:
            logger.error(f"Error getting AWS security features: {str(e)}")
            return {}
    
    def get_system_settings(self) -> Dict[str, Any]:
        """
        Get DuploCloud system settings.
        
        Returns:
            Dictionary with system settings configuration
        """
        try:
            return self.duplo_client.get("v3/admin/systemSettings/config") or {}
        except Exception as e:
            logger.error(f"Error getting system settings: {str(e)}")
            return {}
    
    def get_duplo_features(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get DuploCloud features configuration for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with DuploCloud features configuration
        """
        result = {}
        
        try:
            # Get monitoring status
            monitoring = self.duplo_client.get(f"v3/subscriptions/{tenant_id}/monitoring")
            result["Monitoring"] = monitoring.get("Enable", False) if monitoring else False
            
            # Get logging status
            logging_status = self.duplo_client.get(f"v3/subscriptions/{tenant_id}/logging")
            result["Logging"] = logging_status.get("Enable", False) if logging_status else False
            
            # Get alerting status
            alerting = self.duplo_client.get(f"v3/subscriptions/{tenant_id}/alerting")
            result["Alerting"] = alerting.get("Enable", False) if alerting else False
            
            # Get notification channels
            notification_channels = self.duplo_client.get(f"v3/subscriptions/{tenant_id}/faultnotification")
            result["NotificationChannels"] = notification_channels or []
            
        except Exception as e:
            logger.error(f"Error getting DuploCloud features: {str(e)}")
            
        return result
    
    def _get_tenant_id(self, tenant_name: str) -> Optional[str]:
        """
        Get tenant ID from tenant name.
        
        Args:
            tenant_name: Name of the tenant
            
        Returns:
            Tenant ID or None if not found
        """
        try:
            tenants = self.duplo_client.list_tenants()
            
            for t in tenants:
                if t.get("Name") == tenant_name or t.get("TenantId") == tenant_name:
                    return t.get("TenantId")
                    
            logger.warning(f"Tenant not found: {tenant_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting tenant ID: {str(e)}")
            return None
