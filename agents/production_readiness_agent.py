import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Data, Command, ExecutedCommand
from services.llm import BedrockAnthropicLLM
from services.duplo_client import DuploClient
import os
import json
import requests
from datetime import datetime

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
        # self.model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
        self.llm = llm
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.response_schema = self._create_response_schema()
    
    def _create_response_schema(self) -> Dict[str, Any]:
        """
        Create the JSON schema for structured LLM responses.
        
        Returns:
            The response schema as a dictionary
        """
        return {
            "name": "return_assessment",
            "description": "Generate a structured production readiness assessment with remediation actions",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user. Should provide a clear explanation."
                    },
                    "check_prod_readiness": {
                        "type": "boolean",
                        "description": "Set this to true if the user asks to check production readiness. This triggers a check of the DuploCloud tenant's production readiness and determines whether to invoke the production readiness tool or function for a tenant, returning the assessment details to the agent."
                    },
                    "remediation_actions": {
                        "type": "array",
                        "description": "Specify remediation actions to address issues. If check_prod_readiness is true, provide each action in the format action_type:parameters. If check_prod_readiness is false, this field should be empty.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "description": "The remediation action in format action_type:parameters"
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "A brief explanation of what this action does."
                                },
                            },
                            "required": ["action", "explanation"]
                        }
                    }
                },
                "required": ["content"]
            }
        }

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
        2. Show a category-level score
        3. For each resource in that category, create a subsection with:
           - Resource name as a subheading
           - Table with columns: Check, Status (✅/❌), Severity, Recommendation
        
        Example structure:
        
        ### DuploCloud Services
        **Score: X/100**
        
        #### Service: my-api-service
        
        | Check | Status | Severity | Recommendation |
        |-------|--------|----------|----------------|
        | Replicas >= 2 | ✅/❌ | CRITICAL | [brief recommendation] |
        | Resource Limits | ✅/❌ | WARNING | [brief recommendation] |
        | Health Checks | ✅/❌ | WARNING | [brief recommendation] |
        
        #### Service: my-worker-service
        
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
        
        The user must explicitly type "APPROVE" to execute any of these remediation actions. Always explain what each action will do before suggesting it.
        ```        
        Always use tables for showing check results with columns for Check Name, Status (✅/❌), Severity, and Recommendation
        
        Remember that your assessment directly impacts production deployment decisions, so be thorough, accurate, and provide practical, implementable recommendations."""
    
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
            An AgentMessage containing the response, remediation actions, and executed actions
        """
        try:
            # Extract platform context from the first user message
            platform_context = None
            if messages and "messages" in messages and messages["messages"]:
                for message in messages["messages"]:
                    if message.get("role") == "user" and message.get("platform_context"):
                        platform_context = message.get("platform_context")
                        break
            
            # Initialize DuploClient with platform context
            self.duplo_client = self._initialize_duplo_client(platform_context)
            
            # Process messages to handle remediation actions and prepare for LLM
            processed_messages, executed_cmds = self._process_messages(messages)

            if not self.duplo_client:
                return AgentMessage(content="Unable to initialize DuploClient. Please provide valid credentials.")
            
            # Determine if this is a remediation-only request
            is_remediation_only = False
            if messages and "messages" in messages and messages["messages"]:
                latest_message = messages["messages"][-1]
                if latest_message.get("role") == "user":
                    content = latest_message.get("content", "").lower()
                    keywords = {"approve", "remediate", "fix", "execute", "remediation"}
                    if not content or any(keyword in content for keyword in keywords):
                        is_remediation_only = True
                        logger.info("Detected remediation-only request")
            
            logger.info("#### processed_messages:")
            logger.info(processed_messages)
            logger.info("#### executed_commands:")
            logger.info(executed_cmds)
            
            tool_choice = {
                "type": "tool",
                "name": "return_assessment"
            }
            initial_response = None
            # First LLM call to determine if production readiness check is needed
            if not is_remediation_only:
                logger.info("Making initial LLM call to determine if production readiness check is needed")
                initial_response = self.llm.invoke(
                    messages=processed_messages, 
                    model_id=self.model_id, 
                    system_prompt=self.system_prompt,
                    max_tokens=20000, 
                    tools=[self.response_schema],
                    tool_choice=tool_choice
                )
                logger.info("#### initial_response:")
                logger.info(initial_response)
            
            # Check if production readiness assessment is requested
            should_check_readiness = False
            if isinstance(initial_response, dict) and initial_response.get("check_prod_readiness") is True:
                should_check_readiness = True
                logger.info("LLM indicated production readiness check is needed")
            
            final_response = initial_response

            # Run production readiness check if needed and not in remediation-only mode
            if should_check_readiness or is_remediation_only:
                logger.info("Performing production readiness assessment")
                # Check resources for production readiness
                results = self.check_production_readiness()
                
                # Calculate summary statistics
                self._calculate_summary(results)
                
                # Add the assessment results to the messages
                processed_messages.append({
                    "role": "user",
                    "content": f"Here are the production readiness assessment results for tenant {results['tenant']}:\n\n{json.dumps(results, indent=2)}"
                })
                
                # Second LLM call with assessment results
                logger.info("Making second LLM call with assessment results")
                final_response = self.llm.invoke(
                    messages=processed_messages, 
                    model_id=self.model_id, 
                    system_prompt=self.system_prompt,
                    max_tokens=20000, 
                    tools=[self.response_schema],
                    tool_choice=tool_choice
                )
                
                logger.info("Final LLM response with assessment results:")
                logger.info(final_response)
                
                # Print the LLM response content in string format for easy copy-pasting
                if final_response and 'content' in final_response:
                    print("\n\n=== ASSESSMENT REPORT (MARKDOWN) ===\n")
                    print(final_response['content'])
                    print("\n=== END OF ASSESSMENT REPORT ===\n\n")
                
            # Extract remediation actions from LLM response
            remediation_actions = []
            if isinstance(final_response, dict) and "remediation_actions" in final_response:
                remediation_actions = final_response.get("remediation_actions", [])
            print("#### remediation_actions:")
            print(remediation_actions)
            cmds=[]
            for action in remediation_actions:
                cmds.append(Command(command=action["action"]))
            # Create and return the agent message with assessment results and remediation actions
            return AgentMessage(
                content=final_response.get("content", "I'm unable to provide a response at this time."),
                data=Data(
                    cmds=cmds,
                    executed_cmds=[ExecutedCommand(command=executed_cmd["command"], output=executed_cmd["output"]) 
                                  for executed_cmd in executed_cmds]
                )
            )
                
        except Exception as e:
            logger.error(f"Error in ProductionReadinessAgent.invoke: {str(e)}", exc_info=True)
            return AgentMessage(
                content=f"I encountered an error while assessing your resources: {str(e)}\n\nPlease try again or contact support if the issue persists."
            )
    
    def _process_messages(self, messages: Dict[str, List[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process messages to handle remediation actions and prepare for LLM.
        
        Args:
            messages: A dictionary containing message history
            
        Returns:
            Tuple of (processed_messages, executed_cmds)
        """
        logger.info("Processing messages...")
        print("#### Processing messages...")
        
        processed_messages = []
        executed_cmds = []
        
        # Extract messages list from the messages dictionary
        messages_list = messages.get("messages", [])
        
        # Process each message
        for message in messages_list:
            # Skip platform_context and other metadata
            if not message.get("content") or message.get("role") not in ["user", "assistant"]:
                continue

            processed_msg = {"role": message.get("role"), "content": message.get("content", "")}

            if message.get("role") == "user":
                data = message.get("data", {})

                # Check for approved remediation actions
                if "cmds" in data and message == messages_list[-1]:  # Only check the most recent message
                    for cmd in data["cmds"]:
                        if cmd.get("execute", False):
                            print("#### Executing approved command:", cmd)
                            logger.info(f"Executing approved command: {cmd['command']}")
                            # Execute the approved command
                            output = self._execute_remediation_action(cmd["command"])
                            # Track executed commands
                            executed_cmds.append({
                                "command": cmd["command"],
                                "output": output
                            })
                            
                            # Append command output to the message content
                            cmd_info = f"\n\nExecuted command: {cmd['command']}\nOutput: {output}"
                            processed_msg["content"] += cmd_info
                        else:
                            logger.info(f"Skipping command without execute flag: {cmd['command']}")

                # Include previously executed commands
                if "executed_cmds" in data and data["executed_cmds"]:
                    for cmd in data["executed_cmds"]:
                        executed_cmds.append(cmd)
                        cmd_info = f"\n\nPreviously executed: {cmd['command']}\nOutput: {cmd['output']}"
                        processed_msg["content"] += cmd_info

             # Add the processed message to the list
            processed_messages.append(processed_msg)
        
        return processed_messages, executed_cmds
        
    def _extract_remediation_actions(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract remediation actions from LLM response.
        
        Args:
            content: LLM response content
            
        Returns:
            List of remediation actions
        """
        actions = []
        
        # First try to extract from structured response
        if isinstance(content, dict) and "remediation_actions" in content:
            for action_item in content["remediation_actions"]:
                actions.append({
                    "action": action_item["action"],
                    "explanation": action_item.get("explanation", "")
                })
            return actions
    
        # Fallback to regex extraction from markdown code blocks
        action_pattern = r"```remediation\s*\n([\s\S]*?)\n```"
        matches = re.findall(action_pattern, content)
        
        for match in matches:
            action_lines = match.strip().split("\n")
            for line in action_lines:
                if line.strip():
                    actions.append({
                        "action": line.strip(),
                        "explanation": ""
                    })
        
        return actions
        
    def _execute_remediation_action(self, action: str) -> str:
        """
        Execute a remediation action using the DuploClient.
        
        Args:
            action: Action to execute
            
        Returns:
            Result of the action execution
        """
        logger.info(f"Executing remediation action: {action}")
        
        try:
            # Parse the action string
            parts = action.split(":", 1)
            if len(parts) != 2:
                return f"Invalid action format: {action}"
                
            action_type = parts[0].strip().lower()
            action_params = parts[1].strip()
            
            # Handle different action types
            if action_type == "enable_aws_security_feature":
                return self._enable_aws_security_feature(action_params)
            elif action_type == "update_duplo_system_setting":
                return self._update_duplo_system_setting(action_params)
            elif action_type == "enable_duplo_monitoring":
                return self._enable_duplo_monitoring(action_params)
            elif action_type == "enable_duplo_logging":
                return self._enable_duplo_logging(action_params)
            elif action_type == "enable_fault_notification_channel":
                return self._enable_fault_notification_channel(action_params)
            elif action_type == "enable_duplo_alerting":
                return self._enable_duplo_alerting(action_params)    
            elif action_type == "update_duplo_service":
                return self._update_duplo_service(action_params)
            else:
                return f"Unknown action type: {action_type}"
        except Exception as e:
            logger.error(f"Error executing remediation action: {str(e)}", exc_info=True)
            return f"Error executing action: {str(e)}"
            
    def _enable_aws_security_feature(self, params: str) -> str:
        """
        Enable an AWS security feature using the AWS account security features API.
        
        Args:
            params: Parameters for enabling the security feature (format: "feature_name:true/false")
            
        Returns:
            Result of the action
        """
        # Parse parameters (format: "feature_name:true/false")
        try:
            parts = params.split(":", 1)
            if len(parts) == 1:
                feature_name = parts[0].strip().lower()
                enable = True  # Default to enabling if no value specified
            else:
                feature_name, value_str = parts
                feature_name = feature_name.strip().lower()
                value_str = value_str.strip().lower()
                enable = value_str == "true"
        except ValueError:
            return f"Invalid security feature format: {params}"
        
        # Map feature names to API parameters
        feature_map = {
            "vpc_flow_logs": "EnableVpcFlowLogs",
            "security_hub": "EnableSecurityHub",
            "guardduty": "EnableGuardDuty",
            "cloudtrail": "EnableCloudTrail",
            "s3_public_access_block": "EnableGlobalS3PublicAccessBlock",
            "inspector": "EnableInspector",
            "password_policy": "EnablePasswordPolicy",
            "delete_default_vpcs": "DeleteDefaultVpcs",
            "revoke_default_sg_rules": "RevokeDefaultSgRules",
            "delete_default_nacl_rules": "DeleteDefaultNaclRules"
        }
        
        # Check if feature is supported
        if feature_name not in feature_map:
            return f"Unsupported security feature: {feature_name}"
        
        api_param = feature_map[feature_name]
        
        try:
            # Get current AWS security settings
            current_settings = self.duplo_client.get("/v3/admin/systemSettings/awsAccountSecurity")
            if not current_settings:
                current_settings = {}
            features = current_settings.get("Features", {})
            # Update the specific feature
            features[api_param] = enable
            
            # Call the API to update AWS account security features
            logger.info(f"Updating AWS security feature {feature_name} to {enable}")
            logger.debug(f"Request body: {features}")
            
            self.duplo_client.post("/v3/admin/systemSettings/awsAccountSecurityFeatures", features)
            logger.info(f"Successfully {'enabled' if enable else 'disabled'} {feature_name}")
            
            return f"Successfully {'enabled' if enable else 'disabled'} {feature_name}"
        except Exception as e:
            logger.error(f"Failed to update security feature {feature_name}: {str(e)}", exc_info=True)
            return f"Failed to {'enable' if enable else 'disable'} {feature_name}: {str(e)}"
            
    def _update_duplo_system_setting(self, params: str) -> str:
        """
        Update a DuploCloud system setting.
        
        Args:
            params: Parameters for updating the system setting
            
        Returns:
            Result of the action
        """
        print("#### Updating DuploCloud system setting:", params)
        logger.info(f"Updating DuploCloud system setting: {params}")
        # Parse parameters (format: "setting_name=value")
        try:
            setting_name, value = params.split("=", 1)
            setting_name = setting_name.strip()
            value = value.strip()
        except ValueError:
            return f"Invalid system setting format: {params}"
        
        # Map setting names to API keys
        setting_map = {
            "user_token_expiration": "EnableUserTokenExpirationNotification",
            "token_expiration_notification_email": "UserTokenExpirationNotificationEmails"
        }
        
        # Check if setting is supported
        if setting_name.lower() not in setting_map:
            return f"Unsupported system setting: {setting_name}"
        
        # Prepare request body
        key = setting_map[setting_name.lower()]
        request_body = {
            "Type": "AppConfig",
            "Key": key,
            "Value": value
        }
        
        
        # Direct API call fallback
        try:
            # Use the POST endpoint as specified in the API
            logger.debug(f"Request body: {request_body}")
            result = self.duplo_client.post("/v3/admin/systemSettings/config", request_body)
            logger.info(f"Response: {result}")
            logger.info(f"Successfully updated {setting_name} to {value}")
            return f"Successfully updated {setting_name} to {value}"
        except Exception as e:
            logger.error(f"Failed to update {setting_name}: {str(e)}", exc_info=True)
            return f"Failed to update {setting_name}: {str(e)}"
            
    def _enable_duplo_monitoring(self, params: str) -> str:
        """
        Enable monitoring for a tenant.
        
        Args:
            params: Parameters for enabling monitoring
            
        Returns:
            Result of the action
        """
        # Parse parameters if needed
        monitoring_type = params.strip()
        
        # Call the API
        try:
            # This is a placeholder - you'll need to implement the actual API calls
            result = self.duplo_client.post("v3/admin/tenant/monitoring/enable", {"Type": monitoring_type})
            return f"Successfully enabled {monitoring_type} monitoring"
        except Exception as e:
            return f"Failed to enable monitoring: {str(e)}"
            
    def _enable_duplo_logging(self, params: str) -> str:
        """
        Enable logging for a tenant.
        
        Args:
            params: Parameters for enabling logging
            
        Returns:
            Result of the action
        """
        # Parse parameters if needed
        logging_type = params.strip()
        
        # Call the API
        try:
            # This is a placeholder - you'll need to implement the actual API calls
            result = self.duplo_client.post("v3/admin/tenant/logging/enable", {"Type": logging_type})
            return f"Successfully enabled {logging_type} logging"
        except Exception as e:
            return f"Failed to enable logging: {str(e)}"

    def _enable_duplo_alerting(self, params: str) -> str:
        """
        Enable alerting for a tenant.
        
        Args:
            params: Parameters for enabling alerting
            
        Returns:
            Result of the action
        """
        # Check if this is the special case to enable all alerts using the base template
        if params.strip().lower() == "true":
            try:
                # Step 1: Get the alerts base template
                logger.info("Fetching alerts base template")
                alerts_template = self.duplo_client.get("admin/GetAlertsBaseTemplate")
                
                if not alerts_template:
                    return "Failed to fetch alerts base template: Empty response"
                    
                logger.info(f"Successfully fetched alerts base template with {len(alerts_template)} alerts")
                
                # Step 2: Update the tenant with the base template
                logger.info(f"Updating alerts template for tenant {self.duplo_client.tenant_id}")
                
                # Post the exact template to the update endpoint and handle the response directly
                # without trying to parse it as JSON
                url = self.duplo_client._build_url(f"admin/UpdateAlertsTemplateForTenant/{self.duplo_client.tenant_id}")
                headers = self.duplo_client._get_headers()
                
                logger.info(f"Making POST request to {url}")
                response = requests.post(url, headers=headers, json=alerts_template)
                response.raise_for_status()  # This will raise an exception for HTTP errors
                
                # Successfully updated the alerts template
                logger.info(f"Successfully updated alerts template for tenant {self.duplo_client.tenant_id}")
                return f"Successfully enabled alerting for tenant {self.duplo_client.tenant_id} using base template"
            except Exception as e:
                logger.error(f"Failed to enable alerting: {str(e)}", exc_info=True)
                return f"Failed to enable alerting: {str(e)}"
        

    def _enable_fault_notification_channel(self, params: str) -> str:
        """
        Enable fault notification channels for a tenant using the UpdateTenantMonConfig API.
        
        Args:
            params: Parameters for enabling notification channels (format: "channel_type=endpoint")
            
        Returns:
            Result of the action
        """
        # Parse parameters (format: "channel_type=endpoint")
        try:
            channel_type, endpoint = params.split("=", 1)
            channel_type = channel_type.strip().lower()
            endpoint = endpoint.strip()
        except ValueError:
            return f"Invalid notification channel format: {params}"
        
        # Map channel types to API parameters
        channel_map = {
            "pagerduty": "RoutingKey",
            "sentry": "Dsn",
            "newrelic": "NrApiKey",
            "opsgenie": "OpsGenieApiKey"
        }
        
        # Check if channel type is supported
        if channel_type not in channel_map:
            return f"Unsupported notification channel: {channel_type}"
        
        # Get current tenant monitoring configuration if available
        try:
            current_config = self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetTenantMonConfig")
        except Exception:
            # If we can't get the current config, start with an empty one
            current_config = {}
        
        # Set default alert publish frequency if not already set
        if "AlertPublishFrequency" not in current_config:
            current_config["AlertPublishFrequency"] = 90  # Default to 90 minutes
        
        # Update the specific channel
        api_param = channel_map[channel_type]
        current_config[api_param] = endpoint
        
        # Call the API
        try:
            logger.info(f"Configuring {channel_type} notification channel")
            logger.debug(f"Request body: {current_config}")
            
            self.duplo_client.post(f"subscriptions/{self.duplo_client.tenant_id}/UpdateTenantMonConfig", current_config)
            logger.info(f"Successfully configured {channel_type} notification channel")
            
            return f"Successfully configured {channel_type} notification channel"
        except Exception as e:
            logger.error(f"Failed to configure {channel_type} notification channel: {str(e)}", exc_info=True)
            return f"Failed to configure {channel_type} notification channel: {str(e)}"
        
    def _update_duplo_service(self, params: str) -> str:
        """
        Update a DuploCloud Service configuration.
        
        Args:
            params: Parameters for updating the service
            
        Returns:
            Result of the action
        """
        # Parse parameters (format: "service_name:setting=value")
        try:
            service_name, setting_str = params.split(":", 1)
            setting_name, value = setting_str.split("=", 1)
            service_name = service_name.strip()
            setting_name = setting_name.strip().lower()
            value = value.strip()
        except ValueError:
            return f"Invalid service update format: {params}"
        
        # Map setting names to API parameters
        setting_map = {
            "replicas": "Replicas",
            "cpu": "AllocatedCpu",
            "memory": "AllocatedMemoryMB",
            "health_check": "HealthCheckConfig"
        }
        
        # Check if setting is supported
        if setting_name not in setting_map:
            return f"Unsupported service setting: {setting_name}"
        
        # Get current service configuration
        try:
            service = self.duplo_client.get(f"v3/admin/tenant/replicationcontroller/{service_name}")
            if not service:
                return f"Service not found: {service_name}"
        except Exception as e:
            return f"Failed to get service {service_name}: {str(e)}"
        
        # Update the setting
        api_param = setting_map[setting_name]
        service[api_param] = value
        
        # Call the API to update the service
        try:
            # This is a placeholder - you'll need to implement the actual API calls
            result = self.duplo_client.put(f"v3/admin/tenant/replicationcontroller/{service_name}", service)
            return f"Successfully updated {service_name} {setting_name} to {value}"
        except Exception as e:
            return f"Failed to update service: {str(e)}"

    
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
            
            # Check different resource types
            # The resource types to check would be determined by what's available in your DuploClient
            logger.info("Getting resources to check...")
            resources = self._get_resources_to_check()
            logger.info(f"Found {len(resources)} resource types to check")
            for resource_type, resource_count in resources.items():
                if isinstance(resource_count, list):
                    logger.info(f"Resource type {resource_type}: {len(resource_count)} items")
                elif isinstance(resource_count, dict):
                    logger.info(f"Resource type {resource_type}: dictionary with {len(resource_count)} keys")
                else:
                    logger.info(f"Resource type {resource_type}: {type(resource_count)}")

            
            # Check RDS instances
            logger.info("Checking RDS instances...")
            if "rds" in resources and resources["rds"]:
                results["resources"]["rds"] = self._check_rds_instances(tenant, resources["rds"])
            else:
                results["resources"]["rds"] = []
                logger.info("No RDS instances found")
            
            # Check ecache clusters
            logger.info("Checking ecache clusters...")
            if "ecache" in resources and resources["ecache"]:
                results["resources"]["ecache"] = self._check_ecache_clusters(tenant, resources["ecache"])
            else:
                results["resources"]["ecache"] = []
                logger.info("No ecache clusters found")
            
            # Check K8s deployments
            logger.info("Checking K8s deployments...")
            if "k8s_deployments" in resources and resources["k8s_deployments"]:
                results["resources"]["k8s_deployments"] = self._check_k8s_deployments(tenant, resources["k8s_deployments"])
            else:
                results["resources"]["k8s_deployments"] = []
                logger.info("No K8s deployments found")
            
            # Check ASGs
            logger.info("Checking ASGs...")
            if "asgs" in resources and resources["asgs"]:
                results["resources"]["asgs"] = self._check_autoscaling_groups(tenant, resources["asgs"])
            else:
                results["resources"]["asgs"] = []
                logger.info("No ASGs found")
            
            # Check S3 buckets
            logger.info("Checking S3 buckets...")
            if "s3" in resources and resources["s3"]:
                results["resources"]["s3"] = self._check_s3_buckets(tenant, resources["s3"])
            else:
                results["resources"]["s3"] = []
                logger.info("No S3 buckets found")
            
            # Check Duplo tenant features
            logger.info("Checking Duplo tenant features...")
            results["resources"]["duplo_features"] = self._check_duplo_features(tenant, resources)
            
            # Check AWS security features
            logger.info("Checking AWS security features...")
            results["resources"]["aws_security"] = self._check_aws_security(tenant, resources)
            
            # Check system settings
            logger.info("Checking system settings...")
            results["resources"]["system_settings"] = self._check_system_settings(tenant, resources)
            
            # Calculate summary statistics
            logger.info("Calculating summary statistics...")
            self._calculate_summary(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking production readiness: {str(e)}", exc_info=True)
            return {"error": f"Error checking production readiness: {str(e)}"}
    
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
    
    def _get_resources_to_check(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get resources to check from DuploCloud.
        
        Returns:
            Dictionary with resource types and their instances
        """
        # Fetch all resources from DuploCloud
        raw_resources = {
            "rds": self.duplo_client.official_client.load("rds").list(),
            "ecache": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetEcacheInstances"),
            "k8s_deployments": self.duplo_client.official_client.load("service").list(),
            "s3": self.duplo_client.official_client.load("s3").list(),
            "asgs": self.duplo_client.official_client.load("asg").list(),
            "duplo_logging": self.duplo_client.get(f"admin/GetLoggingEnabledTenants"),
            "duplo_monitoring": self.duplo_client.get(f"admin/GetMonitoringConfigForTenant/default"),
            "duplo_alerting": self.duplo_client.get(f"v3/admin/tenant/{self.duplo_client.tenant_id}/metadata/enable_alerting"),
            "duplo_notification": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetTenantMonConfig"),
            "aws_security": self.duplo_client.get(f"v3/admin/systemSettings/awsAccountSecurity"),
            "system_settings": self.duplo_client.get(f"v3/admin/systemSettings/config"),
        }
        
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
        for resource_type, resources_list in raw_resources.items():
            prefixes = exclude_prefixes.get(resource_type, [])
            filtered_resources[resource_type] = self._filter_resources(resources_list, prefixes)
        
        return filtered_resources
    
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
    
    def _check_rds_instances(self, tenant: str, instances: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check RDS instances for production readiness"""
        
        # Define checks for RDS instances
        rds_checks = [
            {
                'name': 'encryption',
                'attribute_path': ['EncryptStorage'],
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
                'condition': lambda val: (val >= 0 if isinstance(val, (int, float)) else False,
                                         f"Backup retention period is {val} days" if isinstance(val, (int, float)) else
                                         "Backup retention period not set"),
                'severity': 'critical',
                'recommendation': "Set backup retention period to at least 7 days"
            },
            {
                'name': 'deletion_protection',
                'attribute_path': ['DeletionProtection'],
                'condition': lambda val: (val is True, 
                                         "Deletion protection is enabled" if val is True else 
                                         "Deletion protection is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable deletion protection to prevent accidental deletion"
            },
            {
                'name': 'logging',
                'attribute_path': ['EnableLogging'],
                'condition': lambda val: (val is True, 
                                         "Logging is enabled" if val is True else 
                                         "Logging is not enabled"),
                'severity': 'warning',
                'recommendation': "Enabling logging is crucial for observability, performance tuning, security auditing, and troubleshooting"
            },
            {
                'name': 'performance_insights',
                'attribute_path': ['EnablePerformanceInsights'],
                'condition': lambda val: (val is True, 
                                         "Performance insights is enabled" if val is True else 
                                         "Performance insights is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable performance insights for better database performance over time"
            }
        ]
        
        return self._generic_resource_check(tenant, instances, rds_checks)
    
    def _check_ecache_clusters(self, tenant: str, clusters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check ecache clusters for production readiness"""
        
        # Define checks for ecache clusters
        ecache_checks = [
            {
                'name': 'encryption_at_rest',
                'attribute_path': ['EnableEncryptionAtRest'],
                'condition': lambda val: (val is True, 
                                         "Encryption at rest is enabled" if val is True else 
                                         "Encryption at rest is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable encryption at rest for data protection"
            },
            {
                'name': 'encryption_at_transit',
                'attribute_path': ['EnableEncryptionAtTransit'],
                'condition': lambda val: (val is True, 
                                         "Encryption at transit is enabled" if val is True else 
                                         "Encryption at transit is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable encryption at transit for data protection"
            },
            {
                'name': 'multi_az',
                'attribute_path': ['MultiAZEnabled'],
                'condition': lambda val: (val is True, 
                                         "Multi-AZ deployment is enabled" if val is True else 
                                         "Multi-AZ deployment is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Multi-AZ deployment for high availability"
            },
            {
                'name': 'automatic_failover',
                'attribute_path': ['AutomaticFailoverEnabled'],
                'condition': lambda val: (val is True, 
                                         "Automatic failover is enabled" if val is True else 
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
                'name': 'hpa_configured',
                'attribute_path': ['HPASpecs'],
                'condition': lambda val: (
                    val is not None,
                    "HPA is configured" if val is not None else "HPA is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure Horizontal Pod Autoscaler (HPA) for automatic scaling"
            },
            {
                'name': 'hpa_min_replicas',
                'attribute_path': ['HPASpecs', 'minReplicas'],
                'condition': lambda val: (
                    isinstance(val, (int, float)) and val >= 2,
                    f"HPA minimum replicas is {val}" if isinstance(val, (int, float)) else "HPA minimum replicas not determined"
                ),
                'severity': 'critical',
                'recommendation': "Configure HPA with at least 2 minimum replicas for high availability"
            },
            {
                'name': 'hpa_metrics_configured',
                'attribute_path': ['HPASpecs', 'metrics'],
                'condition': lambda metrics: (
                    isinstance(metrics, list) and len(metrics) > 0,
                    f"HPA has {len(metrics)} metrics configured" if isinstance(metrics, list) else "HPA metrics not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure HPA with appropriate metrics (CPU/memory)"
            },
            {
                'name': 'resource_limits',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"Resources"' in config and '"limits"' in config,
                    "Resource limits are configured" if isinstance(config, str) and '"Resources"' in config and '"limits"' in config else
                    "Resource limits are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Set resource limits for all containers"
            },
            {
                'name': 'resource_requests',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"Resources"' in config and '"requests"' in config,
                    "Resource requests are configured" if isinstance(config, str) and '"Resources"' in config and '"requests"' in config else
                    "Resource requests are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Set resource requests for all containers"
            },
            {
                'name': 'liveness_probe',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"LivenessProbe"' in config,
                    "Liveness probe is configured" if isinstance(config, str) and '"LivenessProbe"' in config else
                    "Liveness probe is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure liveness probe to ensure automatic restart of unhealthy containers"
            },
            {
                'name': 'readiness_probe',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"ReadinessProbe"' in config,
                    "Readiness probe is configured" if isinstance(config, str) and '"ReadinessProbe"' in config else
                    "Readiness probe is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure readiness probe to prevent routing traffic to containers that aren't ready"
            },
            {
                'name': 'rolling_update_strategy',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"DeploymentStrategy"' in config and '"RollingUpdate"' in config,
                    "Rolling update strategy is configured" if isinstance(config, str) and '"DeploymentStrategy"' in config and '"RollingUpdate"' in config else
                    "Rolling update strategy is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure rolling update strategy for zero-downtime deployments"
            }
        ]
        
        return self._generic_resource_check(tenant, deployments, k8s_checks)
    
    def _check_autoscaling_groups(self, tenant: str, asgs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check Auto Scaling Groups for production readiness"""
        
        if asgs is None or asgs == []:
            # Specific checks for when no ASGs are found
            asg_checks = [
                {
                    'name': 'asg_not_found',
                    'condition': lambda val: (False, "No Auto Scaling Groups found"),
                    'severity': 'critical',
                    'recommendation': "Configure Auto Scaling Groups for high availability and fault tolerance in production environments"
                }
            ]
        else:
            # Normal checks when ASGs are present
            asg_checks = [
                {
                'name': 'is_cluster_autoscaled',
                'attribute_path': ['IsClusterAutoscaled'],
                'condition': lambda val: (val is True, 
                                         "Cluster autoscaling is enabled" if val is True else 
                                         "Cluster autoscaling is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable cluster autoscaling for high availability"
                },
                {
                    'name': 'multiple_azs',
                    'attribute_path': ['Zones'],
                    'condition': lambda zones: (
                        isinstance(zones, list) and len(zones) >= 2,
                        f"ASG spans {len(zones)} availability zones" if isinstance(zones, list) and len(zones) >= 2 else
                        "ASG availability zones not determined"
                    ),
                    'severity': 'critical',
                    'recommendation': "Configure ASG to span at least 2 availability zones"
                }
            ]
        
        return self._generic_resource_check(tenant, asgs, asg_checks)

    def _check_s3_buckets(self, tenant: str, buckets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Check S3 Buckets for production readiness"""
        
        s3_checks = [
            {
                'name': 'encryption',
                'attribute_path': ['DefaultEncryption'],
                'condition': lambda val: (val is not None, 
                    "Server-side encryption is enabled" if val is not None else 
                    "Server-side encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable server-side encryption"
            },
            {
                'name': 'public_access_block',
                'attribute_path': ['AllowPublicAccess'],
                'condition': lambda val: (val is False,
                    "Block public access is enabled" if val is False else
                    "Block public access is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable block public access"
            },
            {
                'name': 'versioning',
                'attribute_path': ['EnableVersioning'],
                'condition': lambda val: (val is True, 
                    "Versioning is enabled" if val is True else 
                    "Versioning is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable versioning for data protection"
            },
            {
                'name': 'logging',
                'attribute_path': ['EnableAccessLogs'],
                'condition': lambda val: (val is True, 
                    "Logging is enabled" if val is True else 
                    "Logging is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable logging to track bucket access"
            },
        ]
    
        return self._generic_resource_check(tenant, buckets, s3_checks)
        
    def _check_aws_security(self, tenant: str, resources: Dict[str, Any]) -> Dict[str, Any]:
        """Check AWS security features for production readiness"""
        
        # Create a synthetic resource to represent AWS security features
        security_resource = {
            'identifier': f"aws-security",
            'Name': f"aws-security"
        }
        
        # Extract security features
        security_features = {}
        if "aws_security" in resources and resources["aws_security"] and isinstance(resources["aws_security"], dict):
            features = resources["aws_security"].get("Features", {})
            if features and isinstance(features, dict):
                security_features = features
        
        # Add security features to resource
        security_resource["EnableVpcFlowLogs"] = security_features.get("EnableVpcFlowLogs", False)
        security_resource["EnableSecurityHub"] = security_features.get("EnableSecurityHub", False)
        security_resource["EnableGuardDuty"] = security_features.get("EnableGuardDuty", False)
        security_resource["EnableCloudTrail"] = security_features.get("EnableCloudTrail", False)
        security_resource["EnablePasswordPolicy"] = security_features.get("EnablePasswordPolicy", False)
        security_resource["EnableGlobalS3PublicAccessBlock"] = security_features.get("EnableGlobalS3PublicAccessBlock", False)
        security_resource["EnableInspector"] = security_features.get("EnableInspector", False)
        security_resource["EnableCisCloudTrailCloudWatchAlarms"] = security_features.get("EnableCisCloudTrailCloudWatchAlarms", False)
        security_resource["EnableAllSecurityHubRegions"] = security_features.get("EnableAllSecurityHubRegions", False)
        security_resource["EnableAllInspectorRegions"] = security_features.get("EnableAllInspectorRegions", False)
        security_resource["DeleteDefaultVpcs"] = security_features.get("DeleteDefaultVpcs", False)
        security_resource["RevokeDefaultSgRules"] = security_features.get("RevokeDefaultSgRules", False)
        
        # Define checks for AWS security features
        security_checks = [
            {
                'name': 'vpc_flow_logs',
                'attribute_path': ['EnableVpcFlowLogs'],
                'condition': lambda val: (val is True,
                                        "VPC Flow Logs are enabled" if val is True else "VPC Flow Logs are not enabled"),
                'severity': 'critical',
                'recommendation': "Enable VPC Flow Logs to monitor network traffic for security analysis and troubleshooting"
            },
            {
                'name': 'security_hub',
                'attribute_path': ['EnableSecurityHub'],
                'condition': lambda val: (val is True,
                                        "AWS Security Hub is enabled" if val is True else "AWS Security Hub is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS Security Hub for comprehensive security compliance monitoring"
            },
            {
                'name': 'guard_duty',
                'attribute_path': ['EnableGuardDuty'],
                'condition': lambda val: (val is True,
                                        "AWS GuardDuty is enabled" if val is True else "AWS GuardDuty is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS GuardDuty for threat detection and continuous security monitoring"
            },
            {
                'name': 'cloud_trail',
                'attribute_path': ['EnableCloudTrail'],
                'condition': lambda val: (val is True,
                                        "AWS CloudTrail is enabled" if val is True else "AWS CloudTrail is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable AWS CloudTrail for comprehensive API activity tracking and auditing"
            },
            {
                'name': 'password_policy',
                'attribute_path': ['EnablePasswordPolicy'],
                'condition': lambda val: (val is True,
                                        "AWS Password Policy is enabled" if val is True else "AWS Password Policy is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable AWS Password Policy to enforce strong password requirements"
            },
            {
                'name': 's3_public_access_block',
                'attribute_path': ['EnableGlobalS3PublicAccessBlock'],
                'condition': lambda val: (val is True,
                                        "Global S3 Public Access Block is enabled" if val is True else "Global S3 Public Access Block is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Global S3 Public Access Block to prevent accidental public exposure of S3 buckets"
            },
            {
                'name': 'inspector',
                'attribute_path': ['EnableInspector'],
                'condition': lambda val: (val is True,
                                        "AWS Inspector is enabled" if val is True else "AWS Inspector is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable AWS Inspector for automated security assessment and vulnerability identification"
            },
            {
                'name': 'cis_cloudtrail_cloudwatch_alarms',
                'attribute_path': ['EnableCisCloudTrailCloudWatchAlarms'],
                'condition': lambda val: (val is True,
                                        "CIS CloudTrail CloudWatch Alarms are enabled" if val is True else "CIS CloudTrail CloudWatch Alarms are not enabled"),
                'severity': 'warning',
                'recommendation': "Enable CIS CloudTrail CloudWatch Alarms for monitoring and alerting on suspicious activities"
            },
            {
                'name': 'all_security_hub_regions',
                'attribute_path': ['EnableAllSecurityHubRegions'],
                'condition': lambda val: (val is True,
                                        "Security Hub is enabled in all regions" if val is True else "Security Hub is not enabled in all regions"),
                'severity': 'warning',
                'recommendation': "Enable Security Hub in all regions to ensure comprehensive security coverage"
            },
            {
                'name': 'all_inspector_regions',
                'attribute_path': ['EnableAllInspectorRegions'],
                'condition': lambda val: (val is True,
                                        "Inspector is enabled in all regions" if val is True else "Inspector is not enabled in all regions"),
                'severity': 'warning',
                'recommendation': "Enable Inspector in all regions to ensure comprehensive vulnerability assessment"
            },
            {
                'name': 'delete_default_vpcs',
                'attribute_path': ['DeleteDefaultVpcs'],
                'condition': lambda val: (val is True,
                                        "Default VPCs are deleted" if val is True else "Default VPCs are not deleted"),
                'severity': 'warning',
                'recommendation': "Delete default VPCs to reduce the attack surface and enforce explicit network configuration"
            },
            {
                'name': 'revoke_default_sg_rules',
                'attribute_path': ['RevokeDefaultSgRules'],
                'condition': lambda val: (val is True,
                                        "Default security group rules are revoked" if val is True else "Default security group rules are not revoked"),
                'severity': 'warning',
                'recommendation': "Revoke default security group rules to enforce explicit security group configuration"
            }
        ]
        
        # Use the generic resource check with a list containing just the security resource
        return self._generic_resource_check(tenant, [security_resource], security_checks)
    
    def _check_system_settings(self, tenant: str, resources: Dict[str, Any]) -> Dict[str, Any]:
        """Check DuploCloud system settings for production readiness"""
        
        # Create a synthetic resource to represent system settings
        system_resource = {
            'identifier': f"system-settings",
            'Name': f"system-settings"
        }
        
        # Extract system settings
        token_expiration_notification_enabled = False
        token_expiration_notification_days = 0
        token_expiration_notification_emails = ""
        
        if "system_settings" in resources and resources["system_settings"] and isinstance(resources["system_settings"], list):
            for setting in resources["system_settings"]:
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "EnableUserTokenExpirationNotification":
                    try:
                        days = int(setting.get("Value", "0"))
                        if days > 0:
                            token_expiration_notification_enabled = True
                            token_expiration_notification_days = days
                    except (ValueError, TypeError):
                        pass
                
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "UserTokenExpirationNotificationEmails":
                    token_expiration_notification_emails = setting.get("Value", "")
        
        # Add settings to resource
        system_resource["TokenExpirationNotificationEnabled"] = token_expiration_notification_enabled
        system_resource["TokenExpirationNotificationDays"] = token_expiration_notification_days
        system_resource["TokenExpirationNotificationEmails"] = token_expiration_notification_emails
        system_resource["HasTokenExpirationEmails"] = bool(token_expiration_notification_emails)
        
        # Define checks for system settings
        system_checks = [
            {
                'name': 'token_expiration_notification',
                'attribute_path': ['TokenExpirationNotificationEnabled'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"User token expiration notification is enabled ({resource.get('TokenExpirationNotificationDays', 0)} days)" if val is True 
                    else "User token expiration notification is not enabled"
                ),
                'severity': 'warning',
                'recommendation': "Enable user token expiration notification to alert users before their tokens expire"
            },
            {
                'name': 'token_expiration_emails',
                'attribute_path': ['HasTokenExpirationEmails'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"Token expiration notification emails are configured" if val is True 
                    else "Token expiration notification emails are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure token expiration notification emails to ensure notifications are delivered"
            }
        ]
        
        # Use the generic resource check with a list containing just the system resource
        return self._generic_resource_check(tenant, [system_resource], system_checks)
    
    def _check_duplo_features(self, tenant: str, resources: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check DuploCloud tenant-specific features for production readiness"""
        
        # Create a synthetic resource to represent the tenant features
        tenant_resource = {
            'identifier': f"{tenant}",
            'Name': f"{tenant}"
        }
        
        # Extract logging status
        logging_enabled = False
        if "duplo_logging" in resources and resources["duplo_logging"]:
            for tenant_logging in resources["duplo_logging"]:
                if tenant_logging.get("TenantId") == self.duplo_client.tenant_id and tenant_logging.get("Enabled") is True:
                    logging_enabled = True
                    break
        tenant_resource["LoggingEnabled"] = logging_enabled
        
        # Extract monitoring status
        monitoring_enabled = False
        if "duplo_monitoring" in resources and resources["duplo_monitoring"]:
            # Check if monitoring is enabled globally
            monitoring_data = resources["duplo_monitoring"]
            if isinstance(monitoring_data, dict):
                # First check global monitoring enabled flag
                if monitoring_data.get("Enabled") is True:
                    # Then check if this tenant is in the enabled tenants list
                    enabled_tenants = monitoring_data.get("EnabledTenants", [])
                    for tenant_info in enabled_tenants:
                        if tenant_info.get("TenantId") == self.duplo_client.tenant_id and tenant_info.get("Enabled") is True:
                            monitoring_enabled = True
                            break
        tenant_resource["MonitoringEnabled"] = monitoring_enabled
        
        # Extract alerting status
        alerting_enabled = False
        if "duplo_alerting" in resources and resources["duplo_alerting"]:
            alerting_data = resources["duplo_alerting"]
            if isinstance(alerting_data, dict) and alerting_data.get("Value", "").lower() == "true":
                alerting_enabled = True
            # Some API responses might have a different structure
            elif isinstance(alerting_data, dict) and alerting_data.get("Key") == "enable_alerting" and alerting_data.get("Value", "").lower() == "true":
                alerting_enabled = True
        tenant_resource["AlertingEnabled"] = alerting_enabled
        
        # Extract notification configuration status
        notification_configured = False
        notification_channel = "None"
        if "duplo_notification" in resources and resources["duplo_notification"]:
            notification_data = resources["duplo_notification"]
            if isinstance(notification_data, dict):
                # Check for different notification channels
                if notification_data.get("RoutingKey"):
                    notification_configured = True
                    notification_channel = "PagerDuty"
                elif notification_data.get("Dsn"):
                    notification_configured = True
                    notification_channel = "Sentry"
                elif notification_data.get("NrApiKey"):
                    notification_configured = True
                    notification_channel = "New Relic"
                elif notification_data.get("OpsGenieApiKey"):
                    notification_configured = True
                    notification_channel = "OpsGenie"
        tenant_resource["NotificationConfigured"] = notification_configured
        tenant_resource["NotificationChannel"] = notification_channel
        
        # Define checks for tenant features
        tenant_checks = [
            {
                'name': 'logging_enabled',
                'attribute_path': ['LoggingEnabled'],
                'condition': lambda val: (val is True,
                                         "Logging is enabled" if val is True else "Logging is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable logging for the tenant to ensure proper audit trails and troubleshooting capabilities"
            },
            {
                'name': 'monitoring_enabled',
                'attribute_path': ['MonitoringEnabled'],
                'condition': lambda val: (val is True,
                                         "Monitoring is enabled" if val is True else "Monitoring is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable monitoring for the tenant to track resource performance and health"
            },
            {
                'name': 'alerting_enabled',
                'attribute_path': ['AlertingEnabled'],
                'condition': lambda val: (val is True,
                                         "Alerting is enabled" if val is True else "Alerting is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable alerting to receive notifications for critical events and issues"
            },
            {
                'name': 'notification_configured',
                'attribute_path': ['NotificationConfigured'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"Alert notification is configured using {resource.get('NotificationChannel')}" if val is True and resource else "Alert notification is not configured"
                ),
                'severity': 'critical',
                'recommendation': "Configure alert notification channel (PagerDuty, Sentry, New Relic, or OpsGenie) to ensure timely response to critical alerts"
            }
        ]
        
        # Use the generic resource check with a list containing just the tenant resource
        return self._generic_resource_check(tenant, [tenant_resource], tenant_checks)

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