from typing import Any, Dict, List

from schemas.ProdReadinessCheck import ProdReadinessCheck
from schemas.ResourceProdReadinessReport import ResourceProdReadinessReport

class ProdReadinessChecksEvaluator:
    def __init__(self, checks: List[ProdReadinessCheck]):
        self.checks = checks

    def evaluate(self, resources: List[Dict[str, Any]]) -> Dict[str, ResourceProdReadinessReport]:
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
        if not resources and self.checks:
            # Create a placeholder result for "not found" case
            resource_id = "not_found"
            resource_results = {
                'checks': {},
                'pass_count': 0,
                'fail_count': 0,
                'critical_failures': 0,
                'warnings': 0
            }
            
            for check in self.checks:
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
            total_checks = len(self.checks)
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
            
            for check in self.checks:
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
            total_checks = len(self.checks)
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