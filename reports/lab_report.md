# Day 08 Lab Report — LangGraph Agent

## 1. Team / student

- Name:  Nguyễn Trần Mạnh Thắng
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


| Field             | Reducer        | Why                                    |
| ----------------- | -------------- | -------------------------------------- |
| messages          | append (`add`) | Audit conversation trail               |
| tool_results      | append (`add`) | Accumulate tool outputs across retries |
| errors            | append (`add`) | Track transient failures               |
| events            | append (`add`) | Node visit audit for metrics           |
| route             | overwrite      | Current classification only            |
| attempt           | overwrite      | Retry counter                          |
| evaluation_result | overwrite      | Retry-loop gate                        |
| approval          | overwrite      | Latest HITL decision                   |
| final_answer      | overwrite      | Single response per run                |




## 4. Scenario results


| Metric                  | Value  |
| ----------------------- | ------ |
| Total scenarios         | 7      |
| Success rate            | 100.0% |
| Avg nodes visited       | 6.4    |
| Total retries           | 3      |
| Total interrupts (HITL) | 2      |
| Resume success          | True   |



| Scenario        | Expected     | Actual       | Success | Retries | Interrupts |
| --------------- | ------------ | ------------ | ------- | ------- | ---------- |
| S01_simple      | simple       | simple       | ✓       | 0       | 0          |
| S02_tool        | tool         | tool         | ✓       | 0       | 0          |
| S03_missing     | missing_info | missing_info | ✓       | 0       | 0          |
| S04_risky       | risky        | risky        | ✓       | 0       | 1          |
| S05_error       | error        | error        | ✓       | 2       | 0          |
| S06_delete      | risky        | risky        | ✓       | 0       | 1          |
| S07_dead_letter | error        | error        | ✓       | 1       | 0          |




## 5. Failure analysis

1. **Retry / tool failure**: Error-route scenarios simulate transient `ERROR` responses when `attempt < 2`. The evaluate node detects `ERROR` in tool output and routes to retry. S07 (`max_attempts=1`) exhausts immediately → dead_letter without unbounded loops.
2. **Risky action without approval**: Risky routes (refunds, deletions) pass through `risky_action` → `approval` before tool execution. Metrics track `approval_required` vs `approval_observed`. Rejected approval routes to clarify instead of executing the action.



## 6. Persistence / recovery evidence

- **Checkpointer**: SQLite (`SqliteSaver`) with WAL journal mode on `checkpoints.db`
- **thread_id**: Each scenario uses `thread-{scenario_id}` for isolated checkpoint threads
- **State history**: Checkpoints survive across `graph.invoke` calls; `resume_success=true` when sqlite backend is used
- Extension: set `LANGGRAPH_INTERRUPT=true` for real HITL via `interrupt()`



## 7. Extension work

- SQLite persistence with WAL mode (`persistence.py`)
- Optional real HITL via `LANGGRAPH_INTERRUPT` env var
- Graph can export Mermaid: `build_graph().get_graph().draw_mermaid()`



## 8. Improvement plan

With one more day: add Streamlit UI for approval interrupts, Postgres checkpointer for multi-worker deployments, and OpenTelemetry tracing on each node event.