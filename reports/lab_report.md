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

## 9. Grading questions (`grading_questions.json`)

| Metric | Value |
|---|---|
| Total questions | 10 |
| Success count | 10 |
| Success rate | 100.0% |
| Retrieval accuracy (top-1) | 100.0% |

| ID | Expected doc | Retrieval | Content | Overall |
|---|---|---|---|---|
| gq_d10_01 | policy_refund_v4 | ✓ | ✓ | ✓ |
| gq_d10_02 | policy_refund_v4 | ✓ | ✓ | ✓ |
| gq_d10_03 | policy_refund_v4 | ✓ | ✓ | ✓ |
| gq_d10_04 | sla_p1_2026 | ✓ | ✓ | ✓ |
| gq_d10_05 | sla_p1_2026 | ✓ | ✓ | ✓ |
| gq_d10_06 | sla_p1_2026 | ✓ | ✓ | ✓ |
| gq_d10_07 | it_helpdesk_faq | ✓ | ✓ | ✓ |
| gq_d10_08 | it_helpdesk_faq | ✓ | ✓ | ✓ |
| gq_d10_09 | hr_leave_policy | ✓ | ✓ | ✓ |
| gq_d10_10 | access_control_sop | ✓ | ✓ | ✓ |

### Chi tiết từng câu

### gq_d10_01
- **Câu hỏi:** Theo chính sách hoàn tiền hiện hành, khách hàng có tối đa bao nhiêu ngày làm việc để gửi yêu cầu hoàn tiền sau khi đơn được xác nhận?
- **Route:** simple
- **Retrieved doc:** policy_refund_v4
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 7 ngày làm việc; Không chấp nhận 14 ngày là chính sách hiện hành; Top-1 retrieval nên đến từ policy_refund_v4
- **Trả lời:** Chào bạn,

Theo chính sách hoàn tiền hiện hành, khách hàng có tối đa 7 ngày làm việc để gửi yêu cầu hoàn tiền sau khi đơn được xác nhận. Xin lưu ý rằng các sản phẩm như hàng kỹ thuật số, license key, và subscription không đủ điều kiện hoàn tiền.

Nếu bạn cần thêm thông tin, vui lòng cho chúng tôi bi...

### gq_d10_02
- **Câu hỏi:** Đâu là loại sản phẩm bị loại khỏi điều kiện hoàn tiền?
- **Route:** simple
- **Retrieved doc:** policy_refund_v4
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng nhóm sản phẩm không được hoàn tiền; Không lấy ngoại lệ chung ngẫu nhiên
- **Trả lời:** Chào bạn,

Các sản phẩm bị loại khỏi điều kiện hoàn tiền bao gồm hàng kỹ thuật số, license key và subscription. Nếu bạn cần thêm thông tin, vui lòng cho chúng tôi biết.

Trân trọng!

### gq_d10_03
- **Câu hỏi:** Finance Team xử lý yêu cầu hoàn tiền trong bao lâu?
- **Route:** simple
- **Retrieved doc:** policy_refund_v4
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng thời gian xử lý 3-5 ngày làm việc; Phải là thông tin từ policy_refund_v4
- **Trả lời:** Chào bạn,

Finance Team sẽ xử lý yêu cầu hoàn tiền trong khoảng 3-5 ngày làm việc. Bạn cần lưu ý rằng bạn có tối đa 7 ngày làm việc để gửi yêu cầu hoàn tiền sau khi đơn hàng được xác nhận. Các sản phẩm không đủ điều kiện hoàn tiền bao gồm hàng kỹ thuật số, license key, và subscription.

Nếu bạn cần ...

### gq_d10_04
- **Câu hỏi:** SLA phản hồi ban đầu cho ticket P1 là bao lâu?
- **Route:** simple
- **Retrieved doc:** sla_p1_2026
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 15 phút; Top-1 retrieval nên là sla_p1_2026
- **Trả lời:** SLA phản hồi ban đầu cho ticket P1 là 15 phút. Nếu không có phản hồi sau 10 phút, hệ thống sẽ tự động escalated.

### gq_d10_05
- **Câu hỏi:** SLA resolution cho ticket P1 là bao nhiêu giờ?
- **Route:** simple
- **Retrieved doc:** sla_p1_2026
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 4 giờ; Top-1 retrieval nên là sla_p1_2026
- **Trả lời:** SLA resolution cho ticket P1 là 4 giờ. Nếu không có phản hồi sau 10 phút, hệ thống sẽ tự động escalated.

### gq_d10_06
- **Câu hỏi:** Nếu không có phản hồi với ticket P1 sau bao lâu thì hệ thống auto escalate?
- **Route:** simple
- **Retrieved doc:** sla_p1_2026
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 10 phút; Không trả lời sai giá trị escalation
- **Trả lời:** Chào bạn,

Theo quy định, nếu không có phản hồi với ticket P1 sau 10 phút, hệ thống sẽ tự động tiến hành escalated.

Nếu bạn cần thêm thông tin, vui lòng cho tôi biết.

Trân trọng!

### gq_d10_07
- **Câu hỏi:** Tài khoản bị khóa sau bao nhiêu lần đăng nhập sai liên tiếp?
- **Route:** simple
- **Retrieved doc:** it_helpdesk_faq
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 5 lần; Top-1 retrieval nên là it_helpdesk_faq
- **Trả lời:** Tài khoản của bạn sẽ bị khóa sau 5 lần đăng nhập sai liên tiếp. Nếu bạn cần thêm hỗ trợ, vui lòng cho chúng tôi biết.

### gq_d10_08
- **Câu hỏi:** VPN cho phép kết nối tối đa bao nhiêu thiết bị cùng lúc?
- **Route:** simple
- **Retrieved doc:** it_helpdesk_faq
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng giới hạn 2 thiết bị; Không lấy thông tin từ tài liệu khác
- **Trả lời:** Chào bạn,

VPN cho phép kết nối tối đa 2 thiết bị cùng lúc. Nếu bạn cần thêm thông tin, vui lòng cho tôi biết.

Trân trọng!

### gq_d10_09
- **Câu hỏi:** Nhân viên dưới 3 năm kinh nghiệm được bao nhiêu ngày phép năm theo chính sách HR 2026?
- **Route:** simple
- **Retrieved doc:** hr_leave_policy
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng 12 ngày phép năm; Không chấp nhận 10 ngày phép năm (bản HR 2025); Top-1 retrieval nên là hr_leave_policy
- **Trả lời:** Theo chính sách HR 2026, nhân viên dưới 3 năm kinh nghiệm được 12 ngày phép năm.

### gq_d10_10
- **Câu hỏi:** Level 4 Admin Access yêu cầu phê duyệt bởi ai?
- **Route:** simple
- **Retrieved doc:** access_control_sop
- **Kết quả:** PASS
- **Tiêu chí:** Nêu đúng IT Manager và/hoặc CISO; Top-1 retrieval nên là access_control_sop
- **Trả lời:** Level 4 Admin Access requires approval from the IT Manager and the CISO. If you have any further questions, feel free to ask.


