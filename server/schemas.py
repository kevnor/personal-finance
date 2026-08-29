"""Request and response bodies.

Validation lives here rather than in the routes so that a malformed body is
a 422 describing the field, not a 500 from SQLite three layers down. The
treatment enums in particular mirror the schema's CHECK constraints: without
them a typo reaches the database and fails as an opaque IntegrityError.
"""
from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BudgetTreatment = Literal["fixed", "variable", "exceptional"]
BudgetOverride = Literal["fixed", "variable", "exceptional", "reimbursable",
                         "ignore"]


# --- auth ------------------------------------------------------------------

class PasscodeIn(BaseModel):
    passcode: str = Field(min_length=1)


class PasscodeChangeIn(BaseModel):
    current_passcode: str = Field(min_length=1)
    new_passcode: str = Field(min_length=1)


class AuthStatus(BaseModel):
    configured: bool
    authenticated: bool
    # Whether an Entra app registration is configured, so the client knows
    # whether to offer "Sign in with Microsoft" at all. Says nothing about
    # the caller -- an unauthenticated client needs it to draw the login
    # screen.
    entra_available: bool = False
    # How the current session was obtained, when there is one. The client
    # uses it to decide whether a 401 can be retried silently: only an Entra
    # session can, and only if the browser had one to begin with.
    source: str | None = None


# --- transactions ----------------------------------------------------------

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: str
    account: str
    description: str
    amount: float
    category: str | None
    category_kind: str | None
    treatment: str | None
    counterparty: str | None
    note: str | None
    needs_review: bool
    is_transfer: bool
    is_derived: bool
    origin: str

    @classmethod
    def from_row(cls, row) -> "TransactionOut":
        return cls(
            id=row["id"],
            date=row["date"],
            account=row["account"],
            description=row["description"],
            amount=row["amount"],
            category=row["category"],
            category_kind=row["category_kind"],
            treatment=row["treatment"],
            counterparty=row["counterparty"],
            note=row["note"],
            needs_review=bool(row["needs_review"]),
            is_transfer=bool(row["is_transfer"]),
            is_derived=bool(row["is_derived"]),
            origin=row["origin"])


class TransactionIn(BaseModel):
    """One hand-entered transaction.

    `amount` is signed like everywhere else in this codebase -- positive is
    money in -- and is rejected at zero: a zero-amount row is always a mistake
    and would sit in the ledger contributing nothing but confusion.
    """
    date: datetime.date
    description: str = Field(min_length=1, max_length=500)
    amount: float
    account: str = Field(min_length=1)
    category: str | None = None
    counterparty: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _amount_is_not_zero(self) -> "TransactionIn":
        if self.amount == 0:
            raise ValueError("amount must not be zero")
        return self


class BulkIn(BaseModel):
    """`POST /transactions/bulk`, the spec's programmatic entry point.

    Capped at 1000 rows per call. The cap is not about the database -- SQLite
    would take far more -- but about the request being one unit of work whose
    failure a caller can retry cheaply; ingest is idempotent, so retrying a
    smaller batch is free.
    """
    rows: list[TransactionIn] = Field(min_length=1, max_length=1000)


class BulkResult(BaseModel):
    inserted: int
    ids: list[int]


class TransactionPatch(BaseModel):
    """A correction to one row.

    `teach` is what turns a one-off fix into a rule: recategorising a row in
    the UI writes a `merchant_rules` entry so next month's charge from the
    same merchant lands correctly. It is opt-in per request because it is
    not always right -- a memo says what was bought, not why, and some
    corrections are about one payment only (see server/corrections.py).
    """
    category: str | None = None
    budget_override: BudgetOverride | None = None
    clear_override: bool = False
    note: str | None = None
    teach: bool = False
    teach_pattern: str | None = None

    @model_validator(mode="after")
    def _something_to_do(self) -> "TransactionPatch":
        if (self.category is None and self.budget_override is None
                and not self.clear_override and self.note is None):
            raise ValueError("patch must change at least one field")
        if self.budget_override is not None and self.clear_override:
            raise ValueError(
                "budget_override and clear_override are mutually exclusive")
        if (self.teach or self.teach_pattern) and self.category is None:
            raise ValueError("teach requires a category")
        return self


# --- budget ----------------------------------------------------------------

class PoolOut(BaseModel):
    income: float
    fixed: float
    committed: float
    savings: float
    amount: float
    estimated: bool


class FiguresOut(BaseModel):
    week_envelope: float
    week_spent: float
    week_remaining: float
    today_allowance: float
    today_spent: float
    today_remaining: float
    days_left: int


class BudgetOut(BaseModel):
    day: datetime.date
    week_start: datetime.date
    week_end: datetime.date
    estimated: bool
    figures: FiguresOut
    pools: dict[str, PoolOut]


class ConfigOut(BaseModel):
    income_mode: str
    fixed_mode: str
    manual_income: float | None
    manual_fixed: float | None
    savings_target: float
    week_starts_on: int


class ConfigIn(BaseModel):
    """A change to the budget configuration.

    `effective_from` defaults to today rather than to the beginning of time:
    versioning exists so that changing the savings target does not retroactively
    rewrite what last month's weeks were allowed to spend.
    """
    effective_from: datetime.date | None = None
    income_mode: Literal["derived", "manual"] | None = None
    fixed_mode: Literal["derived", "manual"] | None = None
    manual_income: float | None = Field(default=None, ge=0)
    manual_fixed: float | None = Field(default=None, ge=0)
    savings_target: float | None = Field(default=None, ge=0)
    week_starts_on: int | None = Field(default=None, ge=1, le=7)

    @model_validator(mode="after")
    def _something_to_change(self) -> "ConfigIn":
        if all(getattr(self, field) is None for field in (
                "income_mode", "fixed_mode", "manual_income", "manual_fixed",
                "savings_target", "week_starts_on")):
            raise ValueError("no configuration fields given")
        return self


# --- categories ------------------------------------------------------------

class CategoryOut(BaseModel):
    """`name` is the identifier rules key on; `label` is what the UI shows.

    Both are sent because they are different things: the client displays the
    label but sends the name back on a PATCH, and conflating them would mean
    a rule silently detaching the day a label is reworded.
    """
    id: int
    name: str
    label: str
    kind: str
    budget_treatment: str
    cash_treatment: str


class CategoryPatch(BaseModel):
    budget_treatment: BudgetTreatment


class AccountOut(BaseModel):
    id: int
    name: str
    kind: str


# --- reimbursements --------------------------------------------------------

class ReimbursementOut(BaseModel):
    id: int
    transaction_id: int
    date: str
    description: str
    expected_from: str
    expected_amount: float
    note: str | None
    settled_at: str | None


class ReimbursementIn(BaseModel):
    transaction_id: int
    expected_from: str = Field(min_length=1)
    note: str | None = None


class SettleIn(BaseModel):
    settled_by_transaction_id: int | None = None
    settled_at: datetime.date | None = None


# --- imports ---------------------------------------------------------------

class PreviewRow(BaseModel):
    date: str
    description: str
    amount: float
    category: str
    needs_review: bool
    status: Literal["new", "existing"]


class PreviewOut(BaseModel):
    """What committing this file would do.

    Counts first, because that is the decision: "43 rows, 38 already here, 5
    new, 2 need review" is what a person needs before pressing commit. The
    rows follow for the ones being added.
    """
    account: str
    total: int
    new: int
    existing: int
    needs_review: int
    rows: list[PreviewRow]


class ImportOut(BaseModel):
    account: str
    inserted: int
    skipped: int
    derived: int
