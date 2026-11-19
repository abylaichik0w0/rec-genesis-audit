import csv
import json
import os
from dataclasses import asdict, fields, is_dataclass
from typing import Any
from src.schemas import FxRate, LedgerRow
from .anomalies import inject_anomalies
from .company import generate_clean_company


def _to_dict(obj: Any) -> dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def generate_episode(
    seed: int,
    episode_id: str,
    scenario_mode: str = "full",
    num_base_invoices: int = 25,
) -> dict[str, Any]:
    """Полный пайплайн генерации эпизода по seed."""
    clean_ep = generate_clean_company(
        seed=seed,
        episode_id=episode_id,
        num_base_invoices=num_base_invoices,
    )
    return inject_anomalies(clean_ep, seed=seed, scenario_mode=scenario_mode)


def save_episode(episode: dict[str, Any], out_dir: str) -> None:
    """Сохраняет открытые и закрытые файлы эпизода на диск."""
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(_to_dict(episode["manifest"]), f, indent=2)

    with open(os.path.join(out_dir, "policy.json"), "w", encoding="utf-8") as f:
        json.dump(_to_dict(episode["policy"]), f, indent=2)

    with open(os.path.join(out_dir, "invoices.jsonl"), "w", encoding="utf-8") as f:
        for inv in episode["invoices"]:
            f.write(json.dumps(_to_dict(inv)) + "\n")

    with open(os.path.join(out_dir, "payments.jsonl"), "w", encoding="utf-8") as f:
        for pay in episode["payments"]:
            f.write(json.dumps(_to_dict(pay)) + "\n")

    with open(os.path.join(out_dir, "ledger.csv"), "w", newline="", encoding="utf-8") as f:
        field_names = [fld.name for fld in fields(LedgerRow)]
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        for row in episode["ledger"]:
            writer.writerow(_to_dict(row))

    with open(os.path.join(out_dir, "fx.csv"), "w", newline="", encoding="utf-8") as f:
        field_names = [fld.name for fld in fields(FxRate)]
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        for rate in episode["fx_rates"]:
            writer.writerow(_to_dict(rate))

    with open(os.path.join(out_dir, "truth.json"), "w", encoding="utf-8") as f:
        json.dump([_to_dict(t) for t in episode["truth"]], f, indent=2)

    with open(os.path.join(out_dir, "provenance.json"), "w", encoding="utf-8") as f:
        json.dump(episode["provenance"], f, indent=2)
