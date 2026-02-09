"""Tests for legacy agent base class and subclasses."""

from unittest.mock import MagicMock

import pytest

from dcaf.agents.base_command_agent import (
    LEGACY_DEFAULT_MODEL_ID,
    LEGACY_MAX_TOKENS,
    BaseCommandAgent,
)

# =============================================================================
# Helpers
# =============================================================================


class ConcreteAgent(BaseCommandAgent):
    """Minimal concrete subclass for testing the base class."""

    def _default_system_prompt(self) -> str:
        return "You are a test agent."

    def _create_response_schema(self) -> dict:
        return {
            "name": "return_response",
            "description": "Test schema",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "terminal_commands": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                        },
                    },
                },
                "required": ["content"],
            },
        }


def _create_fake_llm(response: dict | None = None):
    """Create a mock BedrockLLM that returns a canned response."""
    llm = MagicMock()
    llm.normalize_message_roles.side_effect = lambda msgs: msgs
    llm.invoke.return_value = response or {"content": "Hello!", "terminal_commands": []}
    return llm


# =============================================================================
# BaseCommandAgent.__init__ Tests
# =============================================================================


class TestBaseCommandAgentInit:
    def test_default_system_prompt_used(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)
        assert agent.system_prompt == "You are a test agent."

    def test_custom_system_prompt(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm, system_prompt="Custom prompt")
        assert agent.system_prompt == "Custom prompt"

    def test_response_schema_set(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)
        assert agent.response_schema["name"] == "return_response"


# =============================================================================
# BaseCommandAgent.call_llm Tests
# =============================================================================


class TestCallLlm:
    def test_calls_llm_invoke(self):
        llm = _create_fake_llm({"content": "Response", "terminal_commands": []})
        agent = ConcreteAgent(llm)

        result = agent.call_llm([{"role": "user", "content": "Hi"}])

        assert result["content"] == "Response"
        llm.invoke.assert_called_once()

    def test_passes_correct_params(self, monkeypatch):
        monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        agent.call_llm([{"role": "user", "content": "Hi"}])

        call_kwargs = llm.invoke.call_args
        assert call_kwargs.kwargs["model_id"] == LEGACY_DEFAULT_MODEL_ID
        assert call_kwargs.kwargs["max_tokens"] == LEGACY_MAX_TOKENS

    def test_expired_token_raises_with_hint(self):
        llm = _create_fake_llm()
        llm.invoke.side_effect = Exception(
            "An error occurred (ExpiredTokenException) when calling the InvokeModel operation: "
            "The security token included in the request is expired"
        )
        agent = ConcreteAgent(llm)

        with pytest.raises(Exception, match="ExpiredTokenException.*refresh"):
            agent.call_llm([{"role": "user", "content": "Hi"}])

    def test_other_error_raises(self):
        llm = _create_fake_llm()
        llm.invoke.side_effect = RuntimeError("Connection failed")
        agent = ConcreteAgent(llm)

        with pytest.raises(Exception, match="Connection failed"):
            agent.call_llm([{"role": "user", "content": "Hi"}])


# =============================================================================
# BaseCommandAgent.execute_cmd Tests
# =============================================================================


