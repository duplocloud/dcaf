"""Tests for ServerAdapter — gap fixes for command-executing agents."""

import os
import tempfile
from unittest.mock import MagicMock, patch

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
        ctx = {"tenant_name": "acme", "kubeconfig": "/home/user/.kube/config"}

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


class TestProcessApprovedCommandsPassesFiles:
    def test_files_extracted_and_passed_to_execute_cmd(self):
        """Files in data.cmds[].files must be forwarded to _execute_cmd."""
        adapter = _make_adapter()
        files = [{"file_path": "values.yaml", "file_content": "replicaCount: 2"}]

        with patch.object(adapter, "_execute_cmd", return_value="ok") as mock_exec:
            messages = [
                {
                    "role": "user",
                    "content": "go",
                    "data": {
                        "cmds": [
                            {
                                "command": "helm install myapp .",
                                "execute": True,
                                "files": files,
                            }
                        ]
                    },
                }
            ]
            adapter._process_approved_commands(messages, {})
            mock_exec.assert_called_once_with("helm install myapp .", files=files, context={})

    def test_no_files_passes_none(self):
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


class TestExecuteCmdWithFiles:
    def test_files_are_written_to_tempdir(self):
        """When files are provided, _execute_cmd writes them before running the command."""
        adapter = _make_adapter()
        files = [{"file_path": "hello.txt", "file_content": "world"}]

        # Command that reads the file we wrote
        result = adapter._execute_cmd("cat hello.txt", files=files, context={})

        assert result.strip() == "world"

    def test_tempdir_is_cleaned_up_after_execution(self):
        """Temp directory must not persist after _execute_cmd returns."""
        adapter = _make_adapter()
        captured_dirs: list[str] = []

        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            captured_dirs.append(d)
            return d

        files = [{"file_path": "f.txt", "file_content": "x"}]
        with patch("tempfile.mkdtemp", side_effect=recording_mkdtemp):
            adapter._execute_cmd("echo done", files=files, context={})

        assert len(captured_dirs) == 1
        assert not os.path.exists(captured_dirs[0]), "Temp dir should be deleted"

    def test_tempdir_cleaned_up_on_error(self):
        """Temp directory is cleaned up even when file writing raises."""
        adapter = _make_adapter()
        captured_dirs: list[str] = []

        original_mkdtemp = tempfile.mkdtemp

        def recording_mkdtemp(**kwargs):
            d = original_mkdtemp(**kwargs)
            captured_dirs.append(d)
            return d

        files = [{"file_path": "f.txt", "file_content": "x"}]
        with (
            patch("tempfile.mkdtemp", side_effect=recording_mkdtemp),
            # Simulate file-write failure
            patch("builtins.open", side_effect=OSError("disk full")),
        ):
            result = adapter._execute_cmd("echo nope", files=files, context={})

        assert "Error" in result
        assert not os.path.exists(captured_dirs[0]), "Temp dir should be deleted on error"

    def test_no_files_runs_in_default_cwd(self):
        """Without files, command runs normally (no tempdir created)."""
        adapter = _make_adapter()
        with patch("tempfile.mkdtemp") as mock_mkdtemp:
            adapter._execute_cmd("echo hello", files=None, context={})
            mock_mkdtemp.assert_not_called()
