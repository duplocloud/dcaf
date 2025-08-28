from dcaf.llm import BedrockLLM
import dotenv
import logging
import os

dotenv.load_dotenv(override=True)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(message)s",
)

# Example Usage
if __name__ == "__main__":
    print("Example Usage - Bedrock Converse API")
    
    # Initialize the client
    llm = BedrockLLM(region_name="us-west-2")
    
    # Simple text conversation
    response = llm.invoke(
        messages=[{"role": "user", "content": "Hello, how are you?"}],
        # model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        model_id="openai.gpt-oss-120b-1:0",
        max_tokens=500,
        temperature=0.7
    )

    print('\n'*5)
    print("Response:", response)
    print('\n'*5)

    # Example with tools
    tools = [{
        "name": "get_weather",
        "description": "Get the weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA"
                }
            },
            "required": ["location"]
        }
    }]
    
    response_with_tools = llm.invoke(
        messages=[{"role": "user", "content": "What's the weather in New York?"}],
        model_id="anthropic.claude-3-5-sonnet-20240620-v1:0",
        system_prompt="You are a helpful assistant that can check the weather.",
        tools=tools,
        tool_choice="any"
        # tool_choice={"name": "get_weather"}
    )
    
    print('\n'*5)
    print("Response with tools:", response_with_tools)
    print('\n'*5)