# Service Desk Agents

A flexible, protocol-based service desk agent framework built with FastAPI that enables various agent implementations to respond to user chat messages.

## Overview

This project provides a modular framework for creating, testing and deploying agents that can integrate with DuploCloud Service Desk and can:

- Process chat messages from users
- Integrate with AWS Bedrock for LLM capabilities (especially Anthropic Claude models)
- Provide a standardized message schema for communication
- Include a mock UI for testing interactions

## Project Structure

```
├── agent_server.py         # FastAPI server and agent protocol definition
├── agents/                 # Agent implementations
│   ├── boilerplate_agent.py # Minimal starter boilerplate agent
│   ├── cmd_agent.py        # Command-execution agent implementation
│   ├── echo_agent.py       # Simple echo agent implementation
│   └── llm_passthrough_agent.py # Agent that passes through to LLM
├── main.py                 # Application entry point
├── schemas/                # Pydantic data models
│   └── messages.py         # Message schema definitions
├── services/               # Service implementations
│   └── llm.py              # AWS Bedrock LLM integration
└── service_desk_mock_ui.py # Mock UI for testing
```

## Getting Started

### Prerequisites

- Python 3.8+
- The application uses AWS Bedrock for LLM functionality. Configure your AWS credentials in the `.env` file (refer to env.example) or through standard AWS credential methods (environment variables, IAM roles, etc.) when running locally. Not required when deployed in DuploCloud.

### Installation

1. Clone the repository:

```bash
git clone https://github.com/duplocloud/service-desk-agents.git
cd service-desk-agents
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Copy the environment example file and configure it:

```bash
cp env.example .env
```

Edit the `.env` file with your AWS credentials and other configuration values.

### AWS Credentials Setup

Use [`env_update_aws_creds.sh`](./env_update_aws_creds.sh) to fetch temporary AWS credentials via `duplo-jit`. It creates `.env` if not present, adds missing variables, and updates credentials. Uses default host (`https://duplo.hackathon.duploworkshop.com/`) and tenant (`agents`), overridable with `--host` and `--tenant` arguments.

Make executable and run:
```bash
chmod +x env_update_aws_creds.sh
./env_update_aws_creds.sh [--host=HOST_URL] [--tenant=TENANT_NAME]
```

### Running the Application

Start the server:

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --port 8000 --reload
```

### API Endpoints

- **Health Check**: `GET /health`
- **Send Message**: `POST /api/sendMessage`

### Testing the API

- Import the postman collection in the project root (service-desk-agent.postman_collection.json) into postman to try out the /health and /api/sendMessage endpoints

(or)

- Sample cURL for /api/sendMessage:
```
  curl --location 'http://localhost:8000/api/sendMessage' \
--header 'Content-Type: application/json' \
--data '{
 "messages" : [
    {
        "role" : "user",
        "content" : "Hi! What'\''s your name?"
    }
    ]   
}'

```

### Testing the Agent API using Service Desk Mock UI (Work in progress)

```bash
python service_desk_mock_ui.py
```

Note: This is a simple mock UI for testing interactions. Creates a UI that connects to the FastAPI server at `http://localhost:8000/api/sendMessage`. It does not mock all service desk features and only replciates the content and terminal command approval/rejection features. Future support will be added to mock all service desk features for local testing.

### Common Errors and Solutions:

- 404 while testing the /sendMessage API endpoint:
SolutionLTry to replace `0.0.0.0` in the url with `localhost` when making the API call

- `An error occurred (ExpiredTokenException) when calling the InvokeModel operation: The security token included in the request is expired`
Update the aws creds in the .env file (use the env_update_aws_creds.sh script to update it automatically using duplo jit)  

## Boilerplate Agents

The framework includes three boilerplate agent implementations that can be used as-is or as a foundation for custom agents:

### 1. EchoAgent

A simple agent that echoes back the user's last message.

- **Implementation**: `agents/echo_agent.py`
- **Functionality**: Extracts the last user message and returns it prefixed with "Echo: "
- **Use Case**: Useful for testing the messaging framework and verifying that communication is working properly


### 2. LLMPassthroughAgent

A simple agent that passes messages directly to an LLM and returns the response.

- **Implementation**: `agents/llm_passthrough_agent.py`
- **Functionality**: Preprocesses messages and sends them to AWS Bedrock Anthropic LLM, then returns the LLM's response
- **Use Case**: Useful for general conversational assistance without custom processing logic

### 3. CommandAgent

A more sophisticated agent that can process messages, execute terminal commands, and leverage LLM capabilities.

- **Implementation**: `agents/cmd_agent.py`
- **Functionality**:
  - Processes user messages and handles approved command execution
  - Uses AWS Bedrock Anthropic LLM to generate responses and suggest commands
  - Provides structured responses with explanations for suggested commands
  - Tracks and includes executed command outputs in responses
