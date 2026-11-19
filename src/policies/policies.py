import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.env.audit_env import AuditEnv


class BasePolicy:
    name: str = "base"

    def run_episode(self, env: AuditEnv, episode_dir: str | Path, seed: int = 42) -> dict[str, Any]:
        raise NotImplementedError


class RandomPolicy(BasePolicy):
    """Случайный исследователь с фиксированным seed."""
    name = "random"

    def __init__(self, max_explore_steps: int = 10):
        self.max_explore_steps = max_explore_steps

    def run_episode(self, env: AuditEnv, episode_dir: str | Path, seed: int = 42) -> dict[str, Any]:
        rng = random.Random(seed)
        obs, _ = env.reset(episode_dir, seed=seed)
        tables = ["ledger", "invoices", "payments", "fx"]

        for _ in range(self.max_explore_steps):
            choice = rng.choice(["list", "calc"])
            if choice == "list":
                t = rng.choice(tables)
                obs, _, term, trunc, _ = env.step({"tool": "list_records", "args": {"table": t, "cursor": 0, "limit": 10}})
            else:
                a, b = rng.randint(100, 5000), rng.randint(100, 5000)
                obs, _, term, trunc, _ = env.step({"tool": "calculator", "args": {"expression": f"{a} - {b}"}})
            if term or trunc:
                return {"reward": 0.0, "obs": obs}

        obs, reward, _, _, _ = env.step({"tool": "submit", "args": {"findings": []}})
        return {"reward": reward, "obs": obs}


class RuleBasedPolicy(BasePolicy):
    """Алгоритм сверки: дубли счетов, частичные платежи и ошибки отчётного периода."""
    name = "rule_based"

    def run_episode(self, env: AuditEnv, episode_dir: str | Path, seed: int = 42) -> dict[str, Any]:
        obs, _ = env.reset(episode_dir, seed=seed)
        manifest = obs.get("manifest", {})
        period_start = manifest.get("period_start", "")
        period_end = manifest.get("period_end", "")
        findings: list[dict[str, Any]] = []

        # 1. Загружаем все инвойсы
        invoices: list[dict[str, Any]] = []
        cursor = 0
        while True:
            obs, _, term, trunc, _ = env.step({"tool": "list_records", "args": {"table": "invoices", "cursor": cursor, "limit": 50}})
            if term or trunc:
                return {"reward": 0.0, "obs": obs}
            invoices.extend(obs.get("records", []))
            cursor = obs.get("next_cursor")
            if cursor is None:
                break

        # 2. Загружаем все платежи
        payments: list[dict[str, Any]] = []
        cursor = 0
        while True:
            obs, _, term, trunc, _ = env.step({"tool": "list_records", "args": {"table": "payments", "cursor": cursor, "limit": 50}})
            if term or trunc:
                return {"reward": 0.0, "obs": obs}
            payments.extend(obs.get("records", []))
            cursor = obs.get("next_cursor")
            if cursor is None:
                break

        # Проверка 1: Дубли инвойсов
        seen_inv: dict[tuple[str, int, str], dict[str, Any]] = {}
        for inv in invoices:
            key = (inv["entity_id"], inv["total_minor"], inv["currency"])
            if key in seen_inv:
                orig = seen_inv[key]
                findings.append({
                    "type": "duplicate_invoice",
                    "affected_ids": sorted([orig["invoice_id"], inv["invoice_id"]]),
                    "claimed_amount_minor": inv["total_minor"],
                    "currency": inv["currency"],
                    "evidence_ids": [orig["doc_id"], inv["doc_id"]],
                    "explanation": f"Duplicate invoice for {inv['entity_id']} with amount {inv['total_minor']}.",
                })
            else:
                seen_inv[key] = inv

        # Проверка 2: Частичные платежи
        paid_by_inv: dict[str, int] = {}
        pay_docs_by_inv: dict[str, list[str]] = {}
        for pay in payments:
            for ref in pay.get("invoice_refs", []):
                paid_by_inv[ref] = paid_by_inv.get(ref, 0) + pay["amount_minor"]
                pay_docs_by_inv.setdefault(ref, []).append(pay["doc_id"])

        for inv in invoices:
            inv_id = inv["invoice_id"]
            paid = paid_by_inv.get(inv_id, 0)
            if 0 < paid < inv["total_minor"]:
                obs, _, term, trunc, _ = env.step({
                    "tool": "calculator",
                    "args": {"expression": f"{inv['total_minor']} - {paid}"},
                })
                if term or trunc:
                    return {"reward": 0.0, "obs": obs}
                diff = int(Decimal(str(obs.get("result", inv["total_minor"] - paid))))
                findings.append({
                    "type": "missed_or_partial_payment",
                    "affected_ids": [inv_id],
                    "claimed_amount_minor": diff,
                    "currency": inv["currency"],
                    "evidence_ids": [inv["doc_id"]] + pay_docs_by_inv.get(inv_id, [])[:9],
                    "explanation": f"Partial payment: paid {paid} of {inv['total_minor']}, missing {diff}.",
                })

            # Проверка 3: Ошибка отчётного периода (дата инвойса вне границ manifest)
            issued_at = inv.get("issued_at", "")
            if period_start and period_end and issued_at:
                if issued_at < period_start or issued_at > period_end:
                    findings.append({
                        "type": "period_cutoff_error",
                        "affected_ids": [inv_id],
                        "claimed_amount_minor": inv["total_minor"],
                        "currency": inv["currency"],
                        "evidence_ids": [inv["doc_id"]],
                        "explanation": f"Invoice {inv_id} issued_at {issued_at} is outside [{period_start}, {period_end}].",
                    })

        obs, reward, _, _, _ = env.step({"tool": "submit", "args": {"findings": findings[:30]}})
        return {"reward": reward, "obs": obs}


