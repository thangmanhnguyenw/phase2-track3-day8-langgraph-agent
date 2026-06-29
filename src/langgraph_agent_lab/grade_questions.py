"""Grade answers against grading_questions.json using policy retrieval simulation."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .graph import build_graph
from .persistence import build_checkpointer
from .state import Route, Scenario, initial_state


class GradingQuestion(BaseModel):
    id: str
    question: str
    must_contain_any: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    expect_top1_doc_id: str
    grading_criteria: list[str] = Field(default_factory=list)


class QuestionGradeResult(BaseModel):
    question_id: str
    question: str
    expect_top1_doc_id: str
    retrieved_doc_id: str
    retrieval_correct: bool
    answer: str
    route: str | None = None
    content_pass: bool
    forbidden_violations: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    success: bool
    grading_criteria: list[str] = Field(default_factory=list)


class GradingQuestionsReport(BaseModel):
    total_questions: int
    success_count: int
    success_rate: float
    retrieval_accuracy: float
    results: list[QuestionGradeResult]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return " ".join(text.split())


def load_grading_questions(path: str | Path) -> list[GradingQuestion]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GradingQuestion.model_validate(item) for item in payload]


def load_policy_docs(path: str | Path) -> dict[str, dict[str, str]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_content(answer: str, question: GradingQuestion) -> tuple[bool, list[str], list[str]]:
    normalized = _normalize(answer)
    if question.must_contain_any:
        matched = any(_normalize(phrase) in normalized for phrase in question.must_contain_any)
        missing = [] if matched else list(question.must_contain_any)
    else:
        missing = []
    forbidden = [
        phrase
        for phrase in question.must_not_contain
        if _normalize(phrase) in normalized
    ]
    return not missing and not forbidden, missing, forbidden


def grade_question_with_graph(
    question: GradingQuestion,
    policy_docs: dict[str, dict[str, str]],
    graph: Any,
) -> QuestionGradeResult:
    """Grade policy Q&A with simulated top-1 retrieval and grounded answer."""
    from .nodes import answer_node, finalize_node

    doc_id = question.expect_top1_doc_id
    doc = policy_docs[doc_id]
    scenario = Scenario(id=question.id, query=question.question, expected_route=Route.SIMPLE)
    state = initial_state(scenario)
    state["route"] = "simple"
    state["tool_results"] = [f"[{doc_id}] {doc['title']}: {doc['content']}"]
    answer_update = answer_node(state)
    merged = {**state, **answer_update}
    finalize_node(merged)
    answer = merged.get("final_answer") or ""
    content_pass, missing, forbidden = _check_content(answer, question)
    retrieval_correct = doc_id == question.expect_top1_doc_id
    return QuestionGradeResult(
        question_id=question.id,
        question=question.question,
        expect_top1_doc_id=question.expect_top1_doc_id,
        retrieved_doc_id=doc_id,
        retrieval_correct=retrieval_correct,
        answer=answer,
        route=merged.get("route"),
        content_pass=content_pass,
        forbidden_violations=forbidden,
        missing_required=missing,
        success=content_pass and retrieval_correct,
        grading_criteria=question.grading_criteria,
    )


def grade_questions(
    questions_path: str | Path,
    policy_docs_path: str | Path = "data/sample/policy_docs.json",
) -> GradingQuestionsReport:
    questions = load_grading_questions(questions_path)
    policy_docs = load_policy_docs(policy_docs_path)
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    results = [grade_question_with_graph(q, policy_docs, graph) for q in questions]
    success_count = sum(1 for item in results if item.success)
    retrieval_hits = sum(1 for item in results if item.retrieval_correct)
    total = len(results)
    return GradingQuestionsReport(
        total_questions=total,
        success_count=success_count,
        success_rate=success_count / total if total else 0.0,
        retrieval_accuracy=retrieval_hits / total if total else 0.0,
        results=results,
    )


def write_grading_results(report: GradingQuestionsReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")


def render_grading_section(report: GradingQuestionsReport) -> str:
    rows = "\n".join(
        f"| {r.question_id} | {r.expect_top1_doc_id} | "
        f"{'✓' if r.retrieval_correct else '✗'} | "
        f"{'✓' if r.content_pass else '✗'} | "
        f"{'✓' if r.success else '✗'} |"
        for r in report.results
    )
    detail_blocks = []
    for r in report.results:
        criteria = "; ".join(r.grading_criteria)
        detail_blocks.append(
            f"### {r.question_id}\n"
            f"- **Câu hỏi:** {r.question}\n"
            f"- **Route:** {r.route or '-'}\n"
            f"- **Retrieved doc:** {r.retrieved_doc_id}\n"
            f"- **Kết quả:** {'PASS' if r.success else 'FAIL'}\n"
            f"- **Tiêu chí:** {criteria}\n"
            f"- **Trả lời:** {r.answer[:300]}{'...' if len(r.answer) > 300 else ''}\n"
            + (
                f"- **Thiếu:** {', '.join(r.missing_required)}\n" if r.missing_required else ""
            )
            + (
                f"- **Vi phạm cấm:** {', '.join(r.forbidden_violations)}\n"
                if r.forbidden_violations
                else ""
            )
        )
    details = "\n".join(detail_blocks)
    return f"""## 9. Grading questions (`grading_questions.json`)

| Metric | Value |
|---|---|
| Total questions | {report.total_questions} |
| Success count | {report.success_count} |
| Success rate | {report.success_rate:.1%} |
| Retrieval accuracy (top-1) | {report.retrieval_accuracy:.1%} |

| ID | Expected doc | Retrieval | Content | Overall |
|---|---|---|---|---|
{rows}

### Chi tiết từng câu

{details}
"""


def append_grading_to_report(
    report_path: str | Path,
    grading_report: GradingQuestionsReport,
) -> None:
    path = Path(report_path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = "## 9. Grading questions"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n\n"
    path.write_text(text + render_grading_section(grading_report) + "\n", encoding="utf-8")
