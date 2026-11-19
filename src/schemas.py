import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


def _ensure_int(val: Any, name: str) -> int:
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"Field '{name}' must be an integer, got {type(val).__name__}")
    return val


class _BaseSchema:
    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def model_dump_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class Manifest(_BaseSchema):
    episode_id: str
    base_currency: str
    period_start: str
    period_end: str
    timezone: str
    record_counts: dict[str, int]
    schema_version: str = "1.0"
    rounding_rule: str = "HALF_UP"


@dataclass
class LedgerRow(_BaseSchema):
    row_id: str
    timestamp: str
    account: str
    debit_minor: int
    credit_minor: int
    currency: str
    entity_id: Optional[str] = None
    invoice_id: Optional[str] = None
    payment_id: Optional[str] = None

    def __post_init__(self) -> None:
        _ensure_int(self.debit_minor, "debit_minor")
        _ensure_int(self.credit_minor, "credit_minor")


@dataclass
class Invoice(_BaseSchema):
    doc_id: str
    invoice_id: str
    entity_id: str
    issued_at: str
    due_at: str
    currency: str
    total_minor: int
    line_items: list[dict[str, Any]]

    def __post_init__(self) -> None:
        _ensure_int(self.total_minor, "total_minor")


@dataclass
class Payment(_BaseSchema):
    doc_id: str
    payment_id: str
    timestamp: str
    currency: str
    amount_minor: int
    invoice_refs: list[str]

    def __post_init__(self) -> None:
        _ensure_int(self.amount_minor, "amount_minor")


@dataclass
class FxRate(_BaseSchema):
    date: str
    source_currency: str
    target_currency: str
    rate: str


@dataclass
class Policy(_BaseSchema):
    fx_date_rule: str
    period_boundary_rule: str
    rounding_rule: str
    amount_tolerance_minor: int = 1


@dataclass
class TruthIssue(_BaseSchema):
    issue_id: str
    type: str
    affected_ids: list[str]
    expected_amount_minor: int
    currency: str
    valid_evidence_sets: list[list[str]]


@dataclass
class Finding(_BaseSchema):
    type: str
    affected_ids: list[str]
    claimed_amount_minor: int
    currency: str
    evidence_ids: list[str]
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type.strip():
            raise ValueError("Finding 'type' must be a non-empty string")
        if not isinstance(self.affected_ids, list) or not all(isinstance(x, str) for x in self.affected_ids):
            raise ValueError("Finding 'affected_ids' must be a list of strings")
        _ensure_int(self.claimed_amount_minor, "claimed_amount_minor")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("Finding 'currency' must be a non-empty string")
        if not isinstance(self.evidence_ids, list) or not all(isinstance(x, str) for x in self.evidence_ids):
            raise ValueError("Finding 'evidence_ids' must be a list of strings")
        if len(self.evidence_ids) > 10:
            raise ValueError("Max 10 evidence_ids allowed per finding")
        if not isinstance(self.explanation, str):
            raise ValueError("Finding 'explanation' must be a string")
        if len(self.explanation) > 1000:
            raise ValueError("Explanation max length is 1000 characters")


@dataclass
class FindingsSubmission(_BaseSchema):
    episode_id: str
    findings: list[Finding]

    def __post_init__(self) -> None:
        if not isinstance(self.findings, list):
            raise ValueError("'findings' must be a list")
        if len(self.findings) > 30:
            raise ValueError("Max 30 findings allowed per submission")
        parsed: list[Finding] = []
        for f in self.findings:
            if isinstance(f, Finding):
                parsed.append(f)
            elif isinstance(f, dict):
                parsed.append(Finding(**f))
            else:
                raise ValueError("Each finding must be a dict or Finding instance")
        self.findings = parsed


@dataclass
class Action(_BaseSchema):
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed = {"list_records", "get_record", "get_document", "calculator", "submit"}
        if self.tool not in allowed:
            raise ValueError(f"Unknown tool: {self.tool}")
        if not isinstance(self.args, dict):
            raise ValueError("'args' must be a dict")


@dataclass
class TrajectoryStep(_BaseSchema):
    episode_id: str
    step: int
    action: dict[str, Any]
    observation: dict[str, Any]
    reward: float
    terminated: bool
    truncated: bool