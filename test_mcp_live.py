"""
Live test of MCPTool with DuploCloud's MCP server.

This demonstrates the simplest way to use MCP tools with DCAF:
1. Create an MCPTool instance pointing to an MCP server
2. Pass it to an Agent
3. Run the agent - connection is handled automatically
"""

import asyncio
import logging

# Enable logging to see MCP lifecycle events
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Simple example of using MCPTool with a DCAF Agent."""
    from dcaf.core import Agent
    from dcaf.mcp import MCPTool

    # 1. Create MCPTool pointing to an MCP server
    mcp_tool = MCPTool(
        url="https://docs.duplocloud.com/docs/~gitbook/mcp",
        transport="streamable-http",
    )

    # 2. Create an agent with the MCP tools
    agent = Agent(
        tools=[mcp_tool],
        system_prompt="You are a helpful assistant. Use the available tools to answer questions about DuploCloud documentation."
    )

    # 3. Run the agent - MCP connection is handled automatically
    logger.info("Running agent with MCP tools...")
    result = agent.run([
        {"role": "user", "content": "What tools are available to you? Just list them briefly."}
    ])

    logger.info(f"Agent response: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
