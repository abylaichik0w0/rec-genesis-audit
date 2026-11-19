from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class Manifest(BaseModel):
    schema_version: str = "1.0"
    episode_id: str
    base_currency: str
    period_start: str
    period_end: str
    timezone: str
    record_counts: dict[str, int]
    rounding_rule: str = "HALF_UP"


class LedgerRow(BaseModel):
    row_id: str
    timestamp: str
    account: str
    debit_minor: int
    credit_minor: int
    currency: str
    entity_id: Optional[str] = None
    invoice_id: Optional[str] = None
    payment_id: Optional[str] = None


class Invoice(BaseModel):
    doc_id: str
    invoice_id: str
    entity_id: str
    issued_at: str
    due_at: str
    currency: str
    total_minor: int
    line_items: list[dict[str, Any]]


class Payment(BaseModel):
    doc_id: str
    payment_id: str
    timestamp: str
    currency: str
    amount_minor: int
    invoice_refs: list[str]


class FxRate(BaseModel):
    date: str
    source_currency: str
    target_currency: str
    rate: str  # Строковое десятичное число (Decimal)


class Policy(BaseModel):
    fx_date_rule: str
    period_boundary_rule: str
    rounding_rule: str
    amount_tolerance_minor: int = 1


class TruthIssue(BaseModel):
    issue_id: str
    type: Literal[
        "duplicate_invoice",
        "missed_or_partial_payment",
        "wrong_fx_date_or_rate",
        "period_cutoff_error",
    ]
    affected_ids: list[str]
    expected_amount_minor: int
    currency: str
    valid_evidence_sets: list[list[str]]


class Finding(BaseModel):
    type: str
    affected_ids: list[str]
    claimed_amount_minor: int
    currency: str
    evidence_ids: list[str] = Field(max_length=10)
    explanation: str = Field(max_length=1000)


class FindingsSubmission(BaseModel):
    episode_id: str
    findings: list[Finding] = Field(max_length=30)


class Action(BaseModel):
    tool: Literal[
        "list_records",
        "get_record",
        "get_document",
        "calculator",
        "submit",
    ]
    args: dict[str, Any] = Field(default_factory=dict)


class TrajectoryStep(BaseModel):
    episode_id: str
    step: int
    action: dict[str, Any]
    observation: dict[str, Any]
    reward: float
    terminated: bool
    truncated: bool