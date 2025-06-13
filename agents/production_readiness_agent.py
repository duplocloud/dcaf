import logging
import json
from typing import List, Dict, Any, Optional, Tuple
import os
import time
import re
from datetime import datetime

from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Data, Command, ExecutedCommand
from services.llm import BedrockAnthropicLLM
from services.duplo_client import DuploClient

# Import the modular components
from agents.production_readiness.integration import ProductionReadinessAgentBridge

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
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20240620-v1:0")
        self.llm = llm
        self.system_prompt = system_prompt
        self.response_schema = self._create_response_schema()
        self.current_messages = None
        self.duplo_client = None
        
        # Initialize the bridge to the modular agent
        self.agent_bridge = ProductionReadinessAgentBridge(llm, system_prompt)
    
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
            # Store current messages for use in other methods
            self.current_messages = messages
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

            # First LLM call to determine if production readiness check is needed
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
                
                # Extract tenant from platform context
                tenant = platform_context.get("tenant") if platform_context else "unknown"
                
                # Check resources for production readiness using the modular agent
                results = self.agent_bridge.check_production_readiness(tenant, self.duplo_client)
                
                # Calculate summary statistics
                self._calculate_summary(results)
                
                # Add the assessment results to the messages
                processed_messages.append({
                    "role": "user",
                    "content": f"Here are the production readiness assessment results for tenant {results['tenant']}:\n\n{json.dumps(results, indent=2)}"
                })
                
                # Get tenant-specific system prompt
                tenant = platform_context.get("tenant") if platform_context else "unknown"
                tenant_system_prompt = self.agent_bridge.generate_system_prompt(tenant)
                
                # Second LLM call with assessment results
                logger.info("Making second LLM call with assessment results")
                final_response = self.llm.invoke(
                    messages=processed_messages, 
                    model_id=self.model_id, 
                    system_prompt=tenant_system_prompt,
                    max_tokens=20000, 
                    tools=[self.response_schema],
                    tool_choice=tool_choice
                )
                
                logger.info("Using system prompt from SystemPromptHandler for tenant: %s", tenant)
                
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
        
    def _extract_remediation_actions(self, content: str) -> List[Dict[str, str]]:
        """
        Extract remediation actions from LLM response.
        
        Args:
            content: LLM response content
            
        Returns:
            List of remediation actions
        """
        # Use the modular agent bridge to extract remediation actions
        action_strings = self.agent_bridge.extract_remediation_actions(content)
        
        # Convert to the format expected by the original agent
        actions = []
        for action_string in action_strings:
            # Find explanation before or after the action in the content
            explanation = ""
            explanation_pattern = rf"(?:(?<=\n)|^)(?:#|//|\*)\s*(.*{re.escape(action_string)}.*?)(?=\n|$)"
            explanation_matches = re.findall(explanation_pattern, content, re.MULTILINE)
            if explanation_matches:
                explanation = explanation_matches[0].strip()
                
            actions.append({
                "action": action_string,
                "explanation": explanation or f"Execute {action_string}"
            })
        
        return actions
        
    def _execute_remediation_action(self, action: str) -> Dict[str, Any]:
        """
        Execute a remediation action using the DuploClient.
        
        Args:
            action: Action to execute
            
        Returns:
            Result of the action execution
        """
        logger.info(f"Executing remediation action: {action}")
        
        # Extract tenant from platform context
        platform_context = None
        for message in self.current_messages.get("messages", []):
            if message.get("role") == "user" and message.get("platform_context"):
                platform_context = message.get("platform_context")
                break
                
        tenant = platform_context.get("tenant") if platform_context else "unknown"
        
        # Use the modular agent bridge to execute the remediation
        try:
            return self.agent_bridge.execute_remediation(tenant, action, self.duplo_client, approved=True)
        except Exception as e:
            logger.error(f"Error executing remediation action: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Error executing action: {str(e)}"}
            
    # All remediation and resource check methods are now handled by the modular agent bridge

    def check_production_readiness(self) -> Dict[str, Any]:
        """
        Check resources for production readiness.
        
        Returns:
            Dictionary with production readiness check results
        """
        if not self.duplo_client:
            return {"error": "DuploClient not initialized"}
        tenant = self.duplo_client.get_tenant()
        if not tenant:
            return {"error": "Tenant not found"}
            
        logger.info(f"Checking production readiness for tenant: {tenant}")
        
        # Delegate to the modular agent bridge
        return self.agent_bridge.check_production_readiness(tenant, self.duplo_client)
    
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
        # This method is now handled by the modular agent bridge
        logger.info(f"Delegating resource check to modular agent bridge for tenant {tenant}")
        return self.agent_bridge.check_resources(tenant, resources, checks)
    


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