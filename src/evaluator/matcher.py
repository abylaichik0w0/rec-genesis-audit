from typing import Tuple
from src.schemas import Finding, Policy, TruthIssue


def _is_single_match(finding: Finding, truth: TruthIssue, tolerance_minor: int) -> bool:
    """Проверяет совпадение одного вывода агента с одной эталонной ошибкой по 5 правилам ТЗ."""
    # 1. Тип ошибки
    if finding.type != truth.type:
        return False

    # 2. Канонический список affected_ids (без учёта порядка и дубликатов внутри списка)
    if sorted(set(finding.affected_ids)) != sorted(set(truth.affected_ids)):
        return False

    # 3. Точное совпадение валюты
    if finding.currency != truth.currency:
        return False

    # 4. Сумма в пределах допуска policy.json
    if abs(finding.claimed_amount_minor - truth.expected_amount_minor) > tolerance_minor:
        return False

    # 5. Наличие хотя бы одного полного допустимого набора доказательств
    submitted_evidence = set(finding.evidence_ids)
    has_valid_evidence = any(
        set(req_set).issubset(submitted_evidence)
        for req_set in truth.valid_evidence_sets
    )
    if not has_valid_evidence:
        return False

    return True


def match_findings(
    findings: list[Finding],
    truth_issues: list[TruthIssue],
    policy: Policy,
) -> Tuple[int, int, int]:
    """
    Взаимно однозначное сопоставление выводов агента с эталоном.
    Повторные выводы на уже сопоставленный TruthIssue отклоняются и идут в FP.
    Возвращает (TP, FP, FN).
    """
    matched_truth_indices: set[int] = set()
    tp = 0
    fp = 0

    for finding in findings:
        matched_idx = None
        for idx, truth in enumerate(truth_issues):
            if idx in matched_truth_indices:
                continue
            if _is_single_match(finding, truth, policy.amount_tolerance_minor):
                matched_idx = idx
                break

        if matched_idx is not None:
            matched_truth_indices.add(matched_idx)
            tp += 1
        else:
            fp += 1

    fn = len(truth_issues) - len(matched_truth_indices)
    return tp, fp, fn
