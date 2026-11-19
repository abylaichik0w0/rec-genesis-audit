from src.evaluator import evaluate_submission
from src.generator import generate_episode, permute_episode


def test_clean_company_debit_equals_credit():
    ep = generate_episode(seed=42, episode_id="ep_clean_42", scenario_mode="clean")
    total_debit = sum(r.debit_minor for r in ep["ledger"])
    total_credit = sum(r.credit_minor for r in ep["ledger"])
    assert total_debit == total_credit
    assert len(ep["truth"]) == 0


def test_full_anomalies_and_oracle_score():
    ep = generate_episode(seed=101, episode_id="ep_full_101", scenario_mode="full")
    total_debit = sum(r.debit_minor for r in ep["ledger"])
    total_credit = sum(r.credit_minor for r in ep["ledger"])
    assert total_debit == total_credit
    assert len(ep["truth"]) == 8  # 4 базовых + 4 из 2 комбо-сценариев

    oracle_findings = [
        {
            "type": t.type,
            "affected_ids": t.affected_ids,
            "claimed_amount_minor": t.expected_amount_minor,
            "currency": t.currency,
            "evidence_ids": t.valid_evidence_sets[0],
            "explanation": f"Oracle finding for {t.issue_id}",
        }
        for t in ep["truth"]
    ]
    res = evaluate_submission(
        raw_submission={"episode_id": "ep_full_101", "findings": oracle_findings},
        expected_episode_id="ep_full_101",
        truth_issues=ep["truth"],
        policy=ep["policy"],
        inspection_steps=10,
    )
    assert res["f1"] == 1.0
    assert abs(res["reward"] - 0.98) < 1e-6


def test_isomorphic_permutation_preserves_oracle():
    ep1 = generate_episode(seed=77, episode_id="ep_iso_77", scenario_mode="full")
    ep2 = permute_episode(ep1, perm_seed=555)

    assert [r.row_id for r in ep1["ledger"]] != [r.row_id for r in ep2["ledger"]]

    oracle_findings_2 = [
        {
            "type": t.type,
            "affected_ids": t.affected_ids,
            "claimed_amount_minor": t.expected_amount_minor,
            "currency": t.currency,
            "evidence_ids": t.valid_evidence_sets[0],
            "explanation": "Oracle after permutation",
        }
        for t in ep2["truth"]
    ]
    res = evaluate_submission(
        raw_submission={"episode_id": "ep_iso_77", "findings": oracle_findings_2},
        expected_episode_id="ep_iso_77",
        truth_issues=ep2["truth"],
        policy=ep2["policy"],
        inspection_steps=10,
    )
    assert res["f1"] == 1.0
