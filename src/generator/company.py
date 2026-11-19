import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from src.schemas import FxRate, Invoice, LedgerRow, Manifest, Payment, Policy


ENTITIES = ["ENT-KAZTECH", "ENT-STEPPE", "ENT-ALATAU", "ENT-NOMAD", "ENT-CASPIAN"]
SERVICES = [
    "Cloud Infrastructure",
    "Security Monitoring",
    "API Gateway License",
    "Data Warehouse Storage",
    "Managed Kubernetes",
]


def _iso_almaty(dt: datetime) -> str:
    tz = timezone(timedelta(hours=5))
    return dt.astimezone(tz).isoformat()


def _convert_minor(amount_minor: int, rate_str: str) -> int:
    val = (Decimal(amount_minor) * Decimal(rate_str)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(val)


def generate_clean_company(
    seed: int,
    episode_id: str,
    num_base_invoices: int = 25,
) -> dict[str, Any]:
    """
    Генерирует детерминированную согласованную бухгалтерию компании (дебет == кредит)
    с отвлекающими корректными случаями: разбитыми платежами, возвратами и
    повторяющимися суммами у разных контрагентов.
    """
    rng = random.Random(seed)
    tz = timezone(timedelta(hours=5))
    period_start = datetime(2026, 11, 1, 0, 0, 0, tzinfo=tz)
    period_end = datetime(2026, 11, 30, 23, 59, 59, tzinfo=tz)

    # Курсы валют на каждый день ноября 2026
    fx_rates: list[FxRate] = []
    fx_map: dict[tuple[str, str], str] = {}
    base_usd = Decimal("488.00")
    base_eur = Decimal("525.00")

    for day in range(1, 31):
        date_str = f"2026-11-{day:02d}"
        delta_usd = Decimal(rng.randint(-400, 400)) / Decimal("100")
        delta_eur = Decimal(rng.randint(-500, 500)) / Decimal("100")
        usd_rate = f"{(base_usd + delta_usd):.2f}"
        eur_rate = f"{(base_eur + delta_eur):.2f}"

        fx_rates.append(FxRate(date=date_str, source_currency="USD", target_currency="KZT", rate=usd_rate))
        fx_rates.append(FxRate(date=date_str, source_currency="EUR", target_currency="KZT", rate=eur_rate))
        fx_map[(date_str, "USD")] = usd_rate
        fx_map[(date_str, "EUR")] = eur_rate

    invoices: list[Invoice] = []
    payments: list[Payment] = []
    ledger: list[LedgerRow] = []

    inv_seq = 1000
    pay_seq = 2000
    row_seq = 1

    def next_row_id() -> str:
        nonlocal row_seq
        rid = f"ROW-{row_seq:04d}"
        row_seq += 1
        return rid

    # Одинаковая сумма для отвлекающего случая у двух разных контрагентов
    shared_distractor_amount = 25000000  # 250 000.00 KZT

    for idx in range(num_base_invoices):
        inv_seq += 1
        inv_id = f"INV-{inv_seq}"
        doc_inv_id = f"DOC-{inv_id}"
        entity = ENTITIES[idx % len(ENTITIES)]

        day = rng.randint(2, 24)
        hour = rng.randint(9, 17)
        issued_dt = datetime(2026, 11, day, hour, 0, 0, tzinfo=tz)
        due_dt = issued_dt + timedelta(days=14)

        if idx in (0, 1):
            currency = "KZT"
            total_minor = shared_distractor_amount
        else:
            currency = rng.choice(["KZT", "KZT", "USD", "EUR"])
            if currency == "KZT":
                total_minor = rng.randint(50, 300) * 100000
            else:
                total_minor = rng.randint(500, 3000) * 100

        service_name = rng.choice(SERVICES)
        invoices.append(
            Invoice(
                doc_id=doc_inv_id,
                invoice_id=inv_id,
                entity_id=entity,
                issued_at=_iso_almaty(issued_dt),
                due_at=_iso_almaty(due_dt),
                currency=currency,
                total_minor=total_minor,
                line_items=[{"desc": service_name, "qty": 1, "unit_price_minor": total_minor}],
            )
        )

        # Сумма в базовой валюте KZT на дату инвойса
        inv_date_str = issued_dt.strftime("%Y-%m-%d")
        if currency == "KZT":
            base_inv_minor = total_minor
        else:
            base_inv_minor = _convert_minor(total_minor, fx_map[(inv_date_str, currency)])

        # Проводка начисления инвойса (Дебет AR = Кредит REV)
        ledger.append(
            LedgerRow(
                row_id=next_row_id(),
                timestamp=_iso_almaty(issued_dt),
                account="1210_AR",
                debit_minor=base_inv_minor,
                credit_minor=0,
                currency="KZT",
                entity_id=entity,
                invoice_id=inv_id,
                payment_id=None,
            )
        )
        ledger.append(
            LedgerRow(
                row_id=next_row_id(),
                timestamp=_iso_almaty(issued_dt),
                account="6010_REV",
                debit_minor=0,
                credit_minor=base_inv_minor,
                currency="KZT",
                entity_id=entity,
                invoice_id=inv_id,
                payment_id=None,
            )
        )

        # Отвлекающий случай 1: разбитый платёж (2 части) на idx == 2
        if idx == 2 and currency == "KZT":
            part1 = total_minor // 2
            part2 = total_minor - part1
            parts = [(part1, issued_dt + timedelta(days=1)), (part2, issued_dt + timedelta(days=3))]
        else:
            parts = [(total_minor, issued_dt + timedelta(days=rng.randint(1, 4)))]

        for part_amount, pay_dt in parts:
            pay_seq += 1
            pay_id = f"PAY-{pay_seq}"
            doc_pay_id = f"DOC-{pay_id}"

            payments.append(
                Payment(
                    doc_id=doc_pay_id,
                    payment_id=pay_id,
                    timestamp=_iso_almaty(pay_dt),
                    currency=currency,
                    amount_minor=part_amount,
                    invoice_refs=[inv_id],
                )
            )

            pay_date_str = pay_dt.strftime("%Y-%m-%d")
            if currency == "KZT":
                base_pay_minor = part_amount
                base_ar_close = part_amount
            else:
                base_pay_minor = _convert_minor(part_amount, fx_map[(pay_date_str, currency)])
                base_ar_close = base_inv_minor

            ledger.append(
                LedgerRow(
                    row_id=next_row_id(),
                    timestamp=_iso_almaty(pay_dt),
                    account="1030_BANK",
                    debit_minor=base_pay_minor,
                    credit_minor=0,
                    currency="KZT",
                    entity_id=entity,
                    invoice_id=inv_id,
                    payment_id=pay_id,
                )
            )
            ledger.append(
                LedgerRow(
                    row_id=next_row_id(),
                    timestamp=_iso_almaty(pay_dt),
                    account="1210_AR",
                    debit_minor=0,
                    credit_minor=base_ar_close,
                    currency="KZT",
                    entity_id=entity,
                    invoice_id=inv_id,
                    payment_id=pay_id,
                )
            )
            # Курсовая разница при оплате в валюте (строгий баланс дебет == кредит)
            fx_diff = base_pay_minor - base_ar_close
            if fx_diff > 0:
                ledger.append(
                    LedgerRow(
                        row_id=next_row_id(),
                        timestamp=_iso_almaty(pay_dt),
                        account="6250_FX_GAIN",
                        debit_minor=0,
                        credit_minor=fx_diff,
                        currency="KZT",
                        entity_id=entity,
                        invoice_id=inv_id,
                        payment_id=pay_id,
                    )
                )
            elif fx_diff < 0:
                ledger.append(
                    LedgerRow(
                        row_id=next_row_id(),
                        timestamp=_iso_almaty(pay_dt),
                        account="7430_FX_LOSS",
                        debit_minor=abs(fx_diff),
                        credit_minor=0,
                        currency="KZT",
                        entity_id=entity,
                        invoice_id=inv_id,
                        payment_id=pay_id,
                    )
                )

        # Отвлекающий случай 2: законный возврат средств (refund) на idx == 3
        if idx == 3 and currency == "KZT":
            refund_amount = 5000000  # 50 000.00 KZT
            refund_dt = issued_dt + timedelta(days=5)
            pay_seq += 1
            ref_id = f"PAY-{pay_seq}-REF"
            payments.append(
                Payment(
                    doc_id=f"DOC-{ref_id}",
                    payment_id=ref_id,
                    timestamp=_iso_almaty(refund_dt),
                    currency="KZT",
                    amount_minor=-refund_amount,
                    invoice_refs=[inv_id],
                )
            )
            ledger.append(
                LedgerRow(
                    row_id=next_row_id(),
                    timestamp=_iso_almaty(refund_dt),
                    account="6010_REV",
                    debit_minor=refund_amount,
                    credit_minor=0,
                    currency="KZT",
                    entity_id=entity,
                    invoice_id=inv_id,
                    payment_id=ref_id,
                )
            )
            ledger.append(
                LedgerRow(
                    row_id=next_row_id(),
                    timestamp=_iso_almaty(refund_dt),
                    account="1030_BANK",
                    debit_minor=0,
                    credit_minor=refund_amount,
                    currency="KZT",
                    entity_id=entity,
                    invoice_id=inv_id,
                    payment_id=ref_id,
                )
            )

    policy = Policy(
        fx_date_rule="transaction_date",
        period_boundary_rule="strict_local_timezone",
        rounding_rule="HALF_UP",
        amount_tolerance_minor=1,
    )

    manifest = Manifest(
        schema_version="1.0",
        episode_id=episode_id,
        base_currency="KZT",
        period_start=_iso_almaty(period_start),
        period_end=_iso_almaty(period_end),
        timezone="Asia/Almaty",
        record_counts={
            "ledger": len(ledger),
            "invoices": len(invoices),
            "payments": len(payments),
            "fx": len(fx_rates),
        },
        rounding_rule="HALF_UP",
    )

    return {
        "manifest": manifest,
        "policy": policy,
        "invoices": invoices,
        "payments": payments,
        "ledger": ledger,
        "fx_rates": fx_rates,
        "fx_map": fx_map,
        "truth": [],
        "provenance": {"episode_id": episode_id, "seed": seed, "injected_issues": []},
    }
