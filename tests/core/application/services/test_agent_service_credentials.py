"""Test that AgentService wires CredentialManager and enhances platform_context."""

import base64
import os
from typing import Any

import pytest

from dcaf.core.application.dto.requests import AgentRequest
from dcaf.core.application.dto.responses import AgentResponse
from dcaf.core.application.services.agent_service import AgentService
from dcaf.core.domain.entities import Message
from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.testing import FakeConversationRepository, FakeEventPublisher

FAKE_KUBECONFIG_B64 = base64.b64encode(b"apiVersion: v1\nclusters: []\n").decode()


class AsyncFakeRuntime:
    """Async fake that records invoke kwargs for inspection."""

    def __init__(self):
        self._invoke_calls: list[dict[str, Any]] = []

    @property
    def last_platform_context(self) -> dict | None:
        return self._invoke_calls[-1]["platform_context"] if self._invoke_calls else None

    async def invoke(
        self,
        messages: list[Message],
        tools: list[Any],
        system_prompt: str | None = None,
        static_system: str | None = None,
        dynamic_system: str | None = None,
        platform_context: dict | None = None,
    ) -> AgentResponse:
        self._invoke_calls.append({"platform_context": platform_context})
        return AgentResponse.text_only("test-conv", "ok")

    async def invoke_stream(self, **kwargs: Any):
        platform_context = kwargs.get("platform_context")
        self._invoke_calls.append({"platform_context": platform_context})
        # yield nothing — we only care about what was passed
        return
        yield  # make this a generator


@pytest.fixture
def runtime():
    return AsyncFakeRuntime()


@pytest.fixture
def service(runtime):
    return AgentService(
        runtime=runtime,
        conversations=FakeConversationRepository(),
        events=FakeEventPublisher(),
    )


class TestAgentServiceCredentialWiring:
    async def test_kubeconfig_path_added_to_platform_context(self, service, runtime):
        """CredentialManager should add kubeconfig_path to the context passed to runtime."""
        ctx = PlatformContext(kubeconfig=FAKE_KUBECONFIG_B64)
        request = AgentRequest(content="list pods", context=ctx.to_dict())

        await service.execute(request)

        ctx_dict = runtime.last_platform_context
        assert ctx_dict is not None
        assert "kubeconfig_path" in ctx_dict
        # The path is a temp file path (existence already tested in CredentialManager tests)
        assert ctx_dict["kubeconfig_path"].startswith(("/tmp", "/var/folders"))

    async def test_kubeconfig_tempfile_cleaned_up_after_execute(self, service, runtime):
        """Temp file should be gone after execute() returns."""
        ctx = PlatformContext(kubeconfig=FAKE_KUBECONFIG_B64)
        request = AgentRequest(content="list pods", context=ctx.to_dict())

        await service.execute(request)

        path = runtime.last_platform_context["kubeconfig_path"]
        assert not os.path.exists(path)

    async def test_no_kubeconfig_no_kubeconfig_path(self, service, runtime):
        """When no kubeconfig is in context, kubeconfig_path should not appear."""
        request = AgentRequest(content="hello")

        await service.execute(request)

        ctx_dict = runtime.last_platform_context
        assert ctx_dict is None or "kubeconfig_path" not in ctx_dict

    async def test_stream_kubeconfig_path_added(self, service, runtime):
        """CredentialManager should also apply for execute_stream."""
        ctx = PlatformContext(kubeconfig=FAKE_KUBECONFIG_B64)
        request = AgentRequest(content="list pods", context=ctx.to_dict())

        async for _ in service.execute_stream(request):
            pass

        ctx_dict = runtime.last_platform_context
        assert ctx_dict is not None
        assert "kubeconfig_path" in ctx_dict
