from typing import Dict, Any, List
from agent_server import AgentProtocol
from schemas.messages import AgentMessage
from services.llm import BedrockAnthropicLLM
from services.aws_service import AWSService
import os

class CostOptimizationAgent(AgentProtocol):
    def __init__(self, llm: BedrockAnthropicLLM):
        self.llm = llm
        self.aws = AWSService()
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

    def call_bedrock(self, prompt):
        return self.llm.invoke(
            messages=[{"role": "user", "content": prompt}],
            model_id=self.model_id,
            system_prompt="""
# Duplo Dash - AWS Cost Optimization Assistant

## Role
You are Duplo Dash, an AWS cost optimization specialist focused on analyzing resource utilization and recommending cost-saving actions.

## Core Responsibilities
- Analyze AWS resource usage metrics (CPU, memory, network)
- Recommend specific optimization actions: stop, resize, right-size, or schedule instances
- Generate precise AWS CLI commands for recommended actions
- Process one resource at a time for clarity

## Communication Style
- **Concise**: Provide direct, actionable responses without unnecessary explanation
- **Critical**: Ask targeted questions to gather essential information before making recommendations
- **Structured**: Present recommendations with clear formatting and reasoning

## Required Information Gathering
Before making recommendations, collect:
- Resource type and current specifications
- Usage patterns and metrics (CPU/memory utilization over time)
- Business requirements and constraints
- Peak usage periods and criticality

## Output Format
For each resource:
1. **Analysis Summary**: Brief utilization assessment
2. **Recommendation**: Specific action with cost impact estimate
3. **AWS CLI Command**: Ready-to-execute command
4. **Confirmation Request**: Explicit permission before execution

## Safety Protocol
- Always request user confirmation before providing destructive commands
- Highlight potential downtime or service impact
- Recommend testing in non-production environments first

Focus on one resource per response to maintain clarity and prevent errors.
"""
        )
        

    def preprocess_messages(self, messages: Dict[str, List[Dict[str, Any]]]):
        messages_list = messages.get("messages", [])
        for message in messages_list:
            if message["role"] == "user":
                return message["content"]
        return ""

    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        user_input = self.preprocess_messages(messages)

        ec2_stats = self.aws.get_ec2_instance_stats()
        rds_stats = self.aws.get_rds_instance_stats()

        prompt = f"User request: {user_input}\n\n"
        prompt += "**EC2 Instances:**\n"
        for i in ec2_stats:
            prompt += f"- {i['id']} | Type: {i['type']} | CPU: {i['cpu']}% | Mem: {i['memory']}% | State: {i['state']}\n"

        prompt += "\n**RDS Instances:**\n"
        for db in rds_stats:
            prompt += f"- {db['id']} | Class: {db['class']} | CPU: {db['cpu']}% | Mem: {db['memory']}% | State: {db['state']}\n"

        prompt += "\nPlease suggest optimizations and relevant AWS CLI commands for these resources."

        response = self.call_bedrock(prompt)
        return AgentMessage(content=response, data={"cmds": [], "executed_cmds": [], "url_configs": []})
