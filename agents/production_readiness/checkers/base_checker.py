"""
Base checker class for the Production Readiness Agent.
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BaseChecker(ABC):
    """
    Abstract base class for all production readiness checkers.
    """
    
    def __init__(self, duplo_client):
        """
        Initialize the checker with a DuploClient instance.
        
        Args:
            duplo_client: An instance of DuploClient for API calls
        """
        self.duplo_client = duplo_client
    
    @abstractmethod
    def check(self, tenant: str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check resources for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: List of resources to check
            
        Returns:
            Dictionary with check results
        """
        pass
    
    def _generic_resource_check(self, tenant: str, resources: List[Dict[str, Any]], 
                               checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generic function to check attributes on resources.
        
        Args:
            tenant: Tenant name or ID
            resources: List of resource objects to check
            checks: List of check configurations, each containing:
                - name: Name of the check
                - attribute_path: List of keys to traverse to get the attribute
                - condition: Function that takes the attribute value and returns (passed, message)
                - severity: Severity of the check (critical, warning, info)
                - recommendation: Recommendation if the check fails
            
        Returns:
            Dictionary with check results for each resource
        """
        results = []
        
        # Skip if no resources
        if not resources:
            return {"resources": []}
        
        # Process each resource
        for resource in resources:
            resource_name = resource.get("Name", "Unknown")
            resource_result = {
                "name": resource_name,
                "checks": []
            }
            
            # Run each check on the resource
            for check in checks:
                check_name = check.get("name", "Unknown Check")
                attribute_path = check.get("attribute_path", [])
                condition_func = check.get("condition", lambda x: (False, "No condition specified"))
                severity = check.get("severity", "info")
                recommendation = check.get("recommendation", "No recommendation provided")
                
                # Get the attribute value by traversing the path
                attr_value = resource
                try:
                    for key in attribute_path:
                        if isinstance(attr_value, dict) and key in attr_value:
                            attr_value = attr_value[key]
                        else:
                            attr_value = None
                            break
                except Exception as e:
                    logger.warning(f"Error accessing attribute path {attribute_path} for {resource_name}: {str(e)}")
                    attr_value = None
                
                # Apply the condition function
                try:
                    passed, message = condition_func(attr_value)
                except Exception as e:
                    logger.warning(f"Error applying condition for check {check_name} on {resource_name}: {str(e)}")
                    passed, message = False, f"Error evaluating condition: {str(e)}"
                
                # Add the check result
                resource_result["checks"].append({
                    "name": check_name,
                    "passed": passed,
                    "message": message,
                    "severity": severity,
                    "recommendation": recommendation if not passed else ""
                })
            
            results.append(resource_result)
        
        return {"resources": results}
    
    def _filter_resources(self, resources: List[Dict[str, Any]], 
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
            
        filtered_resources = []
        
        for resource in resources:
            name = resource.get(name_field, "")
            
            # Skip resources with excluded prefixes
            if any(name.startswith(prefix) for prefix in exclude_prefixes):
                continue
                
            filtered_resources.append(resource)
            
        return filtered_resources