- **Use Case**: Ideal for providing CLI assistance, executing system operations, and helping users with terminal-based tasks

## Creating a New Agent

The easiest way to create a new agent is to modify the existing `BoilerplateAgent` in `agents/boilerplate_agent.py` which provides a minimal implementation of the `AgentProtocol` interface.

Alternatively, you can implement the `AgentProtocol` interface from scratch:

```python
from typing import Dict, Any, List
from agent_server import AgentProtocol
from schemas.messages import AgentMessage

class MyCustomAgent(AgentProtocol):
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        # Extract messages list from the dictionary
        messages_list = messages.get("messages", [])
        
        # Your agent logic here
        return AgentMessage(content="Your response")
```

After creating your agent, update `main.py` to use it by importing your agent class and updating the agent variable to point to your `agent` instance.

Sample starting point:

Update boilerplate_agent.py to create the following agents.

- Level 1: Refer to the llm_passthrough_agent.py and update the system prompt to give it your information so that it can answer questions about you.

- Level 2: Refer to the CMD boilerplate agent, and update it (the sytem prompt and the json schema descriptions) so that it runs only aws cli commands.

## LLM Snippet

We use AWS Bedrock in order to communicate with an LLM. 
You can try running these examples in services/llm.py 

This is the outline to make a call to given LLM using Bedrock:
```python
raw = client.invoke_model(
    modelId="anthropic.claude-3-5-sonnet-20240620-v1:0", # The given LLM ID
    body=json.dumps(request_body), # Passing in the request body to the API
)
# Parsing the body response from Bedrock 
response = json.loads(raw["body"].read())
```

Here are different request_bodys that we can send to the LLM:

1) One-shot prompt — minimal request / response:

The simplest call we can make to the API. In the input body to the API, we have to define three values
- messages, the list of message data from the user and assistant 
- max_tokens, the "size" of the LLM response (4*max_tokens is approximately the max number of characters)
- anthropic_version, the API-schema date string

Input:
```
request_body = {
  "messages": [
    { "role": "user", "content": "Hi" }
  ],
  "max_tokens": 100,
  "anthropic_version": "bedrock-2023-05-31"
}
```

Output from Bedrock API:
```
response = {
  'id': 'msg_bdrk_01Lcgh98dzetRKiYzGEdkNBu', 
  'type': 'message', 
  'role': 'assistant', 
  'model': 'claude-3-5-sonnet-20240620', 
  'content': [{
    'type': 'text', 
    'text': 'Hello! How can I assist you today? Feel free to ask any questions or let me know if you need help with anything.'
  }], 
  'stop_reason': 'end_turn', 
  'stop_sequence': None, 
  'usage': {'input_tokens': 8, 'output_tokens': 29}
}
```

The response dictionary contains the metadata for the LLM reply. The 'content' field contains the response from the LLM. 

2) Add conversation history through multiple messages

Messages can contain an entire conversation between the user and model, labeled respectively with "user" and "assistant" under 'role'. 
- Messages must strictly alternate between user and alternate for Bedrock to accept the response
- Each message follows this json format with 'role' and 'content'. 

Input:
```
request_body = {
  "messages": [
    { "role": "user",      "content": "Hi" },
    { "role": "assistant", "content": "Hello!" },
    { "role": "user",      "content": "What is your name?" }
  ],
  "max_tokens": 100,
  "anthropic_version": "bedrock-2023-05-31"
}
```
Output from Bedrock API:
```
response = {
  'id': 'msg_bdrk_01SLhsudGzqwCBcyLoo9qvwh', 
  'type': 'message', 
  'role': 'assistant', 
  'model': 'claude-3-5-sonnet-20240620', 
  'content': [{
    'type': 'text', 
    'text': 'My name is Claude. It's nice to meet you!'
  }], 
  'stop_reason': 'end_turn', 
  'stop_sequence': None, 
  'usage': {'input_tokens': 21, 'output_tokens': 15}
}
```


3) System prompt

We can use the system prompt to give specific instructions and any other information useful for the LLM.
- The system prompt is the first message sent to the LLM. 
- It is given the highest priority of all messages. 
- The user is unaware of any instruction outlined in the system prompt

Input:
```
request_body = {
  "messages": [
    { "role": "user",      "content": "Hi" },
    { "role": "assistant", "content": "Hello!" },
    { "role": "user",      "content": "What is your name?" }
  ],
  "max_tokens": 100,
  "anthropic_version": "bedrock-2023-05-31",
  "system": "You are a DUPLOCLOUD agent. Your name is DUPLO."
}
```
Output from Bedrock API:
```
response = {
  'id': 'msg_bdrk_01CvBc4Vctw2iB56o2QW9jmE', 
  'type': 'message', 
  'role': 'assistant', 
  'model': 'claude-3-5-sonnet-20240620', 
  'content': [{
    'type': 'text', 
    'text': "My name is Duplo. I'm an AI assistant created by DuploCloud to help with questions and tasks related to cloud infrastructure, DevOps, and software development. How can I assist you today?"
  }], 
  'stop_reason': 'end_turn', 
  'stop_sequence': None, 
  'usage': {'input_tokens': 37, 'output_tokens': 47}
}
```

