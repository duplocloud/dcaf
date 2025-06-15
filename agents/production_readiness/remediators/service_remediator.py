"""
DuploCloud service remediator for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any
from .base_remediator import BaseRemediator

logger = logging.getLogger(__name__)

class ServiceRemediator(BaseRemediator):
    """
    Remediator for DuploCloud service production readiness issues.
    """
    
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate DuploCloud service production readiness issues.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters in the format "service_name:setting=value"
            
        Returns:
            String with the result of the remediation action
        """
        # Parse service name and settings
        parts = params.split(":", 1)
        if len(parts) < 2:
            return f"Invalid parameters: {params}. Format should be 'service_name:setting=value'"
            
        service_name = parts[0].strip()
        settings_str = parts[1].strip()
        settings = self._parse_params(settings_str)
        
        # Get tenant ID
        tenant_id = self._get_tenant_id(tenant)
        if not tenant_id:
            return f"Tenant not found: {tenant}"
            
        # Validate settings
        valid_settings = ["replicas", "cpu", "memory", "health_check"]
        
        for setting in settings:
            if setting not in valid_settings:
                return f"Invalid setting: {setting}. Valid settings are: {', '.join(valid_settings)}"
                
        try:
            # Get current service configuration
            service = self.duplo_client.get(f"v3/subscriptions/{tenant_id}/k8s/native/service/{service_name}")
            if not service:
                return f"Service not found: {service_name}"
                
            # Update service configuration
            updated = False
            
            # Update replica count
            if "replicas" in settings:
                replicas = settings["replicas"]
                self.duplo_client.post(
                    f"v3/subscriptions/{tenant_id}/k8s/native/service/{service_name}/replicas",
                    {"ReplicaCount": replicas}
                )
                updated = True
                
            # Update resource limits
            if "cpu" in settings or "memory" in settings:
                # Get current container configuration
                containers = service.get("Containers", [])
                if not containers:
                    return "Service has no containers to update"
                    
                # Update first container's resource limits
                container = containers[0]
                resource_limits = container.get("ResourceLimits", {})
                
                if "cpu" in settings:
                    resource_limits["Cpu"] = settings["cpu"]
                    
                if "memory" in settings:
                    resource_limits["Memory"] = settings["memory"]
                    
                # Update container configuration
                container["ResourceLimits"] = resource_limits
                containers[0] = container
                
                # Update service with new container configuration
                service["Containers"] = containers
                self.duplo_client.post(f"v3/subscriptions/{tenant_id}/k8s/native/service/{service_name}", service)
                updated = True
                
            # Update health check
            if "health_check" in settings and settings["health_check"] is True:
                # Get current container configuration
                containers = service.get("Containers", [])
                if not containers:
                    return "Service has no containers to update"
                    
                # Update first container's health check
                container = containers[0]
                
                # Set default liveness probe if not present
                if not container.get("LivenessProbe"):
                    container["LivenessProbe"] = {
                        "Path": "/health",
                        "Port": container.get("Port", 80),
                        "InitialDelaySeconds": 30,
                        "TimeoutSeconds": 5,
                        "PeriodSeconds": 10,
                        "SuccessThreshold": 1,
                        "FailureThreshold": 3
                    }
                    
                # Set default readiness probe if not present
                if not container.get("ReadinessProbe"):
                    container["ReadinessProbe"] = {
                        "Path": "/health",
                        "Port": container.get("Port", 80),
                        "InitialDelaySeconds": 30,
                        "TimeoutSeconds": 5,
                        "PeriodSeconds": 10,
                        "SuccessThreshold": 1,
                        "FailureThreshold": 3
                    }
                    
                # Update container configuration
                containers[0] = container
                
                # Update service with new container configuration
                service["Containers"] = containers
                self.duplo_client.post(f"v3/subscriptions/{tenant_id}/k8s/native/service/{service_name}", service)
                updated = True
                
            if updated:
                # Format the applied settings for the response
                settings_applied = []
                for setting, value in settings.items():
                    settings_applied.append(f"{setting}={value}")
                    
                return f"Successfully updated DuploCloud service '{service_name}' with settings: {', '.join(settings_applied)}"
            else:
                return f"No updates applied to service '{service_name}'"
                
        except Exception as e:
            logger.error(f"Error updating DuploCloud service: {str(e)}")
            return f"Failed to update DuploCloud service: {str(e)}"
