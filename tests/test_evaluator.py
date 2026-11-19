from src.evaluator import evaluate_submission
from src.schemas import Finding, Policy, TruthIssue


def _sample_policy() -> Policy:
    return Policy(
        fx_date_rule="transaction_date",
        period_boundary_rule="strict_local_timezone",
        rounding_rule="HALF_UP",
        amount_tolerance_minor=5,
    )


def _sample_truth() -> list[TruthIssue]:
    return [
        TruthIssue(
            issue_id="ISS-1",
            type="duplicate_invoice",
            affected_ids=["INV-1", "INV-2"],
            expected_amount_minor=10000,
            currency="KZT",
            valid_evidence_sets=[["DOC-1", "DOC-2"], ["ROW-1", "ROW-2"]],
        )
    ]


def test_perfect_match_and_step_penalty():
    res = evaluate_submission(
        raw_submission={
            "episode_id": "ep1",
            "findings": [
                {
                    "type": "duplicate_invoice",
                    "affected_ids": ["INV-2", "INV-1"],  # другой порядок ID
                    "claimed_amount_minor": 10003,       # в пределах допуска 5
                    "currency": "KZT",
                    "evidence_ids": ["DOC-2", "DOC-1", "EXTRA-DOC"],
                    "explanation": "Duplicate invoice detected",
                }
            ],
        },
        expected_episode_id="ep1",
        truth_issues=_sample_truth(),
        policy=_sample_policy(),
        inspection_steps=10,
    )
    assert res["valid"] is True
    assert res["tp"] == 1 and res["fp"] == 0 and res["fn"] == 0
    assert res["f1"] == 1.0
    assert abs(res["reward"] - 0.98) < 1e-6


def test_duplicate_finding_rejected():
    finding = Finding(
        type="duplicate_invoice",
        affected_ids=["INV-1", "INV-2"],
        claimed_amount_minor=10000,
        currency="KZT",
        evidence_ids=["DOC-1", "DOC-2"],
        explanation="Dup",
    )
    res = evaluate_submission(
        raw_submission={"episode_id": "ep1", "findings": [finding.model_dump(), finding.model_dump()]},
        expected_episode_id="ep1",
        truth_issues=_sample_truth(),
        policy=_sample_policy(),
        inspection_steps=5,
    )
    assert res["tp"] == 1 and res["fp"] == 1 and res["fn"] == 0
    assert res["f1"] < 1.0


def test_clean_books_silence_vs_false_accusation():
    silence = evaluate_submission(
        raw_submission={"episode_id": "ep_clean", "findings": []},
        expected_episode_id="ep_clean",
        truth_issues=[],
        policy=_sample_policy(),
        inspection_steps=5,
    )
    assert silence["f1"] == 1.0
    assert silence["reward"] > 0.9

    false_alarm = evaluate_submission(
        raw_submission={
            "episode_id": "ep_clean",
            "findings": [
                {
                    "type": "duplicate_invoice",
                    "affected_ids": ["INV-1"],
                    "claimed_amount_minor": 1000,
                    "currency": "KZT",
                    "evidence_ids": ["DOC-1"],
                    "explanation": "Fake",
                }
            ],
        },
        expected_episode_id="ep_clean",
        truth_issues=[],
        policy=_sample_policy(),
        inspection_steps=5,
    )
    assert false_alarm["f1"] == 0.0
    assert false_alarm["reward"] == -1.0
