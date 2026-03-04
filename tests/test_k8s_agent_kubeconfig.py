"""Tests for K8s agent kubeconfig_path extraction."""

import base64

from dcaf.agents.k8s_agent import K8sAgent


def _make_agent() -> K8sAgent:
    """Create a K8sAgent without initializing the full LLM stack."""
    return K8sAgent.__new__(K8sAgent)


def _user_message(platform_context: dict) -> dict:
    return {"messages": [{"role": "user", "content": "list pods", "platform_context": platform_context}]}


class TestK8sAgentKubeconfigExtraction:
    def test_uses_kubeconfig_path_from_context_when_present(self):
        """If kubeconfig_path is already in platform_context, use it directly (no decode)."""
        agent = _make_agent()
        msgs = _user_message({"kubeconfig_path": "/pre/prepared/kubeconfig.yaml"})
        _, kubeconfig_path = agent._extract_kubeconfig_path(msgs)
        assert kubeconfig_path == "/pre/prepared/kubeconfig.yaml"

    def test_falls_back_to_base64_decode_when_no_path(self, tmp_path):
        """Legacy: if no kubeconfig_path but kubeconfig (base64) is present, decode it."""
        agent = _make_agent()
        kube_b64 = base64.b64encode(b"apiVersion: v1\n").decode()
        msgs = _user_message({"kubeconfig": kube_b64})
        _, kubeconfig_path = agent._extract_kubeconfig_path(msgs)
        assert kubeconfig_path is not None
        import os
        assert os.path.exists(kubeconfig_path)
        # clean up
        os.unlink(kubeconfig_path)

    def test_returns_none_when_no_kubeconfig_data(self):
        """No kubeconfig data → kubeconfig_path is None."""
        agent = _make_agent()
        msgs = _user_message({})
        _, kubeconfig_path = agent._extract_kubeconfig_path(msgs)
        assert kubeconfig_path is None
