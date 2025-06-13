import logging
import json
from typing import List, Dict, Any, Optional
from agent_server import AgentProtocol
from agents.tools.CheckK8sDeploymentProdReadinessTool import CheckK8sDeploymentProdReadinessTool
from agents.tools.CheckElastiCacheProdReadinessTool import CheckElastiCacheProdReadinessTool
from agents.tools.CheckRdsProdReadinessTool import CheckRdsProdReadinessTool
from agents.tools.CheckS3BucketProdReadinessTool import CheckS3BucketProdReadinessTool
from agents.tools.CheckSystemSecurityFeaturesProdReadinessTool import CheckSystemSecurityFeaturesProdReadinessTool
from agents.tools.CheckSystemSettingsProdReadinessTool import CheckSystemSettingsProdReadinessTool
from agents.tools.CheckTenantSettingsProdReadinessTool import CheckTenantSettingsProdReadinessTool
from agents.tools.GetElastiCacheInstancesTool import GetElastiCacheInstancesTool
from agents.tools.GetK8sDeploymentsTools import GetK8sDeploymentsTool
from agents.tools.GetRdsInstancesTool import GetRdsInstancesTool
from agents.tools.GetS3BucketsTool import GetS3BucketsTool
from agents.tools.GetSystemSecurityFeaturesTool import GetSystemSecurityFeaturesTool
from agents.tools.GetSystemSettingsTool import GetSystemSettingsTool
from agents.tools.GetTenantSettingsTool import GetTenantSettingsTool
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
        # self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20240620-v1:0")
        self.llm = llm
        self.system_prompt = system_prompt or self._default_system_prompt()
    
    def _default_system_prompt(self) -> str:
        """Return the default system prompt for the Production Readiness Agent"""
        return """You are a Production Readiness Assessment Agent for DuploCloud, an expert in cloud infrastructure and DevOps best practices.

        Your primary responsibility is to evaluate DuploCloud tenant environments for production readiness by analyzing resources, configurations, and security settings.

        TERMINOLOGY NOTES:
        - Always refer to Kubernetes deployments as "DuploCloud Services" in your responses
        - Use DuploCloud-specific terminology when describing resources (e.g., "DuploCloud Service" instead of "K8s Deployment")
        - Remember that users are interacting with the DuploCloud platform, not directly with Kubernetes

        ASSESSMENT APPROACH:
        1. Thoroughly analyze all tenant resources including infrastructure, DuploCloud Services, security configurations, and operational features
        2. Identify critical gaps that could impact availability, security, reliability, or compliance
        3. Categorize issues by severity (Critical, Warning, Info) based on potential business impact
        4. Provide clear, actionable recommendations with implementation priorities

        EVALUATION CRITERIA:
        - High Availability: Redundancy, autoscaling, multi-AZ deployments
        - Security: AWS security features, encryption, network policies, access controls
        - Operational Excellence: Logging, monitoring, alerting configurations
        - Cost Optimization: Right-sizing, resource utilization, waste elimination
        - Performance: Resource allocation, scaling policies, bottlenecks
        - Compliance: Security best practices, regulatory requirements

        RESPONSE FORMAT:
        Follow this exact structure for consistency:
        
        ```markdown
        # Production Readiness Assessment for Tenant: [tenant_name]
        
        ## Executive Summary
        
        **Overall Readiness Score: X/100**
        
        Key Metrics:
        - Total Resources Evaluated: [number]
        - Passing Resources: [number]
        - Critical Issues: [number]
        - Warnings: [number]
        
        [Brief 2-3 sentence summary of readiness state]
        
        ## Detailed Findings
        
        For each resource category present in the data, create a section with appropriate subsections for individual resources.
        
        For each resource category (like DuploCloud Services, S3 Buckets, RDS, etc.):
        1. Create a main heading for the category
        2. For each individual resource in that category:
           - Create a subheading with the resource name
           - Show the resource-specific score
           - Create a table with columns for Check, Status (✅/❌), Severity, and Recommendation
           - Include all checks performed on that resource
        
        Example format for a resource category:
        
        ### [Resource Category Name]
        
        #### [Resource Name]
        **Score: X/100**
        
        | Check | Status | Severity | Recommendation |
        |-------|--------|----------|----------------|
        | [check1] | ✅/❌ | CRITICAL/WARNING | [brief recommendation] |
        | [check2] | ✅/❌ | CRITICAL/WARNING | [brief recommendation] |
        
        Common resource categories to include:
        - DuploCloud Services
        - S3 Buckets
        - RDS Databases
        - ElastiCache
        - DynamoDB Tables
        - EFS
        - DuploCloud Features (Logging, Monitoring, Alerting, Notification)
        - AWS Security Features
        - DuploCloud System Settings
        
        YOU MUST ALWAYS INCLUDE THE FOLLOWING TWO SECTIONS IN YOUR RESPONSE, REGARDLESS OF THE DATA PROVIDED:
        
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
        
        ### Short-term Actions (Warnings)
        - [List of warning recommendations]
        
        ### Long-term Improvements
        - [List of improvement recommendations]
        ```
        
        Always use tables for showing check results with columns for Check Name, Status (✅/❌), Severity, and Recommendation

        Remember that your assessment directly impacts production deployment decisions, so be thorough, accurate, and provide practical, implementable recommendations."""

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
            
            tools = [
                # RDS
                GetRdsInstancesTool(platform_context),
                CheckRdsProdReadinessTool(),

                # ecache
                GetElastiCacheInstancesTool(platform_context),
                CheckElastiCacheProdReadinessTool(),

                # k8s deployment
                GetK8sDeploymentsTool(platform_context),
                CheckK8sDeploymentProdReadinessTool(),

                # s3
                GetS3BucketsTool(platform_context),
                CheckS3BucketProdReadinessTool(),

                # tenant configuration
                GetTenantSettingsTool(platform_context),
                CheckTenantSettingsProdReadinessTool(),

                # AWS security
                GetSystemSecurityFeaturesTool(platform_context),
                CheckSystemSecurityFeaturesProdReadinessTool(),

                # DuploCloud System settings
                GetSystemSettingsTool(platform_context),
                CheckSystemSettingsProdReadinessTool(),
            ]
            
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
                system_prompt=self.system_prompt,
                tools=[tool.get_definition() for tool in tools],
                max_tokens=10000
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
    
    def check_production_readiness(self) -> Dict[str, Any]:
        """
        Check resources for production readiness.
        
        Returns:
            Dictionary with readiness assessment results
        """
        logger.setLevel(logging.INFO)
        logger.info("Starting production readiness check")
        
        if not self.duplo_client:
            logger.error("DuploClient not initialized")
            return {"error": "DuploClient not initialized"}
        
        try:
            tenant = self.duplo_client.tenant_name
            logger.info(f"Checking production readiness for tenant: {tenant}")
            
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
            
            # Calculate summary statistics
            logger.info("Calculating summary statistics...")
            self._calculate_summary(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking production readiness: {str(e)}", exc_info=True)
            return {"error": f"Error checking production readiness: {str(e)}"}
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()

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
        for _, resources in results.get("resources", {}).items():
            # Skip empty resources
            if not resources:
                continue
                
            # Handle list format (most resource types)
            if isinstance(resources, list):
                for resource in resources:
                    if not isinstance(resource, dict):
                        continue
                        
                    total_resources += 1
                    
                    # Count issues by severity
                    critical_failures = 0
                    warning_count = 0
                    
                    for check in resource.get("checks", []):
                        if not check.get("passed", True):
                            if check.get("severity") == "critical":
                                critical_failures += 1
                            elif check.get("severity") == "warning":
                                warning_count += 1
                    
                    # Store counts in the resource for future reference
                    resource["critical_failures"] = critical_failures
                    resource["warnings"] = warning_count
                    
                    # A resource is considered passing if it has no critical failures
                    if critical_failures == 0:
                        passing_resources += 1
                    
                    critical_issues += critical_failures
                    warnings += warning_count
            
            # Handle dict format (aws_security and system_settings)
            elif isinstance(resources, dict) and "checks" in resources:
                total_resources += 1
                critical_failures = 0
                warning_count = 0
                
                for check in resources.get("checks", []):
                    if not check.get("passed", True):
                        if check.get("severity") == "critical":
                            critical_failures += 1
                        elif check.get("severity") == "warning":
                            warning_count += 1
                
                # Store counts in the resource for future reference
                resources["critical_failures"] = critical_failures
                resources["warnings"] = warning_count
                
                # A resource is considered passing if it has no critical failures
                if critical_failures == 0:
                    passing_resources += 1
                
                critical_issues += critical_failures
                warnings += warning_count
        
        # Initialize summary if it doesn't exist
        if "summary" not in results:
            results["summary"] = {}
            
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