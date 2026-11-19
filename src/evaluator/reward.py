from typing import Any
from pydantic import ValidationError
from src.schemas import FindingsSubmission, Policy, TruthIssue
from .matcher import match_findings


def compute_metrics(
    tp: int,
    fp: int,
    fn: int,
    truth_is_empty: bool,
    findings_is_empty: bool,
) -> dict[str, float]:
    """Расчёт P, R, F1 по правилам раздела 05 ТЗ (включая чистые книги)."""
    if truth_is_empty:
        if findings_is_empty:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    denom = 2 * tp + fp + fn
    f1 = (2 * tp) / denom if denom > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_submission(
    raw_submission: dict[str, Any] | FindingsSubmission,
    expected_episode_id: str,
    truth_issues: list[TruthIssue],
    policy: Policy,
    inspection_steps: int,
) -> dict[str, Any]:
    """
    Валидирует ответ агента и вычисляет терминальную награду:
    clip(2 * F1 - 1 - 0.002 * inspection_steps, -1.0, 1.0).
    При нарушении схемы или чужом episode_id возвращает награду -1.0.
    """
    try:
        if isinstance(raw_submission, FindingsSubmission):
            submission = raw_submission
        else:
            submission = FindingsSubmission.model_validate(raw_submission)
    except ValidationError as exc:
        return {
            "valid": False,
            "error": f"Schema validation error: {exc.errors()}",
            "tp": 0,
            "fp": 0,
            "fn": len(truth_issues),
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "reward": -1.0,
        }

    if submission.episode_id != expected_episode_id:
        return {
            "valid": False,
            "error": f"Episode ID mismatch: expected {expected_episode_id}, got {submission.episode_id}",
            "tp": 0,
            "fp": 0,
            "fn": len(truth_issues),
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "reward": -1.0,
        }

    tp, fp, fn = match_findings(submission.findings, truth_issues, policy)
    metrics = compute_metrics(
        tp=tp,
        fp=fp,
        fn=fn,
        truth_is_empty=(len(truth_issues) == 0),
        findings_is_empty=(len(submission.findings) == 0),
    )

    raw_reward = 2.0 * metrics["f1"] - 1.0 - 0.002 * max(0, inspection_steps)
    clipped_reward = max(-1.0, min(1.0, raw_reward))

    return {
        "valid": True,
        "error": None,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "reward": clipped_reward,
    }