class MarkAllAttackPolicy(BasePolicy):
    """Атака 'пометить всё': проверяет, что оценщик штрафует за ложные срабатывания."""
    name = "attack_mark_all"

    def run_episode(self, env: AuditEnv, episode_dir: str | Path, seed: int = 42) -> dict[str, Any]:
        obs, _ = env.reset(episode_dir, seed=seed)
        obs, _, _, _, _ = env.step({"tool": "list_records", "args": {"table": "invoices", "cursor": 0, "limit": 30}})
        findings = [
            {
                "type": "duplicate_invoice",
                "affected_ids": [inv["invoice_id"]],
                "claimed_amount_minor": inv["total_minor"],
                "currency": inv["currency"],
                "evidence_ids": [inv["doc_id"]],
                "explanation": "Flagging every invoice as duplicate attack test.",
            }
            for inv in obs.get("records", [])[:30]
        ]
        obs, reward, _, _, _ = env.step({"tool": "submit", "args": {"findings": findings}})
        return {"reward": reward, "obs": obs}


class OraclePolicy(BasePolicy):
    """Только для тестов оценщика: читает truth.json и отправляет идеальный ответ."""
    name = "oracle"

    def run_episode(self, env: AuditEnv, episode_dir: str | Path, seed: int = 42) -> dict[str, Any]:
        ep_path = Path(episode_dir)
        obs, _ = env.reset(ep_path, seed=seed)
        truth_raw = json.loads((ep_path / "truth.json").read_text(encoding="utf-8"))
        issues = truth_raw if isinstance(truth_raw, list) else truth_raw.get("issues", [])

        findings = []
        for issue in issues:
            ev_sets = issue.get("valid_evidence_sets", [[]])
            findings.append({
                "type": issue["type"],
                "affected_ids": issue["affected_ids"],
                "claimed_amount_minor": issue["expected_amount_minor"],
                "currency": issue["currency"],
                "evidence_ids": ev_sets[0] if ev_sets else [],
                "explanation": f"Oracle verified issue {issue['issue_id']}.",
            })

        obs, reward, _, _, _ = env.step({"tool": "submit", "args": {"findings": findings}})
        return {"reward": reward, "obs": obs}