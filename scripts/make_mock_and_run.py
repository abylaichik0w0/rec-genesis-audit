import csv
import json
from pathlib import Path

from src.env.audit_env import AuditEnv
from src.policies.policies import MarkAllAttackPolicy, OraclePolicy, RandomPolicy, RuleBasedPolicy

# 1. Создаём минимальный валидный тестовый эпизод data/mock_ep
ep_dir = Path("data/mock_ep")
ep_dir.mkdir(parents=True, exist_ok=True)

(ep_dir / "manifest.json").write_text(
    json.dumps({
        "schema_version": "1.0",
        "episode_id": "ep_mock_001",
        "base_currency": "USD",
        "period_start": "2026-10-01T00:00:00+00:00",
        "period_end": "2026-10-31T23:59:59+00:00",
        "timezone": "UTC",
        "record_counts": {"ledger": 4, "invoices": 3, "payments": 2, "fx": 1},
        "rounding_rule": "HALF_UP",
    }, indent=2),
    encoding="utf-8",
)

(ep_dir / "policy.json").write_text(
    json.dumps({
        "fx_date_rule": "payment_date",
        "period_boundary_rule": "issue_date_inclusive",
        "rounding_rule": "HALF_UP",
        "amount_tolerance_minor": 1,
    }, indent=2),
    encoding="utf-8",
)

with (ep_dir / "ledger.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["row_id", "timestamp", "account", "debit_minor", "credit_minor", "currency", "entity_id", "invoice_id", "payment_id"])
    w.writerow(["ROW-1", "2026-10-05T10:00:00+00:00", "AR", 100000, 0, "USD", "ENT-1", "INV-1", ""])
    w.writerow(["ROW-2", "2026-10-06T10:00:00+00:00", "AR", 100000, 0, "USD", "ENT-1", "INV-2", ""])
    w.writerow(["ROW-3", "2026-10-10T12:00:00+00:00", "CASH", 0, 100000, "USD", "ENT-1", "INV-1", "PAY-1"])
    w.writerow(["ROW-4", "2026-10-15T12:00:00+00:00", "AR", 50000, 0, "USD", "ENT-2", "INV-3", ""])

with (ep_dir / "fx.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "source_currency", "target_currency", "rate"])
    w.writerow(["2026-10-01", "USD", "USD", "1.0"])

with (ep_dir / "invoices.jsonl").open("w", encoding="utf-8") as f:
    invoices = [
        {"doc_id": "DOC-I1", "invoice_id": "INV-1", "entity_id": "ENT-1", "issued_at": "2026-10-05T10:00:00+00:00", "due_at": "2026-10-20T10:00:00+00:00", "currency": "USD", "total_minor": 100000, "line_items": [{"desc": "Service A", "amount_minor": 100000}]},
        {"doc_id": "DOC-I2", "invoice_id": "INV-2", "entity_id": "ENT-1", "issued_at": "2026-10-06T10:00:00+00:00", "due_at": "2026-10-21T10:00:00+00:00", "currency": "USD", "total_minor": 100000, "line_items": [{"desc": "Service A", "amount_minor": 100000}]},
        {"doc_id": "DOC-I3", "invoice_id": "INV-3", "entity_id": "ENT-2", "issued_at": "2026-10-15T12:00:00+00:00", "due_at": "2026-10-30T12:00:00+00:00", "currency": "USD", "total_minor": 50000, "line_items": [{"desc": "Service B", "amount_minor": 50000}]},
    ]
    for inv in invoices:
        f.write(json.dumps(inv) + "\n")

with (ep_dir / "payments.jsonl").open("w", encoding="utf-8") as f:
    payments = [
        {"doc_id": "DOC-P1", "payment_id": "PAY-1", "timestamp": "2026-10-10T12:00:00+00:00", "currency": "USD", "amount_minor": 100000, "invoice_refs": ["INV-1"]},
        {"doc_id": "DOC-P2", "payment_id": "PAY-2", "timestamp": "2026-10-20T12:00:00+00:00", "currency": "USD", "amount_minor": 20000, "invoice_refs": ["INV-3"]},
    ]
    for pay in payments:
        f.write(json.dumps(pay) + "\n")

(ep_dir / "truth.json").write_text(
    json.dumps({
        "issues": [
            {
                "issue_id": "ERR-1",
                "type": "duplicate_invoice",
                "affected_ids": ["INV-1", "INV-2"],
                "expected_amount_minor": 100000,
                "currency": "USD",
                "valid_evidence_sets": [["DOC-I1", "DOC-I2"]],
            },
            {
                "issue_id": "ERR-2",
                "type": "missed_or_partial_payment",
                "affected_ids": ["INV-3"],
                "expected_amount_minor": 30000,
                "currency": "USD",
                "valid_evidence_sets": [["DOC-I3", "DOC-P2"]],
            },
        ]
    }, indent=2),
    encoding="utf-8",
)

# 2. Запускаем 4 политики и сохраняем реальные траектории
env = AuditEnv()
all_steps = []

for policy in [RandomPolicy(max_explore_steps=4), RuleBasedPolicy(), MarkAllAttackPolicy(), OraclePolicy()]:
    res = policy.run_episode(env, ep_dir, seed=42)
    print(f"[{policy.name}] finished in {env.steps_taken} steps -> {res}")
    for step in env.trajectory:
        d = step.model_dump()
        d["episode_id"] = f"ep_mock_001_{policy.name}"
        all_steps.append(d)

out_file = Path("artifacts/trajectories.jsonl")
out_file.parent.mkdir(parents=True, exist_ok=True)
with out_file.open("w", encoding="utf-8") as f:
    for s in all_steps:
        f.write(json.dumps(s) + "\n")

print(f"\nSaved {len(all_steps)} total trajectory steps to {out_file}")