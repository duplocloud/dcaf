import logging
import json
from typing import List, Dict, Any, Optional

from agent_server import AgentProtocol
from schemas.messages import AgentMessage
from services.llm import BedrockAnthropicLLM
from services.duplo_client import DuploClient
import os

logger = logging.getLogger(__name__)

class ProductionReadinessAgent(AgentProtocol):
    """
    An agent that evaluates DuploCloud resources for production readiness
    by checking best practices and security configurations.
    """
    
    def __init__(self, llm: BedrockAnthropicLLM, system_prompt: Optional[str] = None):
        """
        Initialize the ProductionReadinessAgent with an LLM instance and optional custom system prompt.
        
        Args:
            llm: An instance of BedrockAnthropicLLM for generating responses
            system_prompt: Optional custom system prompt to override the default
        """
        logger.info("Initializing ProductionReadinessAgent")
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
        self.llm = llm
        self.system_prompt = system_prompt or self._default_system_prompt()
    
    def _default_system_prompt(self) -> str:
        """Return the default system prompt for the Production Readiness Agent"""
        return """You are a Production Readiness Assessment agent for DuploCloud.
        Your job is to evaluate resources in a DuploCloud tenant for production readiness.
        Analyze the provided resource information and identify any issues or improvements needed.
        Provide clear recommendations and prioritize critical issues.
        Format your response in a clear, structured way with markdown for readability."""
    
    def _validate_platform_context(self, platform_context: Optional[Dict[str, Any]]) -> bool:
        """
        Validate that the platform context contains all required fields.
        
        Args:
            platform_context: Dictionary containing duplo_host, duplo_token, etc.
        
        Returns:
            True if all required fields are present, False otherwise
        """
        if not platform_context:
            logger.error("Platform context is missing")
            return False
            
        required_fields = ['duplo_host', 'duplo_token', 'tenant_name', 'tenant_id']
        logger.info("Validating platform context")
        
        # Check if all required fields exist and are not empty
        missing_fields = []
        for field in required_fields:
            if not platform_context.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            logger.error(f"Missing required fields in platform context: {', '.join(missing_fields)}")
            return False
        
        logger.info("Platform context validation successful")
        return True

    def _initialize_duplo_client(self, platform_context: Optional[Dict[str, Any]] = None) -> Optional[DuploClient]:
        """
        Initialize DuploClient with platform context.
        
        Args:
            platform_context: Dictionary containing duplo_host, duplo_token, etc.
        
        Returns:
            Initialized DuploClient or None if validation fails
        """
        if not platform_context:
            logger.warning("No platform context provided for DuploClient initialization")
            return None
            
        try:
            if not self._validate_platform_context(platform_context):
                return None
                
            logger.info("Initializing DuploClient...")
            return DuploClient(platform_context)
        except Exception as e:
            logger.error(f"Error initializing DuploClient: {str(e)}")
            return None
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """
        Process user messages, check resources for production readiness, and generate a response.
        
        Args:
            messages: A dictionary containing message history in the format {"messages": [...]}
            
        Returns:
            An AgentMessage containing the response and production readiness assessment
        """
        try:
            # Extract messages list from the messages dictionary
            messages_list = messages.get("messages", [])
            if not messages_list:
                return AgentMessage(
                    content="No messages found in the request. Please provide a valid request."
                )
            
            # Initialize DuploClient with platform context from the first message
            platform_context = messages_list[0].get("platform_context")
            if not self._validate_platform_context(platform_context):
                return AgentMessage(
                    content="I couldn't access your DuploCloud environment. Please ensure you're logged in to DuploCloud with valid credentials and have the necessary permissions."
                )
                
            self.duplo_client = self._initialize_duplo_client(platform_context)
            if not self.duplo_client:
                return AgentMessage(
                    content="Failed to initialize connection to DuploCloud. Please check your credentials and try again."
                )
            
            # Process messages to prepare for LLM
            processed_messages = self._preprocess_messages(messages)
            
            # Check resources for production readiness
            readiness_results = self.check_production_readiness()
            logger.debug(f"Readiness results: {json.dumps(readiness_results, indent=2)}")
            
            # Add readiness results to processed messages
            if readiness_results:
                processed_messages.append({
                    "role": "assistant", "content": f"Here are the production readiness results: {json.dumps(readiness_results, indent=2)}"
                })
            
            # Generate response from LLM
            llm_response = self.llm.invoke(
                messages=processed_messages, 
                model_id=self.model_id, 
                system_prompt=self.system_prompt
            )
            print("|--------------------------------------------------------------------------|")
            print(llm_response)
            print("|--------------------------------------------------------------------------|")
            # Create and return the agent message with assessment results
            return AgentMessage(content=llm_response)
            
        except Exception as e:
            logger.error(f"Error in ProductionReadinessAgent.invoke: {str(e)}", exc_info=True)
            return AgentMessage(
                content=f"I encountered an error while assessing your resources: {str(e)}\n\nPlease try again or contact support if the issue persists."
            )
    
    def _preprocess_messages(self, messages: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Preprocess messages for the LLM.
        
        Args:
            messages: A dictionary containing message history
            
        Returns:
            List of processed messages for the LLM
        """
        messages_list = messages.get("messages", [])
        processed_messages = []
        
        for message in messages_list:
            # Only include role and content for LLM
            processed_messages.append({
                "role": message.get("role", "user"),
                "content": message.get("content", "")
            })
        
        return processed_messages

    # def check_production_readiness(self, messages: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    #     """
    #     Check various DuploCloud resources for production readiness.
        
    #     Args:
    #         messages: A dictionary containing message history
            
    #     Returns:
    #         A dictionary with production readiness assessment results
    #     """
    #     # Check Duplo Services for production readiness
    #     logger.info("check_production_readiness 1: ProductionReadinessAgent")
    #     results = {}
    #     results["duplo_services"] = self._check_duplo_services(messages)
        
    #     return results
    
    # def _check_duplo_services(self, messages: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    #     """Check Duplo Services for production readiness"""
    #     results = {}
    #     logger.info("_check_duplo_services 1: ProductionReadinessAgent")
    #     for service in self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetReplicationControllers"):
    #         results[service["Name"]] = service
    #     return results
    
    def check_production_readiness(self) -> Dict[str, Any]:
        """
        Check resources for production readiness.
        
        Returns:
            Dictionary with readiness assessment results
        """
        if not self.duplo_client:
            logger.error("DuploClient not initialized")
            return {"error": "DuploClient not initialized"}
        
        try:
            tenant = self.duplo_client.tenant_name
            results = {
                "tenant": tenant,
                "timestamp": self._get_current_timestamp(),
                "resources": {},
                "summary": {
                    "total_resources": 0,
                    "passing_resources": 0,
                    "critical_issues": 0,
                    "warnings": 0,
                    "overall_score": 0
                }
            }
            
            # Check different resource types
            # The resource types to check would be determined by what's available in your DuploClient
            resources = self._get_resources_to_check()
            
            # Check RDS instances
            logger.info("Checking RDS instances...")
            if "rds" in resources:
                results["resources"]["rds"] = self._check_rds_instances(tenant, resources["rds"])
            else:
                results["resources"]["rds"] = []
                logger.info("No RDS instances found")
            
            # Check ecache clusters
            logger.info("Checking ecache clusters...")
            if "ecache" in resources:
                results["resources"]["ecache"] = self._check_ecache_clusters(tenant, resources["ecache"])
            else:
                results["resources"]["ecache"] = []
                logger.info("No ecache clusters found")
            
            # Check K8s deployments
            logger.info("Checking K8s deployments...")
            if "k8s_deployments" in resources:
                results["resources"]["k8s_deployments"] = self._check_k8s_deployments(tenant, resources["k8s_deployments"])
            else:
                results["resources"]["k8s_deployments"] = []
                logger.info("No K8s deployments found")
            
            # Check ASGs
            logger.info("Checking ASGs...")
            if "asgs" in resources:
                results["resources"]["asgs"] = self._check_autoscaling_groups(tenant, resources["asgs"])
            else:
                results["resources"]["asgs"] = []
                logger.info("No ASGs found")
            
            # Check S3 buckets
            logger.info("Checking S3 buckets...")
            if "s3" in resources:
                results["resources"]["s3"] = self._check_s3_buckets(tenant, resources["s3"])
            else:
                results["resources"]["s3"] = []
                logger.info("No S3 buckets found")
            
            # Calculate summary statistics
            logger.info("Calculating summary statistics...")
            self._calculate_summary(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking production readiness: {str(e)}", exc_info=True)
            return {"error": f"Error checking production readiness: {str(e)}"}
    
    def _get_resources_to_check(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get resources to check from DuploCloud.
        
        Returns:
            Dictionary with resource types and their instances
        """
        # This is a placeholder - you would implement actual resource fetching here
        # based on your DuploClient's capabilities
        return {
            "rds": self.duplo_client.get(f"v3/subscriptions/{self.duplo_client.tenant_id}/aws/rds/instance"),
            "ecache": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetEcacheInstances"),
            "k8s_deployments": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetReplicationControllers"),
            "s3": self.duplo_client.get(f"v3/subscriptions/{self.duplo_client.tenant_id}/aws/s3Bucket"),
            "asgs": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetTenantAsgProfiles"),
            # "duplo-logging": self.duplo_client.get(f"admin/GetLoggingEnabledTenants"),
            # "duplo-monitoring": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetTenantLoggingProfiles"),
        }
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()
    
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
                attribute_path = check['attribute_path']
                condition_func = check['condition']
                severity = check.get('severity', 'warning')
                recommendation = check.get('recommendation', '')
                
                # Extract attribute value by traversing the path
                attr_value = resource
                try:
                    for key in attribute_path:
                        attr_value = attr_value.get(key)
                        if attr_value is None:
                            break
                except (TypeError, KeyError):
                    attr_value = None
                
                # Apply condition function to the attribute value
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
    
    def _check_rds_instances(self, tenant: str, instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check RDS instances for production readiness"""
        
        # Define checks for RDS instances
        rds_checks = [
            {
                'name': 'encryption',
                'attribute_path': ['StorageEncrypted'],
                'condition': lambda val: (val is True, 
                                         "Storage encryption is enabled" if val is True else 
                                         "Storage encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable storage encryption for data protection"
            },
            {
                'name': 'multi_az',
                'attribute_path': ['MultiAZ'],
                'condition': lambda val: (val is True, 
                                         "Multi-AZ deployment is enabled" if val is True else 
                                         "Multi-AZ deployment is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Multi-AZ deployment for high availability"
            },
            {
                'name': 'backup_retention',
                'attribute_path': ['BackupRetentionPeriod'],
                'condition': lambda val: (val >= 7 if isinstance(val, (int, float)) else False,
                                         f"Backup retention period is {val} days" if isinstance(val, (int, float)) else
                                         "Backup retention period not set"),
                'severity': 'warning',
                'recommendation': "Set backup retention period to at least 7 days"
            },
            {
                'name': 'monitoring',
                'attribute_path': ['EnhancedMonitoringResourceArn'],
                'condition': lambda val: (val is not None, 
                                         "Enhanced monitoring is enabled" if val is not None else 
                                         "Enhanced monitoring is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable enhanced monitoring for better visibility"
            }
        ]
        
        return self._generic_resource_check(tenant, instances, rds_checks)
    
    def _check_ecache_clusters(self, tenant: str, clusters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check ecache clusters for production readiness"""
        
        # Define checks for ecache clusters
        ecache_checks = [
            {
                'name': 'encryption_in_transit',
                'attribute_path': ['TransitEncryptionEnabled'],
                'condition': lambda val: (val is True, 
                                         "Transit encryption is enabled" if val is True else 
                                         "Transit encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable transit encryption for data in transit"
            },
            {
                'name': 'auth_token',
                'attribute_path': ['AuthTokenEnabled'],
                'condition': lambda val: (val is True, 
                                         "AUTH token is enabled" if val is True else 
                                         "AUTH token is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AUTH token for authentication"
            },
            {
                'name': 'automatic_failover',
                'attribute_path': ['AutomaticFailover'],
                'condition': lambda val: (val == 'enabled', 
                                         "Automatic failover is enabled" if val == 'enabled' else 
                                         "Automatic failover is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable automatic failover for high availability"
            }
        ]
        
        return self._generic_resource_check(tenant, clusters, ecache_checks)
    
    def _check_k8s_deployments(self, tenant: str, deployments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check Kubernetes deployments for production readiness"""
        
        # Define checks for Kubernetes deployments
        k8s_checks = [
            {
                'name': 'replicas',
                'attribute_path': ['Replicas'],
                'condition': lambda val: (val >= 2 if isinstance(val, (int, float)) else False,
                                         f"Deployment has {val} replicas" if isinstance(val, (int, float)) else
                                         "Replica count not determined"),
                'severity': 'critical',
                'recommendation': "Configure at least 2 replicas for high availability"
            },
            {
                'name': 'resource_limits',
                'attribute_path': ['Template', 'template', 'spec', 'containers'],
                'condition': lambda containers: (
                    all(container.get('resources', {}).get('limits') for container in containers) if isinstance(containers, list) else False,
                    "All containers have resource limits" if isinstance(containers, list) and all(container.get('resources', {}).get('limits') for container in containers) else
                    "Some or all containers are missing resource limits"
                ),
                'severity': 'warning',
                'recommendation': "Set resource limits for all containers"
            },
            {
                'name': 'liveness_probe',
                'attribute_path': ['Template', 'spec', 'containers'],
                'condition': lambda containers: (
                    all(container.get('livenessProbe') for container in containers) if isinstance(containers, list) else False,
                    "All containers have liveness probes" if isinstance(containers, list) and all(container.get('livenessProbe') for container in containers) else
                    "Some or all containers are missing liveness probes"
                ),
                'severity': 'warning',
                'recommendation': "Configure liveness probes for all containers"
            }
        ]
        
        return self._generic_resource_check(tenant, deployments, k8s_checks)
    
    def _check_autoscaling_groups(self, tenant: str, asgs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check Auto Scaling Groups for production readiness"""
        
        asg_checks = [
            {
                'name': 'multiple_azs',
                'attribute_path': ['AvailabilityZones'],
                'condition': lambda azs: (
                    isinstance(azs, list) and len(azs) >= 2,
                    f"ASG spans {len(azs)} availability zones" if isinstance(azs, list) else
                    "ASG availability zones not determined"
                ),
                'severity': 'critical',
                'recommendation': "Configure ASG to span at least 2 availability zones"
            },
            {
                'name': 'min_instances',
                'attribute_path': ['MinSize'],
                'condition': lambda val: (
                    isinstance(val, (int, float)) and val >= 2,
                    f"Minimum instance count is {val}" if isinstance(val, (int, float)) else
                    "Minimum instance count not determined"
                ),
                'severity': 'critical',
                'recommendation': "Set minimum instance count to at least 2 for high availability"
            },
            {
                'name': 'instance_refresh_enabled',
                'attribute_path': ['InstanceRefreshConfig'],
                'condition': lambda val: (
                    val is not None,
                    "Instance refresh is configured" if val is not None else
                    "Instance refresh is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure instance refresh for rolling updates"
            },
            {
                'name': 'health_check_type',
                'attribute_path': ['HealthCheckType'],
                'condition': lambda val: (
                    val == 'ELB',
                    "ELB health check type is used" if val == 'ELB' else
                    f"Health check type is {val}"
                ),
                'severity': 'warning',
                'recommendation': "Use ELB health check type for better health monitoring"
            },
            {
                'name': 'termination_policies',
                'attribute_path': ['TerminationPolicies'],
                'condition': lambda policies: (
                    isinstance(policies, list) and any(p in ['OldestLaunchConfiguration', 'OldestLaunchTemplate'] for p in policies),
                    "Appropriate termination policies are configured" if isinstance(policies, list) and any(p in ['OldestLaunchConfiguration', 'OldestLaunchTemplate'] for p in policies) else
                    "Optimal termination policies not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure termination policies to include OldestLaunchConfiguration or OldestLaunchTemplate"
            }
        ]
        
        return self._generic_resource_check(tenant, asgs, asg_checks)

    def _check_s3_buckets(self, tenant: str, buckets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check S3 Buckets for production readiness"""
        
        s3_checks = [
            {
            'name': 'encryption',
            'attribute_path': ['ServerSideEncryptionConfiguration', 'Rules'],
            'condition': lambda rules: (
                isinstance(rules, list) and len(rules) > 0,
                "Server-side encryption is configured" if isinstance(rules, list) and len(rules) > 0 else
                "Server-side encryption is not configured"
            ),
            'severity': 'critical',
            'recommendation': "Enable default server-side encryption"
            },
            {
            'name': 'public_access_block',
            'attribute_path': ['PublicAccessBlockConfiguration'],
            'condition': lambda config: (
                config is not None and all([
                    config.get('BlockPublicAcls', False),
                    config.get('IgnorePublicAcls', False),
                    config.get('BlockPublicPolicy', False),
                    config.get('RestrictPublicBuckets', False)
                ]),
                "Public access block is fully configured" if config is not None else
                "Public access block is not fully configured"
            ),
            'severity': 'critical',
            'recommendation': "Enable all public access block settings"
            },
            {
            'name': 'versioning',
            'attribute_path': ['Versioning', 'Status'],
            'condition': lambda status: (
                status == 'Enabled',
                "Versioning is enabled" if status == 'Enabled' else
                "Versioning is not enabled"
            ),
            'severity': 'warning',
            'recommendation': "Enable versioning for data protection"
            },
            {
            'name': 'logging',
            'attribute_path': ['LoggingConfiguration'],
            'condition': lambda config: (
                config is not None and config.get('DestinationBucketName') is not None,
                "Logging is enabled" if config is not None and config.get('DestinationBucketName') is not None else
                "Logging is not enabled"
            ),
            'severity': 'warning',
            'recommendation': "Enable logging to track bucket access"
            },
            {
            'name': 'lifecycle_rules',
            'attribute_path': ['LifecycleConfiguration', 'Rules'],
            'condition': lambda rules: (
                isinstance(rules, list) and len(rules) > 0,
                f"{len(rules)} lifecycle rules configured" if isinstance(rules, list) else
                "No lifecycle rules configured"
            ),
            'severity': 'warning',
            'recommendation': "Configure lifecycle rules for cost optimization"
            }
        ]
    
        return self._generic_resource_check(tenant, buckets, s3_checks)

    def _calculate_summary(self, results: Dict[str, Any]) -> None:
        """
        Calculate summary statistics for assessment results.
        
        Args:
            results: Assessment results dictionary to update with summary
        """
        total_resources = 0
        passing_resources = 0
        critical_issues = 0
        warnings = 0
        
        # Process each resource type
        for resource_type, resources in results.get("resources", {}).items():
            for resource_id, resource_data in resources.items():
                total_resources += 1
                
                # A resource is considered passing if it has no critical failures
                if resource_data.get("critical_failures", 0) == 0:
                    passing_resources += 1
                
                critical_issues += resource_data.get("critical_failures", 0)
                warnings += resource_data.get("warnings", 0)
        
        # Update summary
        results["summary"]["total_resources"] = total_resources
        results["summary"]["passing_resources"] = passing_resources
        results["summary"]["critical_issues"] = critical_issues
        results["summary"]["warnings"] = warnings
        
        # Calculate overall score (0-100)
        if total_resources > 0:
            # Weight critical issues more heavily than warnings
            results["summary"]["overall_score"] = max(0, min(100, 
                100 - (critical_issues * 15 + warnings * 5) / total_resources
            ))
        else:
            results["summary"]["overall_score"] = 0