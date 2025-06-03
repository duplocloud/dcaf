import os
import json
import logging
from typing import List, Dict, Any

import dotenv
dotenv.load_dotenv(override=True)  # Load environment variables from .env file

# Import the embedding provider factory from your services/embedding.py module
from services.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class CICDFailurePredictiveAgent:
    def __init__(self, llm):
        """
        Initialize the agent with an LLM instance and the Bedrock embedding provider.
        """
        self.llm = llm
        self.similarity_threshold = 0.8
        # Create an instance of the Bedrock embedding provider using the factory.
        # Ensure that AWS_REGION is set in your environment (defaulting to "us-east-1")
        self.embedding_provider = EmbeddingProvider.create(
            "bedrock",
            model_id="amazon.titan-embed-text-v1",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )

    def invoke(self, messages: dict) -> dict:
        """
        Processes incoming messages to predict CI/CD failures.
        Expects a dict with a key "messages" containing a list of message objects.
        """
        messages_list = self._normalize_messages(messages)
        user_text = self._extract_latest_message(messages_list)
        embedding_vector = self._embed_text(user_text)
        similar_results = self._query_vector_db(embedding_vector)
        risk_score, references = self._compute_risk(similar_results)
        explanation = self._generate_explanation(risk_score, references)
        refined_explanation = self.llm.call_llm(f"Refine this diagnostic explanation: {explanation}")
        commands = self._suggest_commands(risk_score)
        response = {
            "role": "assistant",
            "content": refined_explanation,
            "data": {
                "commands": commands
            }
        }
        return response

    def _normalize_messages(self, messages: dict) -> List[dict]:
        """
        Ensures that the incoming data is a list of message dicts.
        """
        if isinstance(messages, dict) and "messages" in messages:
            return messages["messages"]
        elif isinstance(messages, list):
            return messages
        else:
            raise ValueError("Invalid messages format provided.")

    def _extract_latest_message(self, messages_list: List[dict]) -> str:
        """
        Retrieves the content of the most recent message with role "user".
        """
        for msg in reversed(messages_list):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return msg.get("content", "")
        return ""

    def _embed_text(self, text: str) -> List[float]:
        """
        Uses the Bedrock embedding provider to generate an embedding for the provided text.
        """
        try:
            return self.embedding_provider.embed_query(text)
        except Exception as e:
            logger.error("Error generating embedding: %s", e)
            raise

    def _query_vector_db(self, embedding_vector: List[float]) -> List[Dict[str, Any]]:
        """
        Dummy vector database query function.
        Replace this function with your production vector database integration.
        """
        # For demonstration purposes, return fixed synthetic results.
        return [
            {"id": "log_101", "similarity_score": 0.85},
            {"id": "log_102", "similarity_score": 0.65}
        ]

    def _compute_risk(self, results: List[Dict[str, Any]]) -> (float, List[str]):
        """
        Computes a risk score based on similarity scores and collects log references.
        """
        high_hits = [res for res in results if res.get("similarity_score", 0) >= 0.85]
        if high_hits:
            avg_score = sum(res.get("similarity_score", 0) for res in high_hits) / len(high_hits)
            risk_score = avg_score * 100  # Scale to percentage.
        else:
            risk_score = 0.0
        references = [res.get("id", "unknown") for res in high_hits]
        return risk_score, references

    def _generate_explanation(self, risk_score: float, references: List[str]) -> str:
        """
        Generates a diagnostic explanation based on the risk score and related log references.
        """
        explanation = f"Based on historical CI/CD logs, the computed risk score is {risk_score:.1f}%. "
        if references:
            explanation += f"Found similar failures in logs: {', '.join(references)}. "
        else:
            explanation += "No closely matching failure patterns were found. "
        explanation += "Further diagnostics are recommended."
        return explanation

    def _suggest_commands(self, risk_score: float) -> List[Dict[str, Any]]:
        """
        Suggests diagnostic commands based on the computed risk score.
        """
        if risk_score > 70:
            return [
                {"command": "kubectl describe pods", "execute": False},
                {"command": "kubectl logs --tail=100 <pod_name>", "execute": False},
            ]
        else:
            return [{"command": "kubectl get pods", "execute": False}]


class BedrockAnthropicLLM:
    def __init__(self, region_name: str = "us-east-1"):
        self.region = region_name

    def call_llm(self, prompt: str) -> str:
        """
        Dummy implementation of an LLM call.
        In production, replace this with an API call to the appropriate LLM service.
        """
        return f"Refined explanation: {prompt}"


if __name__ == "__main__":
    # For local testing, ensure your AWS credentials and other settings are provided in the .env file.
    dotenv.load_dotenv(override=True)  # Already loaded at the top, but reloading here ensures it's available.

    # Instantiate the dummy LLM and our CI/CD agent.
    llm_instance = BedrockAnthropicLLM(region_name=os.getenv("AWS_REGION", "us-east-1"))
    agent = CICDFailurePredictiveAgent(llm_instance)

    # Example test message in the expected external request format.
    test_input = {
        "messages": [
            {
                "role": "user",
                "content": "CI/CD pipeline error: Build failed with error code E123 during deployment step."
            }
        ]
    }

    # Invoke the agent and print the resulting response.
    response = agent.invoke(test_input)
    print(json.dumps(response, indent=2))
