from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from .enums import CreditDebit, EntryStatus, MessageType


@dataclass
class Party:
    name: str | None = None
    iban: str | None = None
    other_id: str | None = None
    bic: str | None = None


@dataclass
class Balance:
    code: str
    amount: Decimal
    currency: str
    credit_debit: CreditDebit
    date: date


@dataclass
class TransactionDetails:
    amount: Decimal | None = None
    currency: str | None = None
    credit_debit: CreditDebit | None = None
    end_to_end_id: str | None = None
    instruction_id: str | None = None
    account_servicer_ref: str | None = None
    remittance_info: str | None = None
    bank_transaction_code: str | None = None
    debtor: Party | None = None
    creditor: Party | None = None


@dataclass
class Entry:
    amount: Decimal
    currency: str
    credit_debit: CreditDebit
    status: EntryStatus
    booking_date: date | None = None
    value_date: date | None = None
    account_servicer_ref: str | None = None
    bank_transaction_code: str | None = None
    additional_info: str | None = None
    transaction_details: list[TransactionDetails] = field(default_factory=list)


@dataclass
class Statement:
    """One Stmt / Rpt / Ntfctn block."""

    id: str
    creation_datetime: datetime | None = None
    from_date: date | None = None
    to_date: date | None = None
    account_iban: str | None = None
    account_other_id: str | None = None
    account_currency: str | None = None
    account_owner: Party | None = None
    servicer_bic: str | None = None
    balances: list[Balance] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)

    def balance(self, code: str) -> Balance | None:
        return next((b for b in self.balances if b.code == code), None)

    @property
    def opening_balance(self) -> Balance | None:
        return self.balance("OPBD")

    @property
    def closing_balance(self) -> Balance | None:
        return self.balance("CLBD")


@dataclass
class Document:
    message_type: MessageType
    message_id: str
    creation_datetime: datetime | None = None
    statements: list[Statement] = field(default_factory=list)