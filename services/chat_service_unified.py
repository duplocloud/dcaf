"""
Unified Chat Service - Provider-Agnostic Implementation

This service uses the AgentProvider abstraction to work with any agent framework
(Agno, Strands, or future frameworks). The business logic is completely decoupled
from the specific agent implementation.

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│  BUSINESS LOGIC (Framework-Independent)                         │
│  • Dynamic schema selection                                     │
│  • Tenant scoping security                                      │
│  • Platform context extraction                                  │
│  • Mermaid PDF generation                                       │
│  • Performance tracking                                         │
└─────────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│  AGENT PROVIDER ABSTRACTION (Strategy Pattern)                  │
│  • AgnoProvider ✓                                               │
│  • StrandsProvider (future)                                     │
│  • CustomProvider (future)                                      │
└─────────────────────────────────────────────────────────────────┘
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from services.agent_providers import ToolDefinition, get_agent_provider
from services.diagram_styling import inject_styling_in_content
from services.mermaid_service import attach_pdfs_from_mermaid
from services.performance_tracker import set_request_id
from services.schema_selector import get_schema_selector
from services.tenant_cypher_rewriter import (
    RewriteConfig,
    TenantRewriteError,
    rewrite_cypher,
)
from tools.neo4j_tools import run_cypher_query
from utils.safe_logging import safe_get_nested, safe_log_info, safe_log_json

logger = logging.getLogger(__name__)

# Schema cache version - increment when cache structure changes
SCHEMA_CACHE_VERSION = 1


def _extract_accumulated_schema_cache(history: list[dict]) -> dict:
    """
    Extract accumulated schema cache from previous assistant messages.

    Scans history for assistant messages with data.schema_cache and returns the
    most recent cache object.

    NOTE: This must be called BEFORE _clean_messages_for_bedrock() which strips
    the 'data' field from messages.
    """
    # Iterate in reverse to find most recent assistant message with schema
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            cache = msg.get("data", {}).get("schema_cache")
            if isinstance(cache, dict) and cache:
                return cache
    return {}


def _merge_schema_cache(
    *,
    prior_cache: dict,
    current_elements: list[dict],
    tenant_id: str | None,
) -> dict:
    """
    Merge current schema selection with prior cache.

    - Deduplication key: element['id'] when present (falls back to composite key).
    - Guardrails: if tenant_id differs, discard prior cache.
    - Current elements overwrite prior entries with same key (fresh relevance/similarity).
    """
    prior_tenant = prior_cache.get("tenant_id")
    if tenant_id and prior_tenant and prior_tenant != tenant_id:
        # Tenant changed - discard prior cache to prevent cross-tenant schema leakage
        logger.info(
            "Schema cache tenant mismatch (prior=%s, current=%s) - discarding prior cache",
            prior_tenant,
            tenant_id,
        )
        prior_cache = {}

    elements_by_id = (
        dict(prior_cache.get("elements_by_id"))
        if isinstance(prior_cache.get("elements_by_id"), dict)
        else {}
    )

    def key_for(elem: dict) -> str | None:
        if elem.get("id"):
            return str(elem["id"])
        # Fallback: stable-ish composite (covers nodes + relationships)
        t = elem.get("type")
        if t == "node" and elem.get("label"):
            return f"node:{elem['label']}"
        if t == "relationship":
            return "rel:" + ":".join(
                str(x or "")
                for x in [elem.get("rel_type"), elem.get("from_label"), elem.get("to_label")]
            )
        return None

    for elem in current_elements:
        k = key_for(elem)
        if k:
            elements_by_id[k] = elem

    return {
        "version": SCHEMA_CACHE_VERSION,
        "tenant_id": tenant_id,
        "elements_by_id": elements_by_id,
    }


def _clean_messages_for_bedrock(history: list[dict]) -> list[dict]:
    """
    Clean message history for Bedrock compatibility.

    Removes platform_context and other non-standard fields.
    Also filters out messages that are part of tool call sequences
    (toolUse/toolResult blocks) since Agno handles tool calls internally.
    Including partial tool sequences causes Bedrock ValidationException:
    "Expected toolResult blocks at messages.X.content for the following Ids: ..."
    """
    # TEST FLAG: Set DISABLE_TOOL_FILTERING=true to reproduce the original bug
    disable_filtering = os.getenv("DISABLE_TOOL_FILTERING", "false").lower() == "true"
    if disable_filtering:
        logger.warning("⚠️ DISABLE_TOOL_FILTERING=true - Tool message filtering is DISABLED (bug reproduction mode)")
    
    cleaned_history = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")

        # If filtering is disabled (for bug reproduction), skip all filtering
        if not disable_filtering:
            # Skip messages with no content (tool-only messages)
            if content is None:
                continue

            # Skip empty string content
            if isinstance(content, str) and not content.strip():
                continue

            # Skip messages where content is a list (Bedrock tool blocks)
            # These are toolUse (assistant) or toolResult (user) messages
            if isinstance(content, list):
                continue

        # Build cleaned message with only supported fields
        cleaned = {"role": role, "content": content}
        if "name" in msg:
            cleaned["name"] = msg["name"]

        cleaned_history.append(cleaned)

    return cleaned_history


def _extract_platform_context(last_message: dict) -> dict:
    """
    Extract platform context from the last message.

    Returns:
        dict: Platform context with tenant_id, user_email, roles, etc.
    """
    ctx = last_message.get("platform_context", {})
    return {
        "tenant_id": ctx.get("tenant_id") or ctx.get("tenantId"),
        "tenant_name": ctx.get("tenant_name") or ctx.get("tenantName"),
        "user_email": ctx.get("user_email") or ctx.get("userEmail"),
        "user_roles": ctx.get("user_roles") or ctx.get("userroles", []),
        "k8s_namespace": ctx.get("k8s_namespace") or ctx.get("k8sNamespace"),
    }


_EXISTS_PATTERN = re.compile(
    r"EXISTS\s*\(\s*(\([^()]*\)-\[[^\]]*\]->\([^()]*\))\s*\)",
    re.IGNORECASE,
)


def _normalize_exists_patterns(cypher: str) -> str:
    """Convert deprecated EXISTS() pattern syntax into subquery form."""

    def replacer(match: re.Match) -> str:
        pattern_body = match.group(1).strip()
        return f"EXISTS {{ MATCH {pattern_body} }}"

    return _EXISTS_PATTERN.sub(replacer, cypher)


def _inject_where_clause(cypher: str, predicate: str) -> str:
    """
    Inject a tenant predicate into the first MATCH clause of the Cypher query.

    We keep the user's query structure intact and only add a server-side security filter.
    """
    trimmed = cypher.strip()
    if not trimmed:
        raise ValueError("Security requirement: Cypher query must not be empty.")

    match_pattern = re.compile(
        r"(MATCH\s+.*?)(\s+(?:OPTIONAL\s+MATCH|WHERE|WITH|RETURN|CREATE|MERGE|DELETE|SET|REMOVE|UNWIND|CALL|FOREACH|SKIP|LIMIT|ORDER\s+BY))",
        re.IGNORECASE | re.DOTALL,
    )

    def inject_at_first_match(match_obj):
        match_clause = match_obj.group(1)
        rest = match_obj.group(2)

        if re.search(r"\bWHERE\b", match_clause, re.IGNORECASE):
            updated = re.sub(
                r"(\bWHERE\b)",
                rf"\1 ({predicate}) AND",
                match_clause,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            updated = match_clause + f"\nWHERE {predicate}"

        return updated + rest

    result = match_pattern.sub(inject_at_first_match, trimmed, count=1)
    return result
def make_scoped_cypher_tool(tenant_id: str, role: str) -> ToolDefinition:
    """
    Create tenant-scoped Cypher tool - BUSINESS LOGIC (framework-independent)

    This wraps every Cypher query with server-side security.
    Returns a ToolDefinition that can be used with any agent framework.
    """
    async def run_scoped_cypher_query(cypher: str, params: dict | None = None) -> list[dict]:
        """
        Execute a tenant-scoped Cypher query against Neo4j.

        Security is enforced server-side - the agent cannot bypass it.
        """
        merged = dict(params or {})

        # SECURITY: Access policy guard
        if role != "Administrator":
            forbidden_labels = ["DuploInfra", "DuploPlan", "AWSAccount"]
            pattern = r":\s*(" + "|".join(map(re.escape, forbidden_labels)) + r")\b"
            if re.search(pattern, cypher):
                raise ValueError(
                    "Access denied: query references forbidden labels for user role"
                )

        # Tenant ID resolution (populate for all roles, enforce for non-admins)
        incoming_tenant_id = merged.get("tenantId")
        effective_tenant_id = None
        if isinstance(incoming_tenant_id, str) and incoming_tenant_id.strip():
            effective_tenant_id = incoming_tenant_id.strip()
        elif isinstance(tenant_id, str) and tenant_id.strip():
            effective_tenant_id = tenant_id.strip()

        if effective_tenant_id:
            merged["tenantId"] = effective_tenant_id
        elif role != "Administrator":
            raise ValueError(
                "Security requirement: tenant_id is required for user role but was not provided."
            )

        # SECURITY: Server-side IN_TENANT scoping (CRITICAL)
        if role != "Administrator":
            has_n_var = bool(re.search(r"(?<![A-Za-z0-9_])n(?![A-Za-z0-9_])", cypher))
            if not has_n_var:
                raise ValueError(
                    "Security requirement: The Cypher must use 'n' as the primary node variable "
                    "so tenant scoping can be enforced."
                )
            if os.getenv("ENABLE_AST_REWRITER", "true").lower() == "true":
                try:
                    result = rewrite_cypher(
                        cypher,
                        RewriteConfig(
                            tenant_id=merged["tenantId"],
                            role=role,
                            forbidden_labels=["DuploInfra", "DuploPlan", "AWSAccount"],
                            enforce_primary_alias="n",
                        ),
                    )
                except TenantRewriteError as exc:
                    raise ValueError(f"Tenant safety enforcement failed: {exc}") from exc

                cypher = result.cypher
                if result.security_hints:
                    merged.setdefault("_debug_security_hints", result.security_hints)
            else:
                predicate = (
                    "EXISTS { (n)-[:IN_TENANT]->(:DuploTenant {id: $tenantId}) } "
                    "OR (n:DuploTenant AND n.id = $tenantId)"
                )
                cypher = _inject_where_clause(cypher, predicate)

        # Normalize legacy EXISTS() pattern syntax into subqueries compatible with Neo4j 5+
        cypher = _normalize_exists_patterns(cypher)

        safe_log_info(
            logger,
            "Tenant-scoped Cypher execution (role=%s tenant=%s)",
            role,
            merged.get("tenantId"),
        )
        safe_log_json(
            logger.info,
            "Cypher payload:\n%s",
            {
                "cypher": cypher,
                "params": {k: v for k, v in merged.items() if k != "_debug_security_hints"},
            },
        )

        if "_debug_security_hints" in merged:
            safe_log_json(
                logger.debug,
                "Tenant security hints:\n%s",
                merged["_debug_security_hints"],
            )

        return await run_cypher_query(cypher, merged)

    return ToolDefinition(
        name="run_cypher_query",
        description=(
            "Execute a read-only Cypher against Neo4j and return rows. "
            "Tenant scoping (strict): when role is 'user', a non-empty tenant_id must be provided and the query "
            "is executed inside a read-only subquery that is filtered to entities that have an IN_TENANT relationship "
            "to that tenant (EXISTS predicate). Requests without a tenant_id are rejected. "
            "When role is 'admin', do not apply tenant constraints. "
            "Primary variable must be 'n'."
        ),
        function=run_scoped_cypher_query,
    )


async def process_chat_request(
    payload: dict,
    request,
    system_prompt_text: str,
    request_id: str,
    provider_name: Optional[str] = None
) -> dict:
    """
    Process chat request using the configured agent provider.

    This function contains ALL our business logic and is completely
    framework-agnostic. It works with any AgentProvider implementation.

    Args:
        payload: Request payload with messages
        request: FastAPI request object
        system_prompt_text: System prompt template
        request_id: Unique request identifier
        provider_name: Override the default provider (for testing)

    Returns:
        dict: Response message with content, data, and metadata
    """
    set_request_id(request_id)

    # Get the configured agent provider
    provider = get_agent_provider(provider_name)

    client = "unknown"
    if request and hasattr(request, "client") and request.client:
        client = getattr(request.client, "host", "unknown")

    method = getattr(request, "method", "unknown") if request else "unknown"
    path = safe_get_nested({"request": request}, "request", "url", "path", default="/chat")

    safe_log_info(
        logger,
        "HTTP /chat request: method=%s path=%s client=%s request_id=%s provider=%s",
        method, path, client, request_id, provider.get_provider_name()
    )
    safe_log_json(logger.info, "HTTP /chat payload (full JSON):\n%s", payload)

    messages = payload.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="`messages` must be a non-empty list")

    history: list[dict] = messages[:-1]
    last_message: dict = messages[-1]

    # SCHEMA PERSISTENCE: Extract prior schema cache from raw history
    # NOTE: This MUST happen BEFORE _clean_messages_for_bedrock() which strips msg["data"]
    prior_schema_cache = _extract_accumulated_schema_cache(history)
    if prior_schema_cache:
        logger.info(
            "📦 Found prior schema cache: version=%s, tenant=%s, %d elements",
            prior_schema_cache.get("version"),
            prior_schema_cache.get("tenant_id"),
            len(prior_schema_cache.get("elements_by_id", {})),
        )

    # BUSINESS LOGIC: Clean message history (strips data, platform_context for LLM)
    cleaned_history = _clean_messages_for_bedrock(history)

    # BUSINESS LOGIC: Extract platform context
    ctx = _extract_platform_context(last_message)
    tenant_id_ctx = ctx.get("tenant_id", "")
    user_roles_ctx = ctx.get("user_roles", [])
    resolved_role = "Administrator" if "Administrator" in user_roles_ctx else "User"

    safe_log_json(logger.info, "Platform context:\n%s", ctx)

    # BUSINESS LOGIC: Dynamic schema selection with persistence (OUR COMPETITIVE ADVANTAGE)
    schema_start_time = time.perf_counter()
    selector = None
    schema_cache = {}

    try:
        selector = get_schema_selector()
        # Get raw elements for current query (for merging/caching)
        current_elements = selector.get_relevant_elements(last_message.get("content", ""))
        logger.info(f"🔍 Schema selection: found {len(current_elements)} elements for current query")

        # Merge with prior cache (handles tenant guardrails, deduplication)
        schema_cache = _merge_schema_cache(
            prior_cache=prior_schema_cache,
            current_elements=current_elements,
            tenant_id=tenant_id_ctx or None,
        )

        # Format merged schema for LLM injection
        merged_elements = list(schema_cache.get("elements_by_id", {}).values())
        schema_subset = selector.format_schema_for_llm(merged_elements)

        logger.info(
            f"📦 Schema cache updated: {len(merged_elements)} total elements "
            f"(prior={len(prior_schema_cache.get('elements_by_id', {}))}, "
            f"current={len(current_elements)})"
        )

    except RuntimeError as e:
        # Dynamic schema selection is an optimization. If ChromaDB is unavailable,
        # degrade gracefully: use prior cache if available, otherwise fallback.
        logger.warning(
            "Dynamic schema selection unavailable (%s). Falling back.",
            str(e),
        )
        if prior_schema_cache and prior_schema_cache.get("elements_by_id"):
            # Use prior cache only
            schema_cache = prior_schema_cache
            merged_elements = list(schema_cache.get("elements_by_id", {}).values())
            if selector:
                schema_subset = selector.format_schema_for_llm(merged_elements)
            else:
                schema_subset = "<!-- Schema from prior cache (ChromaDB unavailable) -->\n"
            logger.info(f"📦 Using prior schema cache: {len(merged_elements)} elements")
        else:
            schema_subset = "<!-- Schema selection unavailable - using fallback -->\n"
            schema_cache = {
                "version": SCHEMA_CACHE_VERSION,
                "tenant_id": tenant_id_ctx or None,
                "elements_by_id": {},
            }

    schema_elapsed_ms = (time.perf_counter() - schema_start_time) * 1000

    logger.info(f"⏱️  PERFORMANCE: Schema selection time: {schema_elapsed_ms:.2f}ms (request_id={request_id})")

    # BUSINESS LOGIC: Build effective system prompt
    # Replace schema placeholder with actual selected schema
    logger.info(f"📝 Schema injection: Replacing {{{{neo4j_schema}}}} placeholder with {len(schema_subset)} character schema")
    effective_system_prompt = system_prompt_text.replace(
        "{{neo4j_schema}}", schema_subset
    )

    # Verify schema was actually injected
    if "{{neo4j_schema}}" in effective_system_prompt:
        logger.error("❌ SCHEMA INJECTION FAILED: Placeholder {{neo4j_schema}} still present in prompt!")
    else:
        logger.info("✅ Schema injection verified: Placeholder replaced successfully")
        # Log a sample of the injected schema for verification
        schema_preview = schema_subset[:500] if len(schema_subset) > 500 else schema_subset
        logger.debug(f"Schema preview (first 500 chars): {schema_preview}...")

    # Add runtime context at the beginning (after the main title)
    runtime_context = (
        f"\n## Runtime Context (Current Request)\n\n"
        f"- **Role**: {resolved_role}\n"
        f"- **Tenant ID**: {tenant_id_ctx or '(none)'}\n"
        f"- **Tenant Name**: {ctx.get('tenant_name') or '(none)'}\n"
        f"- **Kubernetes Namespace**: {ctx.get('k8s_namespace') or '(none)'}\n"
        f"- **Primary Cypher Variable**: Must use `n` as the primary node variable\n"
    )

    # Insert runtime context after the first heading
    if effective_system_prompt.startswith("# "):
        first_line_end = effective_system_prompt.find("\n")
        if first_line_end != -1:
            effective_system_prompt = (
                effective_system_prompt[:first_line_end + 1] +
                runtime_context +
                effective_system_prompt[first_line_end + 1:]
            )
        else:
            # Fallback: just prepend
            effective_system_prompt = runtime_context + effective_system_prompt
    else:
        # No heading found, prepend runtime context
        effective_system_prompt = runtime_context + effective_system_prompt

    # BUSINESS LOGIC: Create tenant-scoped tool
    scoped_cypher_tool = make_scoped_cypher_tool(tenant_id=tenant_id_ctx, role=resolved_role)

    # Log final prompt stats before sending to LLM
    prompt_length = len(effective_system_prompt)
    prompt_lines = effective_system_prompt.count('\n') + 1
    logger.info(
        f"📤 Sending to LLM: {prompt_length} chars, {prompt_lines} lines, "
        f"{len(cleaned_history)} history messages"
    )

    # Log full system prompt (always)
    logger.info("=" * 80)
    logger.info("FULL SYSTEM PROMPT SENT TO LLM:")
    logger.info("=" * 80)
    logger.info(effective_system_prompt)
    logger.info("=" * 80)

    # Log if Runtime Context is present
    if "## Runtime Context" in effective_system_prompt:
        logger.info("✅ Runtime Context injection verified")
    else:
        logger.warning("⚠️  Runtime Context NOT found in prompt")

    # FRAMEWORK: Initialize agent using provider abstraction
    # Reasoning mode: When enabled, the model shows its "thinking" process
    # This can lead to more detailed, step-by-step responses with explicit analysis
    # DISABLED by default: Agno has known issues with reasoning + tools + Bedrock
    # causing "Expected toolResult blocks" ValidationException errors
    # Set ENABLE_REASONING=true to re-enable once Agno fixes this
    enable_reasoning = os.getenv("ENABLE_REASONING", "false").lower() == "true"

    logger.info(f"🧠 Reasoning mode: {'ENABLED' if enable_reasoning else 'DISABLED'}")

    agent = await provider.initialize_agent(
        system_prompt=effective_system_prompt,
        tools=[scoped_cypher_tool],
        message_history=cleaned_history,
        # Provider-specific options can be passed here
        reasoning=enable_reasoning,  # Set to True for more detailed responses with reasoning
        telemetry=True,
    )

    # FRAMEWORK: Run agent using provider abstraction
    agent_start_time = time.perf_counter()
    try:
        response = await provider.run_agent(
            agent=agent,
            user_message=last_message.get("content", "")
        )
        agent_elapsed_ms = (time.perf_counter() - agent_start_time) * 1000
        logger.info(
            f"⏱️  PERFORMANCE ({provider.get_provider_name().upper()}): "
            f"Agent invocation time: {agent_elapsed_ms:.2f}ms (request_id={request_id})"
        )
    except Exception as exc:
        agent_elapsed_ms = (time.perf_counter() - agent_start_time) * 1000
        logger.exception(
            f"{provider.get_provider_name().upper()} agent invocation failed "
            f"after {agent_elapsed_ms:.2f}ms (request_id={request_id})"
        )
        error_data = {
            "error": str(exc),
            "framework": provider.get_provider_name()
        }
        # Persist schema cache even on error so context isn't lost
        if schema_cache:
            error_data["schema_cache"] = schema_cache
        return {
            "role": "assistant",
            "content": "Sorry, the AI agent encountered an error while processing your request.",
            "data": error_data,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "_debug_agent_time_ms": agent_elapsed_ms,
        }

    # Extract content and data from provider response
    content = response.content
    data = response.metadata.copy()

    # Add metrics to data
    if response.metrics:
        data["_metrics"] = response.metrics

    # SCHEMA PERSISTENCE: Add schema cache to response for client-side persistence
    if schema_cache:
        data["schema_cache"] = schema_cache
        logger.info(
            f"📦 Persisting schema cache: version={schema_cache.get('version')}, "
            f"tenant={schema_cache.get('tenant_id')}, "
            f"elements={len(schema_cache.get('elements_by_id', {}))}"
        )

    # BUSINESS LOGIC: Mermaid PDF attachment (OUR FEATURE)
    content, data = attach_pdfs_from_mermaid(content, data, logger_override=logger)

    # BUSINESS LOGIC: Inject customer-specific styling into Mermaid diagrams
    # This happens AFTER LLM generation but BEFORE sending to user
    # Allows per-tenant style customization via ConfigMap
    # Run in thread pool to avoid blocking event loop (file I/O is synchronous)
    enable_styling_injection = os.getenv("ENABLE_DIAGRAM_STYLING_INJECTION", "true").lower() == "true"
    if enable_styling_injection and isinstance(content, str):
        content = await asyncio.to_thread(
            inject_styling_in_content,
            content=content,
            customer_id=tenant_id_ctx,  # Use tenant ID for customer-specific styling
            enabled=True
        )
        logger.info(f"✨ Injected custom styling for tenant: {tenant_id_ctx or 'default'}")

    safe_log_info(logger, "LLM reply content (full):\n%s", content)
    safe_log_json(logger.info, "LLM reply data (full):\n%s", data)

    response_message = {
        "role": "assistant",
        "content": content,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "_debug_effective_system_prompt": effective_system_prompt,
        "_debug_agent_time_ms": agent_elapsed_ms,
        "_debug_schema_selection_ms": schema_elapsed_ms,
        "_debug_framework": provider.get_provider_name(),
        "_debug_framework_version": provider.get_provider_version(),
    }

    safe_log_json(logger.info, "HTTP /chat response (full JSON):\n%s", response_message)

    return response_message

