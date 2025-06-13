# base_checker.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from services.duplo_client import DuploClient
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class BaseChecker(ABC):
    """Base class for all resource checkers"""
    
    def __init__(self, duplo_client: DuploClient, resource_provider: Optional[ResourceProvider] = None):
        self.duplo_client = duplo_client
        self.resource_provider = resource_provider or ResourceProvider(duplo_client)
        
    def get_resources(self, tenant: str, resource_type: str) -> List[Dict[str, Any]]:
        """
        Get resources of a specific type for a tenant.
        
        Args:
            tenant: Tenant name or ID
            resource_type: Type of resource to fetch
            
        Returns:
            List of resources of the specified type
        """
        return self.resource_provider.get_resource_by_type(tenant, resource_type)
        
    def _filter_resources(self, resources: List[Dict[str, Any]], exclude_prefixes: List[str], name_field: str = "Name") -> List[Dict[str, Any]]:
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
    
    def _generic_resource_check(self, tenant: str, resources: List[Dict[str, Any]], 
                           checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generic function to check attributes on resources.
        
        Args:
            tenant: Tenant name or ID
            resources: List of resource objects to check
            checks: List of check configurations, each containing:
                - name: Name of the check
                - attribute_path: List of keys to traverse to reach the attribute
                - condition: Function that takes attribute value and returns (bool, str)
                  where bool indicates pass/fail and str is the message
                - severity: 'critical', 'warning', or 'info'
                - recommendation: Recommendation if check fails
        
        Returns:
            Dictionary with check results for each resource
        """
        results = {}
        
        # Handle case where resources list is empty but we still want to run checks
        # (e.g., for "resource not found" type checks)
        if not resources and checks:
            # Create a placeholder result for "not found" case
            resource_id = "not_found"
            resource_results = {
                'checks': {},
                'pass_count': 0,
                'fail_count': 0,
                'critical_failures': 0,
                'warnings': 0
            }
            
            for check in checks:
                check_name = check['name']
                condition_func = check.get('condition', lambda val: (val is not None, "Attribute is set"))
                severity = check.get('severity', 'warning')
                recommendation = check.get('recommendation', '')
                
                # Apply condition function with None as the attribute value
                # Check if the condition function accepts a resource parameter
                try:
                    passed, message = condition_func(None, None)
                except TypeError:
                    # Fallback to original behavior if the function doesn't accept resource parameter
                    passed, message = condition_func(None)
                
                check_result = {
                    'passed': passed,
                    'message': message,
                    'severity': severity,
                    'recommendation': recommendation if not passed else ''
                }
                
                # Update counters
                if passed:
                    resource_results['pass_count'] += 1
                else:
                    resource_results['fail_count'] += 1
                    if severity == 'critical':
                        resource_results['critical_failures'] += 1
                    elif severity == 'warning':
                        resource_results['warnings'] += 1
                
                resource_results['checks'][check_name] = check_result
            
            # Calculate score
            total_checks = len(checks)
            if total_checks > 0:
                weighted_score = (
                    resource_results['pass_count'] * 1.0 - 
                    resource_results['critical_failures'] * 1.5 - 
                    resource_results['warnings'] * 0.5
                ) / total_checks * 100
                resource_results['score'] = max(0, min(100, weighted_score))
            else:
                resource_results['score'] = 0
            
            results[resource_id] = resource_results
            return results
        
        # Normal case with resources present
        for resource in resources:
            resource_id = resource.get('identifier', resource.get('Name', 'unknown'))
            resource_results = {
                'checks': {},
                'pass_count': 0,
                'fail_count': 0,
                'critical_failures': 0,
                'warnings': 0
            }
            
            for check in checks:
                check_name = check['name']
                attribute_path = check.get('attribute_path', [])
                condition_func = check.get('condition', lambda val: (val is not None, "Attribute is set"))
                severity = check.get('severity', 'warning')
                recommendation = check.get('recommendation', '')
                
                # Extract attribute value by traversing the path
                attr_value = resource
                try:
                    if attribute_path:
                        for key in attribute_path:
                            attr_value = attr_value.get(key)
                            if attr_value is None:
                                break
                except (TypeError, KeyError):
                    attr_value = None
                
                # Apply condition function to the attribute value
                # Check if the condition function accepts a resource parameter
                try:
                    passed, message = condition_func(attr_value, resource)
                except TypeError:
                    # Fallback to original behavior if the function doesn't accept resource parameter
                    passed, message = condition_func(attr_value)
                
                check_result = {
                    'passed': passed,
                    'message': message,
                    'severity': severity,
                    'recommendation': recommendation if not passed else ''
                }
                
                # Update counters
                if passed:
                    resource_results['pass_count'] += 1
                else:
                    resource_results['fail_count'] += 1
                    if severity == 'critical':
                        resource_results['critical_failures'] += 1
                    elif severity == 'warning':
                        resource_results['warnings'] += 1
                
                resource_results['checks'][check_name] = check_result
            
            # Calculate score (0-100)
            total_checks = len(checks)
            if total_checks > 0:
                # Weight critical failures more heavily
                weighted_score = (
                    resource_results['pass_count'] * 1.0 - 
                    resource_results['critical_failures'] * 1.5 - 
                    resource_results['warnings'] * 0.5
                ) / total_checks * 100
                resource_results['score'] = max(0, min(100, weighted_score))
            else:
                resource_results['score'] = 0
            
            results[resource_id] = resource_results
        
        return results
        
    @abstractmethod
    def check(self, tenant: str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check resources for production readiness
        
        Args:
            tenant: Tenant name or ID
            resources: List of resources to check
            
        Returns:
            Dictionary with check results
        """
        pass