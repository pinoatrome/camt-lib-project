"""Reconciliation-oriented helpers for camt.054 payment-settlement notifications.

Scenario 3 ("Pagamento settlato"): every settled payment produces two
camt.054 DebitCreditNotification messages — a debit to the payer's PSP, a
credit to the beneficiary's PSP — each reporting exactly one entry, which the
PSP's reconciliation engine matches back to the originating pacs.008 payment
via the entry's EndToEndId. camt.054 is otherwise an ordinary report message
already handled generically by `camt.parser`/`camt.builder`
(`MessageType.CAMT_054`); this module only adds a narrower, single-entry view
on top of that generic `Document` parse — it doesn't reparse the XML itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from .enums import CreditDebit
from .exceptions import CamtParseError
from .models import Entry
from .parser import parse_bytes


@dataclass
class DebitCreditNotification:
    """A single-entry camt.054 payment-settlement notification."""

    message_id: str
    account_iban: str | None
    account_other_id: str | None
    entry: Entry

    @property
    def is_debit(self) -> bool:
        return self.entry.credit_debit is CreditDebit.DEBIT

    @property
    def is_credit(self) -> bool:
        return self.entry.credit_debit is CreditDebit.CREDIT

    @property
    def end_to_end_id(self) -> str | None:
        """The originating pacs.008 payment's EndToEndId, for reconciliation."""
        if not self.entry.transaction_details:
            return None
        return self.entry.transaction_details[0].end_to_end_id


def parse_debit_credit_notification(xml_bytes: bytes) -> DebitCreditNotification:
    """Parse a camt.054 payment-settlement notification: a `Document` with exactly
    one `<Ntfctn>` reporting exactly one `<Ntry>`."""
    document = parse_bytes(xml_bytes)

    if len(document.statements) != 1:
        raise CamtParseError(
            "Expected exactly one <Ntfctn> in a payment-settlement notification, "
            f"found {len(document.statements)}"
        )
    statement = document.statements[0]

    if len(statement.entries) != 1:
        raise CamtParseError(
            "Expected exactly one <Ntry> in a payment-settlement notification, "
            f"found {len(statement.entries)}"
        )

    return DebitCreditNotification(
        message_id=document.message_id,
        account_iban=statement.account_iban,
        account_other_id=statement.account_other_id,
        entry=statement.entries[0],
    )
