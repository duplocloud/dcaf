# Service Desk Agents

A flexible, protocol-based service desk agent framework built with FastAPI that enables various agent implementations to respond to user chat messages.

## Overview

This project provides a modular framework for creating and deploying service desk agents that can:

- Process chat messages from users
- Implement different agent behaviors through a common protocol
- Integrate with AWS Bedrock for LLM capabilities (especially Anthropic Claude models)
- Provide a standardized message schema for communication
- Include a mock UI for testing interactions

## Project Structure

```
├── agent_server.py         # FastAPI server and agent protocol definition
├── agents/                 # Agent implementations
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
- AWS account with Bedrock access (for LLM functionality)
- For mock UI: tkinter
  - Mac: `brew install python-tk`
  - Windows: Included with Python installation

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

### Creating a New Agent

To create a new agent, implement the `AgentProtocol` interface:

```python
from agent_server import AgentProtocol
from schemas.messages import Messages, AgentMessage

class MyCustomAgent(AgentProtocol):
    def invoke(self, messages: Messages) -> AgentMessage:
        # Your agent logic here
        return AgentMessage(content="Your response")
```

### Use Service Desk Mock UI (Work in progress)

```bash
python service_desk_mock_ui.py
```

Note: This is a simple mock UI for testing interactions. It is it does not mock all service desk features and only replciates the content and terminal command approval/rejection features. Future support will be added to mock all service desk features for local testing.

## AWS Configuration

The application uses AWS Bedrock for LLM functionality. Configure your AWS credentials in the `.env` file or through standard AWS credential methods (environment variables, IAM roles, etc.).

## License

See the [LICENSE](LICENSE) file for details.
