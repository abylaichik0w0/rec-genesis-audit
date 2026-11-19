import copy
import random
from typing import Any


def permute_episode(episode: dict[str, Any], perm_seed: int) -> dict[str, Any]:
    """
    Изоморфная перестановка порядка строк и замена всех ID (инвойсов, платежей,
    документов, проводок) с сохранением семантики и пересчётом truth.json
    для парных проверок воспроизводимости (раздел 10 ТЗ).
    """
    ep = copy.deepcopy(episode)
    rng = random.Random(perm_seed)

    id_map: dict[str, str] = {}

    def map_id(old_id: str | None, prefix: str) -> str | None:
        if old_id is None:
            return None
        if old_id not in id_map:
            suffix = "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
            id_map[old_id] = f"{prefix}-{suffix}"
        return id_map[old_id]

    for inv in ep["invoices"]:
        inv.doc_id = map_id(inv.doc_id, "DOC")
        inv.invoice_id = map_id(inv.invoice_id, "INV")

    for pay in ep["payments"]:
        pay.doc_id = map_id(pay.doc_id, "DOC")
        pay.payment_id = map_id(pay.payment_id, "PAY")
        pay.invoice_refs = [map_id(ref, "INV") for ref in pay.invoice_refs]

    for row in ep["ledger"]:
        row.row_id = map_id(row.row_id, "ROW")
        row.invoice_id = map_id(row.invoice_id, "INV")
        row.payment_id = map_id(row.payment_id, "PAY")

    for issue in ep["truth"]:
        issue.affected_ids = [id_map.get(i, i) for i in issue.affected_ids]
        issue.valid_evidence_sets = [
            [id_map.get(ev, ev) for ev in ev_set]
            for ev_set in issue.valid_evidence_sets
        ]

    rng.shuffle(ep["invoices"])
    rng.shuffle(ep["payments"])
    rng.shuffle(ep["ledger"])

    return ep