class TestExecuteCmd:
    def test_successful_command(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent.execute_cmd("echo hello")
        assert "hello" in result

    def test_command_with_no_output(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent.execute_cmd("true")
        assert "successfully" in result.lower() or result.strip() != ""

    def test_command_with_stderr(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent.execute_cmd("echo error >&2")
        assert "error" in result.lower()


# =============================================================================
# BaseCommandAgent._extract_commands Tests
# =============================================================================


class TestExtractCommands:
    def test_with_commands(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent._extract_commands({"terminal_commands": [{"command": "ls -la"}]})
        assert result == [{"command": "ls -la"}]

    def test_without_commands(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent._extract_commands({"content": "No commands"})
        assert result == []

    def test_empty_commands(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        result = agent._extract_commands({"terminal_commands": []})
        assert result == []


# =============================================================================
# BaseCommandAgent.invoke Tests
# =============================================================================


class TestInvoke:
    def test_basic_invoke(self):
        llm = _create_fake_llm(
            {
                "content": "Run this command",
                "terminal_commands": [{"command": "ls"}],
            }
        )
        agent = ConcreteAgent(llm)

        result = agent.invoke({"messages": [{"role": "user", "content": "List files"}]})

        assert result.content == "Run this command"
        assert len(result.data.cmds) == 1
        assert result.data.cmds[0].command == "ls"

    def test_invoke_with_no_commands(self):
        llm = _create_fake_llm(
            {
                "content": "Just text",
                "terminal_commands": [],
            }
        )
        agent = ConcreteAgent(llm)

        result = agent.invoke({"messages": [{"role": "user", "content": "Hello"}]})

        assert result.content == "Just text"
        assert len(result.data.cmds) == 0


# =============================================================================
# BaseCommandAgent.process_messages Tests
# =============================================================================


class TestProcessMessages:
    def test_basic_message_processing(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        processed, executed = agent.process_messages(
            {
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there"},
                ]
            }
        )

        assert len(processed) == 2
        assert processed[0]["role"] == "user"
        assert processed[1]["role"] == "assistant"
        assert executed == []

    def test_skips_non_user_assistant_roles(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        processed, _ = agent.process_messages(
            {
                "messages": [
                    {"role": "system", "content": "System msg"},
                    {"role": "user", "content": "Hello"},
                ]
            }
        )

        assert len(processed) == 1
        assert processed[0]["role"] == "user"

    def test_empty_messages(self):
        llm = _create_fake_llm()
        agent = ConcreteAgent(llm)

        processed, executed = agent.process_messages({"messages": []})

        assert processed == []
        assert executed == []


# =============================================================================
# Subclass Import Tests
# =============================================================================


class TestSubclassImports:
    def test_command_agent_imports(self):
        from dcaf.agents.cmd_agent import CommandAgent

        assert issubclass(CommandAgent, BaseCommandAgent)

    def test_aws_agent_imports(self):
        from dcaf.agents.aws_agent import AWSAgent

        assert issubclass(AWSAgent, BaseCommandAgent)

    def test_k8s_agent_imports(self):
        from dcaf.agents.k8s_agent import K8sAgent

        assert issubclass(K8sAgent, BaseCommandAgent)

    def test_command_agent_creates_successfully(self):
        from dcaf.agents.cmd_agent import CommandAgent

        llm = _create_fake_llm()
        agent = CommandAgent(llm)
        assert agent.system_prompt is not None

    def test_aws_agent_creates_successfully(self):
        from dcaf.agents.aws_agent import AWSAgent

        llm = _create_fake_llm()
        agent = AWSAgent(llm)
        assert agent.system_prompt is not None

    def test_k8s_agent_creates_successfully(self):
        from dcaf.agents.k8s_agent import K8sAgent

        llm = _create_fake_llm()
        agent = K8sAgent(llm)
        assert agent.system_prompt is not None


# =============================================================================
# K8sAgent-specific Tests
# =============================================================================


class TestK8sAgentExtractCommands:
    def test_handles_string_commands(self):
        from dcaf.agents.k8s_agent import K8sAgent

        llm = _create_fake_llm()
        agent = K8sAgent(llm)

        result = agent._extract_commands(
            {"terminal_commands": ["kubectl get pods", "kubectl get svc"]}
        )

        assert len(result) == 2
        assert result[0] == {"command": "kubectl get pods"}
        assert result[1] == {"command": "kubectl get svc"}

    def test_handles_dict_commands(self):
        from dcaf.agents.k8s_agent import K8sAgent

        llm = _create_fake_llm()
        agent = K8sAgent(llm)

        result = agent._extract_commands(
            {"terminal_commands": [{"command": "kubectl get pods -n default"}]}
        )

        assert len(result) == 1
        assert result[0]["command"] == "kubectl get pods -n default"

    def test_handles_mixed_commands(self):
        from dcaf.agents.k8s_agent import K8sAgent

        llm = _create_fake_llm()
        agent = K8sAgent(llm)

        result = agent._extract_commands(
            {
                "terminal_commands": [
                    "kubectl get pods",
                    {"command": "helm list", "explanation": "List helm releases"},
                ]
            }
        )

        assert len(result) == 2
