"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.
"""

from __future__ import annotations

import os
import time
from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


class ClassificationResult(BaseModel):
    """Structured LLM output for intent classification."""

    route: Literal["simple", "tool", "missing_info", "risky", "error"]
    reasoning: str = Field(description="Brief explanation for the chosen route")


CLASSIFY_SYSTEM_PROMPT = """You are a support-ticket intent classifier.
Classify the user query into exactly one route.

Priority (highest first): risky > tool > missing_info > error > simple

Routes:
- risky: Side-effect actions — refunds, deletions, cancellations, sending emails, account changes
- tool: Information lookups — order status, tracking, search, fetch data
- missing_info: Vague or incomplete queries lacking actionable context (e.g. "Can you fix it?")
- error: System failures — timeouts, crashes, service unavailable, processing failures
- simple: General questions answerable without tools or risky actions (password reset, FAQs)

Return only the structured classification."""


def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM with structured output."""
    query = state.get("query", "")
    llm = get_llm().with_structured_output(ClassificationResult)
    start = time.perf_counter()
    result: ClassificationResult = llm.invoke(
        [
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this support ticket:\n\n{query}"},
        ]
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    risk_level = "high" if result.route == "risky" else "low"
    return {
        "route": result.route,
        "risk_level": risk_level,
        "events": [
            make_event(
                "classify",
                "completed",
                f"route={result.route}",
                reasoning=result.reasoning,
                latency_ms=latency_ms,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call with transient failure simulation for error routes."""
    route = state.get("route", "")
    attempt = state.get("attempt", 0)
    query = state.get("query", "")

    if route == "error" and attempt < 2:
        result = f"ERROR: Transient failure processing request (attempt {attempt + 1})"
    elif route == "risky":
        action = state.get("proposed_action", query)
        result = f"SUCCESS: Risky action executed — {action[:80]}"
    elif route == "tool" or "order" in query.lower() or "lookup" in query.lower():
        order_id = "".join(ch for ch in query if ch.isdigit()) or "unknown"
        result = f"SUCCESS: Order {order_id} status is SHIPPED, ETA 2 business days"
    else:
        result = f"SUCCESS: Tool completed for query — {query[:60]}"

    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", result[:100])],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — retry-loop gate using heuristic (ERROR substring check)."""
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    evaluation_result = "needs_retry" if "ERROR" in latest.upper() else "success"
    return {
        "evaluation_result": evaluation_result,
        "events": [
            make_event(
                "evaluate",
                "completed",
                f"evaluation={evaluation_result}",
                latest_result=latest[:80],
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM grounded in context."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")
    route = state.get("route", "")

    context_parts = [f"User query: {query}", f"Route: {route}"]
    if tool_results:
        context_parts.append(f"Tool results: {'; '.join(tool_results)}")
    if approval:
        context_parts.append(
            f"Approval: approved={approval.get('approved')}, reviewer={approval.get('reviewer')}"
        )
    context = "\n".join(context_parts)

    llm = get_llm()
    start = time.perf_counter()
    response = llm.invoke(
        [
            {
                "role": "system",
                "content": (
                    "You are a helpful support agent. Write a concise, professional reply "
                    "grounded ONLY in the provided context. Do not invent data."
                ),
            },
            {"role": "user", "content": f"Context:\n{context}\n\nWrite the support reply:"},
        ]
    )
    latency_ms = int((time.perf_counter() - start) * 1000)
    final_answer = response.content if hasattr(response, "content") else str(response)

    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "response generated", latency_ms=latency_ms)],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    pending_question = (
        f"Could you provide more details about your request? "
        f'Your message "{query}" is too vague for me to help effectively. '
        f"Please specify what needs to be fixed, which account or order is involved, "
        f"and any error messages you see."
    )
    return {
        "pending_question": pending_question,
        "final_answer": pending_question,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    proposed_action = f"Proposed risky action requiring approval: {query}"
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", proposed_action[:80])],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step with mock default or real interrupt."""
    proposed = state.get("proposed_action", state.get("query", ""))
    use_interrupt = os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true"

    if use_interrupt:
        from langgraph.types import interrupt

        payload = {"action": "approve_risky_action", "proposed_action": proposed}
        decision = interrupt(payload)
        if isinstance(decision, dict):
            approved = bool(decision.get("approved", False))
            reviewer = decision.get("reviewer", "human-reviewer")
            comment = decision.get("comment", "")
        else:
            approved = bool(decision)
            reviewer = "human-reviewer"
            comment = ""
    else:
        approved = True
        reviewer = "mock-reviewer"
        comment = "Auto-approved for offline/CI runs"

    approval = {"approved": approved, "reviewer": reviewer, "comment": comment}
    return {
        "approval": approval,
        "events": [
            make_event(
                "approval",
                "interrupt" if use_interrupt else "completed",
                f"approved={approved}",
                reviewer=reviewer,
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt and increment the attempt counter."""
    attempt = state.get("attempt", 0) + 1
    error_msg = f"Transient failure on attempt {attempt}, scheduling retry"
    return {
        "attempt": attempt,
        "errors": [error_msg],
        "events": [make_event("retry", "completed", error_msg, attempt=attempt)],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    errors = state.get("errors", [])
    final_answer = (
        f"Unable to complete your request after {attempt} attempt(s) "
        f"(limit: {max_attempts}). The issue has been escalated to engineering. "
        f"Reference: {state.get('scenario_id', 'unknown')}. "
        f"Errors: {'; '.join(errors[-3:]) if errors else 'max retries exceeded'}"
    )
    return {
        "final_answer": final_answer,
        "events": [
            make_event("dead_letter", "completed", "request escalated to dead letter queue"),
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [
            make_event(
                "finalize",
                "completed",
                "workflow finished",
                route=state.get("route", ""),
                has_answer=bool(state.get("final_answer") or state.get("pending_question")),
            )
        ]
    }
