"""Report generation helper."""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data."""
    scenario_rows = "\n".join(
        f"| {m.scenario_id} | {m.expected_route} | {m.actual_route or '-'} | "
        f"{'✓' if m.success else '✗'} | {m.retry_count} | {m.interrupt_count} |"
        for m in metrics.scenario_metrics
    )

    return f"""# Day 08 Lab Report — LangGraph Agent

## 1. Team / student

- Name: Student
- Repo/commit: phase2-track3-day8-langgraph-agent
- Date: 2026-06-29

## 2. Architecture

The workflow is a **StateGraph** with 11 nodes and conditional routing:

```
START → intake → classify → [route]
  simple       → answer → finalize → END
  tool         → tool → evaluate → [retry loop | answer] → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → tool → evaluate → answer → finalize → END
  error        → retry → tool → evaluate → [retry | dead_letter] → finalize → END
```

**Key design choices:**
- `classify_node` uses LLM structured output (Pydantic) — no keyword hard-coding
- `answer_node` uses LLM grounded in tool_results and approval context
- Retry loop is bounded via `attempt < max_attempts` in `route_after_retry`
- SQLite checkpointer with WAL mode for persistence extension

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| messages | append (`add`) | Audit conversation trail |
| tool_results | append (`add`) | Accumulate tool outputs across retries |
| errors | append (`add`) | Track transient failures |
| events | append (`add`) | Node visit audit for metrics |
| route | overwrite | Current classification only |
| attempt | overwrite | Retry counter |
| evaluation_result | overwrite | Retry-loop gate |
| approval | overwrite | Latest HITL decision |
| final_answer | overwrite | Single response per run |

## 4. Scenario results

| Metric | Value |
|---|---|
| Total scenarios | {metrics.total_scenarios} |
| Success rate | {metrics.success_rate:.1%} |
| Avg nodes visited | {metrics.avg_nodes_visited:.1f} |
| Total retries | {metrics.total_retries} |
| Total interrupts (HITL) | {metrics.total_interrupts} |
| Resume success | {metrics.resume_success} |

| Scenario | Expected | Actual | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
{scenario_rows}

## 5. Failure analysis

1. **Retry / tool failure**: Error-route scenarios simulate transient `ERROR` responses when `attempt < 2`. The evaluate node detects `ERROR` in tool output and routes to retry. S07 (`max_attempts=1`) exhausts immediately → dead_letter without unbounded loops.

2. **Risky action without approval**: Risky routes (refunds, deletions) pass through `risky_action` → `approval` before tool execution. Metrics track `approval_required` vs `approval_observed`. Rejected approval routes to clarify instead of executing the action.

## 6. Persistence / recovery evidence

- **Checkpointer**: SQLite (`SqliteSaver`) with WAL journal mode on `checkpoints.db`
- **thread_id**: Each scenario uses `thread-{{scenario_id}}` for isolated checkpoint threads
- **State history**: Checkpoints survive across `graph.invoke` calls; `resume_success=true` when sqlite backend is used
- Extension: set `LANGGRAPH_INTERRUPT=true` for real HITL via `interrupt()`

## 7. Extension work

- SQLite persistence with WAL mode (`persistence.py`)
- Optional real HITL via `LANGGRAPH_INTERRUPT` env var
- Graph can export Mermaid: `build_graph().get_graph().draw_mermaid()`

## 8. Improvement plan

With one more day: add Streamlit UI for approval interrupts, Postgres checkpointer for multi-worker deployments, and OpenTelemetry tracing on each node event.
"""


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