4) Structured JSON replies

Assume we need the response to be in the form of the following json format:
```
{
  'content':"<response from LLM>",
  'tone': "<Describes the tone of the message. Either angry, sad, happy, or funny.>"
}
```

There are two main ways of doing this.

- We can force a JSON response through system prompt. 
Here, we use the system prompt's priority to enforce a restriction on all responses from the LLM. Since LLMs only deal in strings, the response will be a string as well but formatted as a JSON. 

Input:
```
request_body = {
  "messages": [
      {"role": "user", "content": "Hi"},
      {"role": "assistant", "content": "Hello!"},
      {"role": "user", "content": "What is your name?"},
  ],
  "max_tokens": 100,
  "anthropic_version": "bedrock-2023-05-31",
  "system" : """
      You are a DUPLOCLOUD agent. Your name is DUPLO. 
      Every response you have, make it in a JSON format. 
      It should have two fields. 
      One is the 'content' where you output your normal response. The other is 'tone' where you have one of the following values: 'angry', 'sad', 'happy','funny'
  """
}
```
Output from Bedrock API:
```
response = {
  'id': 'msg_bdrk_01XVLxJufNWbRgKKi4ujwFsE', 
  'type': 'message', 
  'role': 'assistant', 
  'model': 'claude-3-5-sonnet-20240620', 
  'content': [{'
    type': 'text', 
    'text': "{ 'content': 'Hello there! My name is DUPLO. I\'m an AI agent created by DuploCloud to assist with various tasks and answer questions. How may I help you today?',\n    'tone': 'happy'\n}"
  }], 
    'stop_reason': 
    'end_turn', 
    'stop_sequence': None, 
    'usage': {'input_tokens': 108, 'output_tokens': 58}}
```

Ideally, you would use the json library to convert the 'text' field inside of 'content' to strictly a dictionary. 

- We can format the response with the use of tools.

Tools are built-in formatter. You can pass in several tools through the "tools" parameter. Each tool is formatting like the following:
```
example_tool = {
  "name" : "Example tool name",
  "description" : "<description of the tool>",
  "input_schema":{
     "type":"object",
        "properties": {
            ...
        }
  }
}
```
You can use "input_schema" to dictate what the input for a tool call should look like. 

"tool_choice" identifies to Bedrock and the LLM which tools are required or not required in its response. 

Input:
````
request_body = {
  "messages": [
      {"role": "user", "content": "Hi"},
      {"role": "assistant", "content": "Hello!"},
      {"role": "user", "content": "What is your name?"},
  ],
  "max_tokens": 100,
  "anthropic_version": "bedrock-2023-05-31",
  "system" : "You are a DUPLOCLOUD agent. Your name is DUPLO.",
  "tools" : [{
    "name":"tone",
    "description":"Gives the tone of the message while also giving your regular response to the previous message",
    "input_schema": {
        "type":"object",
        "properties": {
            "content" : {
                "type":"string",
                "description" : "The normal response you would have for the user"
            },
            "tone" : {
                "type":"string",
                "enum": ["happy", "angry", "sad", "funny"],
                "description" : "Should be the tone of the message"
            }
        }
    }
  }],
  "tool_choice" : {"type": "tool", "name" : "tone"}
}
```
Output from Bedrock API:
```
response = {
  'id': 'msg_bdrk_011w2xpjfyyf8hLCNaMJCNBF', 
  'type': 'message', 'role': 'assistant', 
  'model': 'claude-3-5-sonnet-20240620', 
  'content': [{
    'type': 'tool_use', 
    'id': 'toolu_bdrk_01Ks3jE3VcoT4T8Wi1RLFLCv', 
    'name': 'tone', 
    'input': {
      'content': "Hello! My name is DUPLO. I'm the DUPLOCLOUD agent, here to assist you with any questions or information you need about DUPLOCLOUD. How can I help you today?", 
      'tone': 'happy'
    }
  }], 
  'stop_reason': 'tool_use', 
  'stop_sequence': None, 
  'usage': {'input_tokens': 425, 'output_tokens': 91}}
```

## Coming Soon (Hopefully before tomorrow)

- A boilerplate for a tool calling agent using strands, so that you can create an agent by just adding some python functions with doc strings (tools) and by editing a system prompt
- Boilerplate for workflows
- Better service desk mock UI
- More comprehensive postman collection for testing
- Dockerizaiton

## References:

- Service Desk Request Response Structure:
https://docs.duplocloud.com/docs/ai-suite/ai-studio/developers

## License
See the [LICENSE](LICENSE) file for details.
