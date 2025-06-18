from schemas.messages import AgentMessage, Data


# simple_log_analyzer.py

def analyze_logs(log_text: str, failure_keywords=None) -> float:
    # If no keywords are provided, use these defaults.
    if failure_keywords is None:
        failure_keywords = ["error", "failed", "exception"]

    # Split the logs into individual lines.
    lines = log_text.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return 0.0

    # Count how many lines contain any of the error keywords.
    failure_count = sum(
        1 for line in lines
        if any(keyword in line.lower() for keyword in failure_keywords)
    )

    # Calculate risk percentage.
    risk_percentage = (failure_count / total_lines) * 100
    return risk_percentage

class SimpleFailurePredictiveAgent:
    def __init__(self):
        pass
    
    def invoke(self, messages: dict) -> AgentMessage:
        # Assume messages come in as: {"messages": [{"role": "user", "content": "log text here"}]}
        msg_list = messages.get("messages", [])
        if not msg_list:
            return AgentMessage(content="No log input provided.", data=Data())

        log_text = msg_list[0].get("content", "")
        risk = analyze_logs(log_text)
        content = f"Predicted failure risk based on log analysis is {risk:.2f}%."
        return AgentMessage(content=content, data=Data())

# For testing:
if __name__ == "__main__":
    sample_request = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "CI/CD pipeline started\n"
                    "CI/CD pipeline error: Build failed with error code E123 during deployment step.\n"
                    "Build logs: some info here\n"
                    "Error: unexpected exception in the build process\n"
                    "CI/CD pipeline completed"
                )
            }
        ]
    }
    agent = SimpleFailurePredictiveAgent()
    response = agent.invoke(sample_request)
    print("Agent Response:", response.content)
