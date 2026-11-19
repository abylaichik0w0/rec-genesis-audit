import random
from datetime import datetime, timedelta, timezone
from typing import Any
from src.schemas import Invoice, LedgerRow, Payment, TruthIssue
from .company import _convert_minor, _iso_almaty


def inject_anomalies(
    episode: dict[str, Any],
    seed: int,
    scenario_mode: str = "full",
) -> dict[str, Any]:
    """
    Внедряет ошибки в согласованную бухгалтерию и формирует закрытый truth.json.
    scenario_mode:
      - 'clean': чистые книги (0 ошибок)
      - 'base4': 4 базовых типа ошибок
      - 'full': 4 базовых типа ошибок + 2 комбинированных сценария
    """
    if scenario_mode == "clean":
        episode["manifest"].record_counts = {
            "ledger": len(episode["ledger"]),
            "invoices": len(episode["invoices"]),
            "payments": len(episode["payments"]),
            "fx": len(episode["fx_rates"]),
        }
        return episode

    rng = random.Random(seed + 999)
    tz = timezone(timedelta(hours=5))
    invoices: list[Invoice] = episode["invoices"]
    payments: list[Payment] = episode["payments"]
    ledger: list[LedgerRow] = episode["ledger"]
    fx_map: dict[tuple[str, str], str] = episode["fx_map"]
    truth: list[TruthIssue] = []
    prov_list: list[dict[str, Any]] = []

    row_counter = len(ledger) + 1

    def next_row() -> str:
        nonlocal row_counter
        rid = f"ROW-{row_counter:04d}"
        row_counter += 1
        return rid

    # --- 1. ОШИБКА ТИПА 1: Дубль счёта (duplicate_invoice) ---
    orig_inv = invoices[4]
    dup_inv_id = f"{orig_inv.invoice_id}-DUP"
    dup_doc_id = f"DOC-{dup_inv_id}"
    dup_dt = datetime.fromisoformat(orig_inv.issued_at) + timedelta(minutes=12)

    invoices.append(
        Invoice(
            doc_id=dup_doc_id,
            invoice_id=dup_inv_id,
            entity_id=orig_inv.entity_id,
            issued_at=_iso_almaty(dup_dt),
            due_at=orig_inv.due_at,
            currency=orig_inv.currency,
            total_minor=orig_inv.total_minor,
            line_items=orig_inv.line_items,
        )
    )
    orig_rows = [r for r in ledger if r.invoice_id == orig_inv.invoice_id and r.payment_id is None]
    base_amt = orig_rows[0].debit_minor
    r_dup_1, r_dup_2 = next_row(), next_row()
    ledger.append(
        LedgerRow(
            row_id=r_dup_1, timestamp=_iso_almaty(dup_dt), account="1210_AR",
            debit_minor=base_amt, credit_minor=0, currency="KZT",
            entity_id=orig_inv.entity_id, invoice_id=dup_inv_id, payment_id=None
        )
    )
    ledger.append(
        LedgerRow(
            row_id=r_dup_2, timestamp=_iso_almaty(dup_dt), account="6010_REV",
            debit_minor=0, credit_minor=base_amt, currency="KZT",
            entity_id=orig_inv.entity_id, invoice_id=dup_inv_id, payment_id=None
        )
    )
    truth.append(
        TruthIssue(
            issue_id="ISS-001",
            type="duplicate_invoice",
            affected_ids=[orig_inv.invoice_id, dup_inv_id],
            expected_amount_minor=orig_inv.total_minor,
            currency=orig_inv.currency,
            valid_evidence_sets=[
                [orig_inv.doc_id, dup_doc_id],
                [orig_rows[0].row_id, r_dup_1],
            ],
        )
    )
    prov_list.append({"issue_id": "ISS-001", "scenario": "base_duplicate_invoice"})

    # --- 2. ОШИБКА ТИПА 2: Пропущенное/частичное распределение платежа (missed_or_partial_payment) ---
    part_inv_id = "INV-8101"
    part_doc_inv = "DOC-INV-8101"
    part_pay_id = "PAY-8101"
    part_doc_pay = "DOC-PAY-8101"
    dt_p2 = datetime(2026, 11, 14, 11, 0, 0, tzinfo=tz)
    full_kzt = 18000000
    paid_kzt = 10000000  # Недоплата 8 000 000 тиынов

    invoices.append(
        Invoice(
            doc_id=part_doc_inv, invoice_id=part_inv_id, entity_id="ENT-KAZTECH",
            issued_at=_iso_almaty(dt_p2), due_at=_iso_almaty(dt_p2 + timedelta(days=10)),
            currency="KZT", total_minor=full_kzt,
            line_items=[{"desc": "Enterprise Audit Suite", "qty": 1, "unit_price_minor": full_kzt}],
        )
    )
    payments.append(
        Payment(
            doc_id=part_doc_pay, payment_id=part_pay_id, timestamp=_iso_almaty(dt_p2 + timedelta(hours=2)),
            currency="KZT", amount_minor=paid_kzt, invoice_refs=[part_inv_id],
        )
    )
    r_p1, r_p2, r_p3, r_p4 = next_row(), next_row(), next_row(), next_row()
    ledger.extend([
        LedgerRow(row_id=r_p1, timestamp=_iso_almaty(dt_p2), account="1210_AR", debit_minor=full_kzt, credit_minor=0, currency="KZT", entity_id="ENT-KAZTECH", invoice_id=part_inv_id, payment_id=None),
        LedgerRow(row_id=r_p2, timestamp=_iso_almaty(dt_p2), account="6010_REV", debit_minor=0, credit_minor=full_kzt, currency="KZT", entity_id="ENT-KAZTECH", invoice_id=part_inv_id, payment_id=None),
        LedgerRow(row_id=r_p3, timestamp=_iso_almaty(dt_p2 + timedelta(hours=2)), account="1030_BANK", debit_minor=paid_kzt, credit_minor=0, currency="KZT", entity_id="ENT-KAZTECH", invoice_id=part_inv_id, payment_id=part_pay_id),
        LedgerRow(row_id=r_p4, timestamp=_iso_almaty(dt_p2 + timedelta(hours=2)), account="1210_AR", debit_minor=0, credit_minor=paid_kzt, currency="KZT", entity_id="ENT-KAZTECH", invoice_id=part_inv_id, payment_id=part_pay_id),
    ])
    truth.append(
        TruthIssue(
            issue_id="ISS-002",
            type="missed_or_partial_payment",
            affected_ids=[part_inv_id, part_pay_id],
            expected_amount_minor=full_kzt - paid_kzt,
            currency="KZT",
            valid_evidence_sets=[
                [part_doc_inv, part_doc_pay],
                [r_p1, r_p3],
            ],
        )
    )
    prov_list.append({"issue_id": "ISS-002", "scenario": "base_partial_payment"})

    # --- 3. ОШИБКА ТИПА 3: Неверный курс/дата FX (wrong_fx_date_or_rate) ---
    fx_inv_id = "INV-8201"
    fx_doc_inv = "DOC-INV-8201"
    dt_fx = datetime(2026, 11, 18, 15, 0, 0, tzinfo=tz)
    usd_minor = 100000  # $1,000.00
    correct_rate = fx_map[("2026-11-18", "USD")]
    wrong_rate = fx_map[("2026-11-02", "USD")]
    if wrong_rate == correct_rate:
        wrong_rate = "450.00"

    correct_kzt = _convert_minor(usd_minor, correct_rate)
    wrong_kzt = _convert_minor(usd_minor, wrong_rate)

    invoices.append(
        Invoice(
            doc_id=fx_doc_inv, invoice_id=fx_inv_id, entity_id="ENT-STEPPE",
            issued_at=_iso_almaty(dt_fx), due_at=_iso_almaty(dt_fx + timedelta(days=10)),
            currency="USD", total_minor=usd_minor,
            line_items=[{"desc": "Global CDN Traffic", "qty": 1, "unit_price_minor": usd_minor}],
        )
    )
    r_fx1, r_fx2 = next_row(), next_row()
    ledger.extend([
        LedgerRow(row_id=r_fx1, timestamp=_iso_almaty(dt_fx), account="1210_AR", debit_minor=wrong_kzt, credit_minor=0, currency="KZT", entity_id="ENT-STEPPE", invoice_id=fx_inv_id, payment_id=None),
        LedgerRow(row_id=r_fx2, timestamp=_iso_almaty(dt_fx), account="6010_REV", debit_minor=0, credit_minor=wrong_kzt, currency="KZT", entity_id="ENT-STEPPE", invoice_id=fx_inv_id, payment_id=None),
    ])
    truth.append(
        TruthIssue(
            issue_id="ISS-003",
            type="wrong_fx_date_or_rate",
            affected_ids=[fx_inv_id, r_fx1],
            expected_amount_minor=abs(correct_kzt - wrong_kzt),
            currency="KZT",
            valid_evidence_sets=[
                [fx_doc_inv, r_fx1],
                [fx_doc_inv, r_fx2],
            ],
        )
    )
    prov_list.append({"issue_id": "ISS-003", "scenario": "base_wrong_fx_rate"})

    # --- 4. ОШИБКА ТИПА 4: Ошибка отчётного периода (period_cutoff_error) ---
    cut_inv_id = "INV-8301"
    cut_doc_inv = "DOC-INV-8301"
    # Документ выписан 1 декабря в 01:30 по Алматы (+05:00), что в UTC ещё 30 ноября 20:30
    out_of_period_dt = datetime(2026, 12, 1, 1, 30, 0, tzinfo=tz)
    booked_in_nov_dt = datetime(2026, 11, 30, 23, 30, 0, tzinfo=tz)
    cut_kzt = 12000000

    invoices.append(
        Invoice(
            doc_id=cut_doc_inv, invoice_id=cut_inv_id, entity_id="ENT-ALATAU",
            issued_at=_iso_almaty(out_of_period_dt), due_at=_iso_almaty(out_of_period_dt + timedelta(days=15)),
            currency="KZT", total_minor=cut_kzt,
            line_items=[{"desc": "December Retainer", "qty": 1, "unit_price_minor": cut_kzt}],
        )
    )
    r_cut1, r_cut2 = next_row(), next_row()
    ledger.extend([
        LedgerRow(row_id=r_cut1, timestamp=_iso_almaty(booked_in_nov_dt), account="1210_AR", debit_minor=cut_kzt, credit_minor=0, currency="KZT", entity_id="ENT-ALATAU", invoice_id=cut_inv_id, payment_id=None),
        LedgerRow(row_id=r_cut2, timestamp=_iso_almaty(booked_in_nov_dt), account="6010_REV", debit_minor=0, credit_minor=cut_kzt, currency="KZT", entity_id="ENT-ALATAU", invoice_id=cut_inv_id, payment_id=None),
    ])
    truth.append(
        TruthIssue(
            issue_id="ISS-004",
            type="period_cutoff_error",
            affected_ids=[cut_inv_id, r_cut1],
            expected_amount_minor=cut_kzt,
            currency="KZT",
            valid_evidence_sets=[
                [cut_doc_inv, r_cut1],
                [cut_doc_inv, r_cut2],
            ],
        )
    )
    prov_list.append({"issue_id": "ISS-004", "scenario": "base_period_cutoff"})

    if scenario_mode == "full":
        # --- 5. КОМБО-СЦЕНАРИЙ 1: Частичный платёж в USD + неверный курс FX ---
        c1_inv_id = "INV-9101"
        c1_doc_inv = "DOC-INV-9101"
        c1_pay_id = "PAY-9101"
        c1_doc_pay = "DOC-PAY-9101"
        dt_c1 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=tz)
        c1_usd_total = 200000  # $2,000.00
        c1_usd_paid = 120000   # $1,200.00 (недоплата $800)
        c1_rate_ok = fx_map[("2026-11-20", "USD")]
        c1_rate_bad = "460.00"

        c1_kzt_booked = _convert_minor(c1_usd_total, c1_rate_bad)
        c1_kzt_paid = _convert_minor(c1_usd_paid, c1_rate_ok)

        invoices.append(
            Invoice(
                doc_id=c1_doc_inv, invoice_id=c1_inv_id, entity_id="ENT-NOMAD",
                issued_at=_iso_almaty(dt_c1), due_at=_iso_almaty(dt_c1 + timedelta(days=10)),
                currency="USD", total_minor=c1_usd_total,
                line_items=[{"desc": "Dedicated GPU Cluster", "qty": 1, "unit_price_minor": c1_usd_total}],
            )
        )
        payments.append(
            Payment(
                doc_id=c1_doc_pay, payment_id=c1_pay_id, timestamp=_iso_almaty(dt_c1 + timedelta(days=1)),
                currency="USD", amount_minor=c1_usd_paid, invoice_refs=[c1_inv_id],
            )
        )
        rc1_1, rc1_2, rc1_3, rc1_4 = next_row(), next_row(), next_row(), next_row()
        ledger.extend([
            LedgerRow(row_id=rc1_1, timestamp=_iso_almaty(dt_c1), account="1210_AR", debit_minor=c1_kzt_booked, credit_minor=0, currency="KZT", entity_id="ENT-NOMAD", invoice_id=c1_inv_id, payment_id=None),
            LedgerRow(row_id=rc1_2, timestamp=_iso_almaty(dt_c1), account="6010_REV", debit_minor=0, credit_minor=c1_kzt_booked, currency="KZT", entity_id="ENT-NOMAD", invoice_id=c1_inv_id, payment_id=None),
            LedgerRow(row_id=rc1_3, timestamp=_iso_almaty(dt_c1 + timedelta(days=1)), account="1030_BANK", debit_minor=c1_kzt_paid, credit_minor=0, currency="KZT", entity_id="ENT-NOMAD", invoice_id=c1_inv_id, payment_id=c1_pay_id),
            LedgerRow(row_id=rc1_4, timestamp=_iso_almaty(dt_c1 + timedelta(days=1)), account="1210_AR", debit_minor=0, credit_minor=c1_kzt_paid, currency="KZT", entity_id="ENT-NOMAD", invoice_id=c1_inv_id, payment_id=c1_pay_id),
        ])
        truth.append(
            TruthIssue(
                issue_id="ISS-005",
                type="wrong_fx_date_or_rate",
                affected_ids=[c1_inv_id, rc1_1],
                expected_amount_minor=abs(_convert_minor(c1_usd_total, c1_rate_ok) - c1_kzt_booked),
                currency="KZT",
                valid_evidence_sets=[[c1_doc_inv, rc1_1]],
            )
        )
        truth.append(
            TruthIssue(
                issue_id="ISS-006",
                type="missed_or_partial_payment",
                affected_ids=[c1_inv_id, c1_pay_id],
                expected_amount_minor=c1_usd_total - c1_usd_paid,
                currency="USD",
                valid_evidence_sets=[[c1_doc_inv, c1_doc_pay]],
            )
        )
        prov_list.append({"issue_id": "ISS-005+006", "scenario": "combo_partial_fx"})

        # --- 6. КОМБО-СЦЕНАРИЙ 2: Дубль счёта на границе периода через полночь ---
        c2_orig_id = "INV-9201"
        c2_dup_id = "INV-9201-NIGHT"
        dt_c2_orig = datetime(2026, 11, 30, 23, 45, 0, tzinfo=tz)
        dt_c2_dup = datetime(2026, 12, 1, 0, 15, 0, tzinfo=tz)
        c2_kzt = 9500000

        invoices.append(
            Invoice(
                doc_id=f"DOC-{c2_orig_id}", invoice_id=c2_orig_id, entity_id="ENT-CASPIAN",
                issued_at=_iso_almaty(dt_c2_orig), due_at=_iso_almaty(dt_c2_orig + timedelta(days=14)),
                currency="KZT", total_minor=c2_kzt,
                line_items=[{"desc": "Midnight Batch Processing", "qty": 1, "unit_price_minor": c2_kzt}],
            )
        )
        invoices.append(
            Invoice(
                doc_id=f"DOC-{c2_dup_id}", invoice_id=c2_dup_id, entity_id="ENT-CASPIAN",
                issued_at=_iso_almaty(dt_c2_dup), due_at=_iso_almaty(dt_c2_dup + timedelta(days=14)),
                currency="KZT", total_minor=c2_kzt,
                line_items=[{"desc": "Midnight Batch Processing", "qty": 1, "unit_price_minor": c2_kzt}],
            )
        )
        rc2_1, rc2_2, rc2_3, rc2_4 = next_row(), next_row(), next_row(), next_row()
        ledger.extend([
            LedgerRow(row_id=rc2_1, timestamp=_iso_almaty(dt_c2_orig), account="1210_AR", debit_minor=c2_kzt, credit_minor=0, currency="KZT", entity_id="ENT-CASPIAN", invoice_id=c2_orig_id, payment_id=None),
            LedgerRow(row_id=rc2_2, timestamp=_iso_almaty(dt_c2_orig), account="6010_REV", debit_minor=0, credit_minor=c2_kzt, currency="KZT", entity_id="ENT-CASPIAN", invoice_id=c2_orig_id, payment_id=None),
            LedgerRow(row_id=rc2_3, timestamp=_iso_almaty(dt_c2_orig + timedelta(minutes=10)), account="1210_AR", debit_minor=c2_kzt, credit_minor=0, currency="KZT", entity_id="ENT-CASPIAN", invoice_id=c2_dup_id, payment_id=None),
            LedgerRow(row_id=rc2_4, timestamp=_iso_almaty(dt_c2_orig + timedelta(minutes=10)), account="6010_REV", debit_minor=0, credit_minor=c2_kzt, currency="KZT", entity_id="ENT-CASPIAN", invoice_id=c2_dup_id, payment_id=None),
        ])
        truth.append(
            TruthIssue(
                issue_id="ISS-007",
                type="duplicate_invoice",
                affected_ids=[c2_orig_id, c2_dup_id],
                expected_amount_minor=c2_kzt,
                currency="KZT",
                valid_evidence_sets=[[f"DOC-{c2_orig_id}", f"DOC-{c2_dup_id}"], [rc2_1, rc2_3]],
            )
        )
        truth.append(
            TruthIssue(
                issue_id="ISS-008",
                type="period_cutoff_error",
                affected_ids=[c2_dup_id, rc2_3],
                expected_amount_minor=c2_kzt,
                currency="KZT",
                valid_evidence_sets=[[f"DOC-{c2_dup_id}", rc2_3]],
            )
        )
        prov_list.append({"issue_id": "ISS-007+008", "scenario": "combo_midnight_dup_cutoff"})

    episode["truth"] = truth
    episode["provenance"]["injected_issues"] = prov_list
    episode["manifest"].record_counts = {
        "ledger": len(ledger),
        "invoices": len(invoices),
        "payments": len(payments),
        "fx": len(episode["fx_rates"]),
    }
    return episode
