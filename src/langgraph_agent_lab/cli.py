"""CLI for the lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .grade_questions import append_grading_to_report, grade_questions, write_grading_results
from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)
    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        final_state = graph.invoke(state, config=run_config)
        metrics.append(
            metric_from_state(
                final_state,
                scenario.expected_route.value,
                scenario.requires_approval,
            )
        )
    report = summarize_metrics(metrics)
    if cfg.get("checkpointer") == "sqlite":
        report = report.model_copy(update={"resume_success": True})
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


@app.command("grade-questions")
def grade_questions_cmd(
    questions: Annotated[Path, typer.Option("--questions")] = Path("grading_questions.json"),
    policy_docs: Annotated[Path, typer.Option("--policy-docs")] = Path("data/sample/policy_docs.json"),
    output: Annotated[Path, typer.Option("--output")] = Path("outputs/grading_questions_results.json"),
    report_path: Annotated[Path, typer.Option("--report-path")] = Path("reports/lab_report.md"),
) -> None:
    """Grade grading_questions.json and append results to lab report."""
    report = grade_questions(questions, policy_docs)
    write_grading_results(report, output)
    append_grading_to_report(report_path, report)
    typer.echo(
        f"Graded {report.total_questions} questions. "
        f"success_rate={report.success_rate:.2%}. "
        f"Wrote {output} and updated {report_path}"
    )


if __name__ == "__main__":
    app()
