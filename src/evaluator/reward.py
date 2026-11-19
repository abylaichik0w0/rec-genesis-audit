from dataclasses import is_dataclass
from typing import Any
from src.schemas import Finding, FindingsSubmission, Policy, TruthIssue
from .matcher import match_findings


def _parse_submission(raw: dict[str, Any] | FindingsSubmission) -> FindingsSubmission:
    """Валидирует входной словарь или dataclass в FindingsSubmission со строгой проверкой типов."""
    if isinstance(raw, FindingsSubmission):
        sub = raw
    elif isinstance(raw, dict):
        allowed_top = {"episode_id", "findings"}
        if set(raw.keys()) != allowed_top:
            raise ValueError(f"Invalid submission keys: {set(raw.keys())}")
        if not isinstance(raw["episode_id"], str) or not isinstance(raw["findings"], list):
            raise ValueError("Invalid types for episode_id or findings")

        parsed_findings: list[Finding] = []
        for item in raw["findings"]:
            if isinstance(item, Finding):
                parsed_findings.append(item)
                continue
            if not isinstance(item, dict):
                raise ValueError("Finding must be a dict")
            # Строгая проверка: int (и не bool) для claimed_amount_minor
            amt = item.get("claimed_amount_minor")
            if isinstance(amt, bool) or not isinstance(amt, int):
                raise ValueError("claimed_amount_minor must be int")
            parsed_findings.append(Finding(**item))

        sub = FindingsSubmission(episode_id=raw["episode_id"], findings=parsed_findings)
    else:
        raise ValueError("Unsupported submission format")

    for f in sub.findings:
        if isinstance(f.claimed_amount_minor, bool) or not isinstance(f.claimed_amount_minor, int):
            raise ValueError("claimed_amount_minor must be int")
    return sub


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
        submission = _parse_submission(raw_submission)
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "valid": False,
            "error": f"Schema validation error: {exc}",
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
