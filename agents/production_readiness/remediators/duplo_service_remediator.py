# duplo_service_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging
import json

logger = logging.getLogger(__name__)

class DuploServiceRemediator(BaseRemediator):
    """
    Remediator for DuploCloud service configurations.
    Updates service settings like replicas, resource limits, and health checks.
    """
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a DuploCloud service configuration.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - service_name: Name of the service to update
                - replicas: Number of replicas to set
                - cpu: CPU limit to set
                - memory: Memory limit to set
                - health_check: Health check configuration
                - hpa_min_replicas: Minimum replicas for HPA
                - hpa_max_replicas: Maximum replicas for HPA
                - hpa_cpu_threshold: CPU threshold for HPA scaling
            
        Returns:
            Dictionary with execution results
        """
        # Extract parameters
        service_name = action_params.get("service_name")
        if not service_name:
            return {
                "success": False,
                "message": "Service name is required",
                "details": {"tenant": tenant}
            }
        
        logger.info(f"Updating service {service_name} for tenant {tenant}")
        
        # Get current service configuration
        services = self.get_resources(tenant, "k8s_deployments")
        
        # Find the target service
        target_service = None
        for service in services:
            if service.get("Name") == service_name:
                target_service = service
                break
        
        if not target_service:
            return {
                "success": False,
                "message": f"Service {service_name} not found in tenant {tenant}",
                "details": {"tenant": tenant, "service_name": service_name}
            }
        
        # Prepare update payload
        update_payload = {}
        
        # Update replicas if specified
        if "replicas" in action_params:
            replicas = action_params["replicas"]
            update_payload["Replicas"] = replicas
            logger.info(f"Setting replicas to {replicas} for service {service_name}")
        
        # Update CPU if specified
        if "cpu" in action_params:
            cpu = action_params["cpu"]
            update_payload["Cpu"] = cpu
            logger.info(f"Setting CPU to {cpu} for service {service_name}")
        
        # Update memory if specified
        if "memory" in action_params:
            memory = action_params["memory"]
            update_payload["Memory"] = memory
            logger.info(f"Setting memory to {memory} for service {service_name}")
        
        # Update health check if specified
        if "health_check" in action_params:
            health_check = action_params["health_check"]
            update_payload["HealthCheckUrl"] = health_check
            logger.info(f"Setting health check to {health_check} for service {service_name}")
        
        # Update HPA configuration if specified
        hpa_update = {}
        if "hpa_min_replicas" in action_params:
            hpa_update["minReplicas"] = action_params["hpa_min_replicas"]
        
        if "hpa_max_replicas" in action_params:
            hpa_update["maxReplicas"] = action_params["hpa_max_replicas"]
        
        if "hpa_cpu_threshold" in action_params:
            hpa_update["metrics"] = [{
                "type": "Resource",
                "resource": {
                    "name": "cpu",
                    "targetAverageUtilization": action_params["hpa_cpu_threshold"]
                }
            }]
        
        if hpa_update:
            # Merge with existing HPA specs if available
            existing_hpa = target_service.get("HPASpecs", {})
            if existing_hpa:
                for key, value in hpa_update.items():
                    existing_hpa[key] = value
                update_payload["HPASpecs"] = existing_hpa
            else:
                # Set minimum required fields if no existing HPA
                if "minReplicas" not in hpa_update:
                    hpa_update["minReplicas"] = 2
                if "maxReplicas" not in hpa_update:
                    hpa_update["maxReplicas"] = 10
                if "metrics" not in hpa_update:
                    hpa_update["metrics"] = [{
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "targetAverageUtilization": 70
                        }
                    }]
                update_payload["HPASpecs"] = hpa_update
            
            logger.info(f"Updating HPA configuration for service {service_name}")
        
        # Update Docker configuration if needed for probes
        if "liveness_probe" in action_params or "readiness_probe" in action_params:
            docker_config = {}
            
            # Get existing Docker config if available
            if "Template" in target_service and "OtherDockerConfig" in target_service["Template"]:
                try:
                    existing_config = json.loads(target_service["Template"]["OtherDockerConfig"])
                    docker_config = existing_config
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # Update liveness probe
            if "liveness_probe" in action_params:
                docker_config["LivenessProbe"] = action_params["liveness_probe"]
            
            # Update readiness probe
            if "readiness_probe" in action_params:
                docker_config["ReadinessProbe"] = action_params["readiness_probe"]
            
            # Update rolling update strategy
            if "rolling_update" in action_params:
                docker_config["DeploymentStrategy"] = {
                    "Type": "RollingUpdate",
                    "RollingUpdate": action_params["rolling_update"]
                }
            
            # Update resource limits and requests
            if "resource_limits" in action_params or "resource_requests" in action_params:
                resources = docker_config.get("Resources", {})
                
                if "resource_limits" in action_params:
                    resources["limits"] = action_params["resource_limits"]
                
                if "resource_requests" in action_params:
                    resources["requests"] = action_params["resource_requests"]
                
                docker_config["Resources"] = resources
            
            # Update the Docker config in the payload
            if not "Template" in update_payload:
                update_payload["Template"] = {}
            
            update_payload["Template"]["OtherDockerConfig"] = json.dumps(docker_config)
            logger.info(f"Updating Docker configuration for service {service_name}")
        
        # Execute the update if there are changes to make
        if update_payload:
            try:
                # Add required fields for the update
                update_payload["Name"] = service_name
                update_payload["TenantId"] = tenant
                
                # Update the service
                self.duplo_client.post(f"v2/subscriptions/{tenant}/UpdateService", update_payload)
                logger.info(f"Successfully updated service {service_name} for tenant {tenant}")
                
                return {
                    "success": True,
                    "message": f"Successfully updated service {service_name}",
                    "details": {
                        "tenant": tenant,
                        "service_name": service_name,
                        "updates": {k: v for k, v in action_params.items() if k != "service_name"}
                    }
                }
            except Exception as e:
                logger.error(f"Failed to update service {service_name} for tenant {tenant}: {e}")
                return {
                    "success": False,
                    "message": f"Failed to update service: {str(e)}",
                    "details": {"tenant": tenant, "service_name": service_name, "error": str(e)}
                }
        else:
            return {
                "success": False,
                "message": "No updates specified",
                "details": {"tenant": tenant, "service_name": service_name}
            }