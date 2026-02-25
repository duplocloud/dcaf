"""Tests for ServerAdapter — gap fixes for command-executing agents."""

from unittest.mock import MagicMock, patch

import pytest

from dcaf.core.adapters.inbound.server_adapter import ServerAdapter


def _make_adapter(**kwargs):
    """Create a ServerAdapter with a minimal mock agent."""
    mock_agent = MagicMock()
    mock_agent.tools = []
    return ServerAdapter(mock_agent, **kwargs)


class TestProcessApprovedCommandsReceivesContext:
    def test_context_is_passed_to_execute_cmd(self):
        """_process_approved_commands must forward platform_context to _execute_cmd."""
        adapter = _make_adapter()
        ctx = {"tenant_name": "acme", "kubeconfig": "/tmp/kubeconfig"}

        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {"cmds": [{"command": "kubectl get pods", "execute": True}]},
                }
            ]
            adapter._process_approved_commands(messages, ctx)
            mock_exec.assert_called_once_with("kubectl get pods", files=None, context=ctx)

    def test_empty_context_is_forwarded(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {"cmds": [{"command": "ls", "execute": True}]},
                }
            ]
            adapter._process_approved_commands(messages, {})
            mock_exec.assert_called_once_with("ls", files=None, context={})
