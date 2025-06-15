"""
Production Readiness Agent main module.
"""
import logging
import os
import re
from typing import Dict, Any, List, Optional, Tuple

from services.duplo_client import DuploClient
from services.llm_client import BedrockAnthropicLLM

from .resource_provider import ResourceProvider
from .checkers.s3_checker import S3ProductionReadinessChecker
from .checkers.rds_checker import RDSProductionReadinessChecker
from .checkers.k8s_checker import K8sProductionReadinessChecker
from .checkers.aws_security_checker import AWSSecurityProductionReadinessChecker
from .checkers.system_settings_checker import SystemSettingsProductionReadinessChecker
from .checkers.duplo_features_checker import DuploFeaturesProductionReadinessChecker

from .remediators.s3_remediator import S3Remediator
from .remediators.aws_security_remediator import AWSSecurityRemediator
from .remediators.system_settings_remediator import SystemSettingsRemediator
from .remediators.duplo_features_remediator import DuploFeaturesRemediator
from .remediators.service_remediator import ServiceRemediator

logger = logging.getLogger(__name__)

class ProductionReadinessAgent:
    """
    Agent for checking and remediating production readiness issues in DuploCloud.
    """
    
    def __init__(self, duplo_client: DuploClient):
        """
        Initialize the Production Readiness Agent.
        
        Args:
            duplo_client: An instance of DuploClient for API calls
        """
        self.duplo_client = duplo_client
        self.llm = BedrockAnthropicLLM(model_id=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"))
        
        # Initialize resource provider
        self.resource_provider = ResourceProvider(duplo_client)
        
        # Initialize checkers
        self.s3_checker = S3ProductionReadinessChecker(duplo_client)
        self.rds_checker = RDSProductionReadinessChecker(duplo_client)
        self.k8s_checker = K8sProductionReadinessChecker(duplo_client)
        self.aws_security_checker = AWSSecurityProductionReadinessChecker(duplo_client)
        self.system_settings_checker = SystemSettingsProductionReadinessChecker(duplo_client)
        self.duplo_features_checker = DuploFeaturesProductionReadinessChecker(duplo_client)
        
        # Initialize remediators
        self.s3_remediator = S3Remediator(duplo_client)
        self.aws_security_remediator = AWSSecurityRemediator(duplo_client)
        self.system_settings_remediator = SystemSettingsRemediator(duplo_client)
        self.duplo_features_remediator = DuploFeaturesRemediator(duplo_client)
        self.service_remediator = ServiceRemediator(duplo_client)
    
    def invoke(self, tenant: str, message: str) -> str:
        """
        Invoke the Production Readiness Agent.
        
        Args:
            tenant: Tenant name or ID
            message: User message
            
        Returns:
            Agent response
        """
        # Check if this is a remediation approval
        if message.strip().upper() == "APPROVE":
            return self._handle_remediation_approval()
            
        # Check if this is a remediation action
        if "```remediation" in message:
            return self._handle_remediation_request(tenant, message)
            
        # Otherwise, perform a production readiness assessment
        return self._perform_assessment(tenant, message)
    
    def _perform_assessment(self, tenant: str, message: str) -> str:
        """
        Perform a production readiness assessment for a tenant.
        
        Args:
            tenant: Tenant name or ID
            message: User message
            
        Returns:
            Assessment results
        """
        try:
            # Get tenant resources
            resources = self.resource_provider.get_tenant_resources(tenant)
            
            # Perform checks
            check_results = {
                "s3_buckets": self.s3_checker.check(tenant, resources.get("s3_buckets", [])),
                "rds_instances": self.rds_checker.check(tenant, resources.get("rds_instances", [])),
                "services": self.k8s_checker.check(tenant, resources.get("services", [])),
                "aws_security_features": self.aws_security_checker.check(tenant, resources.get("aws_security_features", {})),
                "system_settings": self.system_settings_checker.check(tenant, resources.get("system_settings", {})),
                "duplo_features": self.duplo_features_checker.check(tenant, resources.get("duplo_features", {}))
            }
            
            # Generate assessment using LLM
            prompt = self._generate_assessment_prompt(tenant, resources, check_results)
            assessment = self.llm.generate(prompt)
            
            return assessment
            
        except Exception as e:
            logger.error(f"Error performing assessment: {str(e)}")
            return f"Error performing assessment: {str(e)}"
    
    def _handle_remediation_request(self, tenant: str, message: str) -> str:
        """
        Handle a remediation request.
        
        Args:
            tenant: Tenant name or ID
            message: User message containing remediation actions
            
        Returns:
            Response with remediation actions to approve
        """
        try:
            # Extract remediation actions
            actions = self._extract_remediation_actions(message)
            if not actions:
                return "No valid remediation actions found in the message."
                
            # Store actions for later approval
            self._pending_remediation_actions = {
                "tenant": tenant,
                "actions": actions
            }
            
            # Format actions for display
            action_list = "\n".join([f"- {action}" for action in actions])
            
            return f"The following remediation actions will be performed when you type 'APPROVE':\n\n{action_list}\n\nPlease type 'APPROVE' to execute these actions, or provide alternative instructions."
        except Exception as e:
            logger.error(f"Error handling remediation request: {str(e)}")
            return f"Error handling remediation request: {str(e)}"
    
    def _handle_remediation_approval(self, tenant: str, message: str) -> str:
        """
        Handle a remediation approval.
        
        Args:
            tenant: Tenant name or ID
            message: User message containing approval
            
        Returns:
            Response with remediation results
        """
        try:
            # Check if there are pending actions
            if not self._pending_remediation_actions:
                return "There are no pending remediation actions to approve."
                
            # Check if the tenant matches
            if self._pending_remediation_actions["tenant"] != tenant:
                return f"The pending remediation actions are for tenant {self._pending_remediation_actions['tenant']}, not {tenant}."
                
            # Get the actions
            actions = self._pending_remediation_actions["actions"]
            
            # Execute each action
            results = []
            for action in actions:
                try:
                    result = self._execute_remediation_action(tenant, action)
                    results.append(f"✅ {action}: {result}")
                except Exception as e:
                    logger.error(f"Error executing remediation action '{action}': {str(e)}")
                    results.append(f"❌ {action}: {str(e)}")
            
            # Clear pending actions
            self._pending_remediation_actions = None
            
            # Format results
            result_list = "\n".join(results)
            return f"Remediation actions executed:\n\n{result_list}"
        except Exception as e:
            logger.error(f"Error handling remediation approval: {str(e)}")
            return f"Error handling remediation approval: {str(e)}"
    
    def _execute_remediation_action(self, tenant: str, action: str) -> str:
        """
        Execute a remediation action.
        
        Args:
            tenant: Tenant name or ID
            action: Action string in format action_type:parameters
            
        Returns:
            Result message
        """
        # Parse the action
        parts = action.split(":", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid action format: {action}")
            
        action_type = parts[0].strip().lower()
        action_params = parts[1].strip() if len(parts) > 1 else ""
    
    def _extract_remediation_actions(self, message: str) -> List[str]:
        """
        Extract remediation actions from a message.
        
        Args:
            message: Message containing remediation actions
            
        Returns:
            List of action strings
        """
        # Look for remediation code blocks
        pattern = r"```remediation\s*\n([\s\S]*?)\n\s*```"
        matches = re.findall(pattern, message)
        
        if not matches:
            return []
            
        # Extract actions from the first code block
        actions = []
        for line in matches[0].strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                actions.append(line)
                
        return actions
    except Exception as e:
        logger.error(f"Error extracting remediation actions: {str(e)}")
        return []

def _handle_remediation_approval(self) -> str:
    """
    Handle a remediation approval.
    
    Returns:
        Response with remediation results
    """
    try:
        # Check if there are pending actions
        if not hasattr(self, "_pending_remediation_actions") or not self._pending_remediation_actions:
            return "No pending remediation actions to approve."
            # Get pending actions
            tenant = self._pending_remediation_actions["tenant"]
            actions = self._pending_remediation_actions["actions"]
            
            # Execute actions
            results = []
            for action in actions:
                result = self._execute_remediation_action(tenant, action)
                results.append(f"- {action}: {result}")
                
            # Clear pending actions
            self._pending_remediation_actions = None
            
            # Format results
            result_list = "\n".join(results)
            
            return f"""
Remediation actions completed:

{result_list}"""
"""
            
        except Exception as e:
            logger.error(f"Error handling remediation approval: {str(e)}")
            return f"Error handling remediation approval: {str(e)}"
    
    def _execute_remediation_action(self, tenant: str, action: str) -> str:
        """
        Execute a remediation action.
        
        Args:
            tenant: Tenant name or ID
            action: Remediation action string
            
        Returns:
            Result of the remediation action
        """
        parts = action.split(":", 1)
        action_type = parts[0].strip().lower()
        action_params = parts[1].strip() if len(parts) > 1 else ""
        
        if action_type == "update_s3_bucket":
            return self.s3_remediator.remediate(tenant, action_params)
        elif action_type == "enable_aws_security_feature":
            return self.aws_security_remediator.remediate(tenant, action_params)
        elif action_type == "update_duplo_system_setting":
            return self.system_settings_remediator.remediate(tenant, action_params)
        elif action_type == "enable_duplo_monitoring" or action_type == "enable_duplo_logging" or action_type == "enable_duplo_alerting" or action_type == "enable_fault_notification_channel":
            return self.duplo_features_remediator.remediate(tenant, action_params)
        elif action_type == "update_duplo_service":
            return self.service_remediator.remediate(tenant, action_params)
        else:
            return f"Unsupported action type: {action_type}"
    

    
    def _generate_assessment_prompt(self, tenant: str, resources: Dict[str, Any], check_results: Dict[str, Any]) -> str:
        """
        Generate a prompt for the LLM to create an assessment.
        
        Args:
            tenant: Tenant name or ID
            resources: Dictionary with tenant resources
            check_results: Dictionary with check results
            
        Returns:
            Prompt for the LLM
        """
        # Create a summary of resources
        resource_summary = self._create_resource_summary(resources)
        
        # Create a summary of check results
        check_summary = self._create_check_summary(check_results)
        
        # Combine into a prompt
        prompt = f"""
{self._default_system_prompt()}

You are performing a production readiness assessment for tenant: {tenant}

## Resource Summary
{resource_summary}

## Check Results
{check_summary}"""
"""
        
        return prompt
    
    def _create_resource_summary(self, resources: Dict[str, Any]) -> str:
        """
        Create a summary of tenant resources.
        
        Args:
            resources: Dictionary with tenant resources
            
        Returns:
            String with resource summary
        """
        summary = []
        
        # Count services
        services = resources.get("services", [])
        summary.append(f"DuploCloud Services: {len(services)}")
        
        # Count S3 buckets
        s3_buckets = resources.get("s3_buckets", [])
        summary.append(f"S3 Buckets: {len(s3_buckets)}")
        
        # Count RDS instances
        rds_instances = resources.get("rds_instances", [])
        summary.append(f"RDS Instances: {len(rds_instances)}")
        
        # Count ElastiCache clusters
        elasticache_clusters = resources.get("elasticache_clusters", [])
        summary.append(f"ElastiCache Clusters: {len(elasticache_clusters)}")
        
        # Count DynamoDB tables
        dynamodb_tables = resources.get("dynamodb_tables", [])
        summary.append(f"DynamoDB Tables: {len(dynamodb_tables)}")
        
        # Count EFS filesystems
        efs_filesystems = resources.get("efs_filesystems", [])
        summary.append(f"EFS Filesystems: {len(efs_filesystems)}")
        
        # Format as a list
        return "\n".join([f"- {item}" for item in summary])
    
    def _create_check_summary(self, check_results: Dict[str, Any]) -> str:
        """
        Create a summary of check results.
        
        Args:
            check_results: Dictionary with check results
            
        Returns:
            String with check summary
        """
        summary = []
        
        # Process each resource type
        for resource_type, result in check_results.items():
            # Skip empty results
            if not result or not result.get("resources"):
                continue
                
            resources = result.get("resources", [])
            resource_count = len(resources)
            
            # Count passed and failed checks
            total_checks = 0
            passed_checks = 0
            critical_failures = 0
            warning_failures = 0
            
            for resource in resources:
                checks = resource.get("checks", [])
                total_checks += len(checks)
                
                for check in checks:
                    if check.get("passed"):
                        passed_checks += 1
                    elif check.get("severity") == "critical":
                        critical_failures += 1
                    elif check.get("severity") == "warning":
                        warning_failures += 1
            
            # Format the summary
            if total_checks > 0:
                pass_rate = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
                summary.append(f"{resource_type.replace('_', ' ').title()}: {resource_count} resources, {passed_checks}/{total_checks} checks passed ({pass_rate:.1f}%), {critical_failures} critical failures, {warning_failures} warnings")
        
        # Format as a list
        return "\n".join([f"- {item}" for item in summary])
    
    def _default_system_prompt(self) -> str:
        """
        Get the default system prompt for the LLM.
        
        Returns:
            System prompt string
        """
        return """You are a DuploCloud Production Readiness Assessment Agent. Your task is to evaluate the production readiness of a tenant's resources in DuploCloud and provide recommendations for improvement.

IMPORTANT: Always refer to Kubernetes deployments as "DuploCloud Services" and use DuploCloud platform terminology rather than Kubernetes terminology.

Begin your response with a title: "Production Readiness Assessment for Tenant: [tenant_name]"

Follow this structure for your assessment:

## Overall Assessment
**Score: X/100**

Provide a brief summary of the tenant's production readiness, highlighting the most critical issues that need to be addressed.

## Resource Assessment

### DuploCloud Services
**Score: X/100**

For each DuploCloud Service, create a table with the following columns:
- Check Name
- Status (✅/❌)
- Severity (CRITICAL/WARNING/INFO)
- Recommendation

Example:

#### Service: api-service

| Check | Status | Severity | Recommendation |
|-------|--------|----------|----------------|
| Replicas >= 2 | ✅/❌ | CRITICAL | [brief recommendation] |
| Resource Limits | ✅/❌ | WARNING | [brief recommendation] |
| Health Checks | ✅/❌ | WARNING | [brief recommendation] |

### AWS Resources
**Score: X/100**

#### S3 Buckets

| Check | Status | Severity | Recommendation |
|-------|--------|----------|----------------|
| Encryption | ✅/❌ | CRITICAL | [brief recommendation] |
| Versioning | ✅/❌ | WARNING | [brief recommendation] |
| Lifecycle Policy | ✅/❌ | INFO | [brief recommendation] |

#### RDS Databases

| Check | Status | Severity | Recommendation |
|-------|--------|----------|----------------|
| Multi-AZ | ✅/❌ | CRITICAL | [brief recommendation] |
| Automated Backups | ✅/❌ | CRITICAL | [brief recommendation] |
| Encryption | ✅/❌ | CRITICAL | [brief recommendation] |

Other AWS resources to include if present:
- ElastiCache
- DynamoDB Tables
- EFS
- DuploCloud Features (Logging, Monitoring, Alerting, Notification)
- AWS Security Features

### AWS Security Features
**Score: X/100**

| Check | Status | Severity | Recommendation |
|-------|--------|----------|----------------|
| VPC Flow Logs | ✅/❌ | CRITICAL | [brief recommendation] |
| Security Hub | ✅/❌ | CRITICAL | [brief recommendation] |
| GuardDuty | ✅/❌ | CRITICAL | [brief recommendation] |
| CloudTrail | ✅/❌ | CRITICAL | [brief recommendation] |
| Password Policy | ✅/❌ | WARNING | [brief recommendation] |
| S3 Public Access Block | ✅/❌ | CRITICAL | [brief recommendation] |
| Inspector | ✅/❌ | WARNING | [brief recommendation] |
| CIS CloudTrail CloudWatch Alarms | ✅/❌ | WARNING | [brief recommendation] |
| Security Hub in All Regions | ✅/❌ | WARNING | [brief recommendation] |
| Inspector in All Regions | ✅/❌ | WARNING | [brief recommendation] |

### DuploCloud System Settings
**Score: X/100**

| Check | Status | Severity | Recommendation |
|-------|--------|----------|----------------|
| User Token Expiration | ✅/❌ | WARNING | [brief recommendation] |
| Notification Email | ✅/❌ | WARNING | [brief recommendation] |

FAILURE TO INCLUDE THESE TWO SECTIONS WILL RESULT IN AN INCOMPLETE ASSESSMENT.

## Recommendations

### Immediate Actions (Critical)
- [List of critical recommendations]

### Short-term Improvements (Warnings)
- [List of warning recommendations]

### Long-term Optimizations (Info)
- [List of info recommendations]

## Remediation Actions

If the user asks for help implementing any of the recommendations, suggest specific remediation actions they can take. Format these actions in a special code block that starts with ```remediation and ends with ```. Each line in the code block should represent one action in the following format:

```remediation
action_type:parameters
```

Use the following action types:

1. enable_aws_security_feature - To enable AWS security features
    Examples: 
    - enable_aws_security_feature:guardduty:true
    - enable_aws_security_feature:vpc_flow_logs:true
    - enable_aws_security_feature:security_hub:true
    - enable_aws_security_feature:cloudtrail:true
    - enable_aws_security_feature:s3_public_access_block:true
    - enable_aws_security_feature:inspector:true
    - enable_aws_security_feature:password_policy:true
    - enable_aws_security_feature:delete_default_vpcs:true
    - enable_aws_security_feature:revoke_default_sg_rules:true
    - enable_aws_security_feature:delete_default_nacl_rules:true
    Supported features: vpc_flow_logs, security_hub, guardduty, cloudtrail, s3_public_access_block, inspector, password_policy, delete_default_vpcs, revoke_default_sg_rules, delete_default_nacl_rules

2. update_duplo_system_setting - To update DuploCloud system settings
    Examples: 
    - update_duplo_system_setting:token_expiration_notification_email=alerts@example.com
    - update_duplo_system_setting:user_token_expiration=30
    - update_duplo_system_setting:token_expiration_notification_email=security@company.com
    - update_duplo_system_setting:user_token_expiration=90
    Supported settings: user_token_expiration, token_expiration_notification_email

3. enable_duplo_monitoring - To enable monitoring for a tenant
    Examples: 
    - enable_duplo_monitoring:true

4. enable_duplo_logging - To enable logging for a tenant
    Examples: 
    - enable_duplo_logging:true

5. enable_duplo_alerting - To configure alerting for a tenant
    Examples: 
    - enable_duplo_alerting:true

6. enable_fault_notification_channel - To configure fault notification channel for a tenant
    Examples: 
    - enable_fault_notification_channel:pagerduty=YOUR_PD_SERVICE_KEY
    - enable_fault_notification_channel:sentry=YOUR_DSN
    - enable_fault_notification_channel:newrelic=YOUR_NR_API_KEY
    - enable_fault_notification_channel:opsgenie=YOUR_OPSGENIE_API_KEY
    Supported channels: pagerduty, sentry, newrelic, opsgenie

7. update_duplo_service - To update a DuploCloud Service configuration
    Examples: 
    - update_duplo_service:my-api-service:replicas=3
    - update_duplo_service:my-worker-service:cpu=1
    - update_duplo_service:my-web-service:memory=2048
    - update_duplo_service:my-backend-service:health_check=true
    - update_duplo_service:my-frontend-service:replicas=2:cpu=0.5:memory=1024
    Supported settings: replicas, cpu, memory, health_check

8. update_s3_bucket - To update S3 bucket configuration
    Examples: 
    - update_s3_bucket:my-bucket:versioning=true
    - update_s3_bucket:my-bucket:logging=true
    - update_s3_bucket:my-bucket:encryption=true
    - update_s3_bucket:my-bucket:public_access=false
    Supported settings: versioning, logging, encryption, public_access

The user must explicitly type "APPROVE" to execute any of these remediation actions. Always explain what each action will do before suggesting it.
```        
Always use tables for showing check results with columns for Check Name, Status (✅/❌), Severity, and Recommendation

Remember that your assessment directly impacts production deployment decisions, so be thorough, accurate, and provide practical, implementable recommendations."""
