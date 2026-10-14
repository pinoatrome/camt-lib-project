"""Valid camt documents for tests: each function builds one with the library and checks it
against ISO 20022's schema (`validate`) before returning it, so a test that feeds the system
under test a camt document can't be feeding it an invalid one.

Everything has a default, so `notification_xml(Payment("120.00"))` is a complete, valid
camt.054; pass what the test is about. Ids default to `TEST-...`.

- camt.054 notification / camt.052 report / camt.053 statement: `notification_xml`,
  `statement_xml`, with the entries described by `Payment`.
- camt.004 ReturnAccount (a camt.003's answer, or an alert): `account_report_xml`,
  `account_error_xml`.
- camt.025 Receipt (a camt.050's answer): `receipt_xml`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .camt004 import AccountReport, Camt004Response, build_return_account_bytes
from .camt004 import Balance as AccountBalance
from .builder import build_bytes
from .camt025 import REJECTED, SETTLED, ReceiptResult, build_receipt_bytes
from .enums import CreditDebit, EntryStatus, MessageType
from .models import Balance, Document, Entry, Party, Statement, TransactionDetails
from .validation import validate

CREATED = datetime(2026, 10, 10, 12, 0, 0)
CREATED_TEXT = "2026-10-10T12:00:00.000Z"


@dataclass
class Payment:
    """One booked entry of a notification or statement, with its one transaction (unless `with_details` is off)."""

    amount: str | Decimal = "120.00"
    credit_debit: CreditDebit = CreditDebit.CREDIT
    end_to_end_id: str = "TEST-E2E-0001"
    servicer_ref: str = "TEST-TX-0001"
    counterparty: Party | None = None  # the debtor of a credit, the creditor of a debit
    remittance_info: str | None = None
    additional_info: str | None = None
    message_id: str | None = None  # the pacs.008 that carried it (Refs/MsgId)
    instruction_id: str | None = None
    bank_transaction_code: str | None = None  # e.g. PMNT-RCDT-ESCT
    with_details: bool = True  # False: the entry has no transaction details (NtryDtls), only its own data
    currency: str = "EUR"


def _entry(payment: Payment, booked: date) -> Entry:
    amount = Decimal(payment.amount)
    credit = payment.credit_debit == CreditDebit.CREDIT
    details = TransactionDetails(
        amount=amount, currency=payment.currency, credit_debit=payment.credit_debit,
        end_to_end_id=payment.end_to_end_id, instruction_id=payment.instruction_id,
        account_servicer_ref=payment.servicer_ref, message_id=payment.message_id, remittance_info=payment.remittance_info,
        debtor=payment.counterparty if credit else None, creditor=None if credit else payment.counterparty)
    return Entry(
        amount, payment.currency, payment.credit_debit, EntryStatus.BOOKED, booking_date=booked, value_date=booked,
        account_servicer_ref=payment.servicer_ref, bank_transaction_code=payment.bank_transaction_code,
        additional_info=payment.additional_info, transaction_details=[details] if payment.with_details else [])


def statement_xml(
    payments: Sequence[Payment] = (), *, message_type: MessageType = MessageType.CAMT_053,
    account: str = "DEAN-IT-0001-ALPHA", message_id: str = "TEST-STMT-0001", statement_id: str | None = None,
    created: datetime = CREATED, opening: str | Decimal | None = None, closing: str | Decimal | None = None,
    balances: Sequence[Balance] | None = None, owner_name: str | None = "MultiCredit SpA",
    owner_bic: str | None = "UNCRITM1XXX", servicer_bic: str | None = None, page_number: int | None = None,
    last_page: bool | None = None, currency: str = "EUR", statement_date: date | None = None,
) -> bytes:
    """A valid camt.053 (or camt.052 / camt.054 with `message_type`) of one account with one
    entry per payment. `account` is an IBAN (starting with two letters and two digits) or
    another id, e.g. a DEAN. `opening` and `closing` add the OPBD and CLBD balances (a page
    of a paginated statement has only one of them); `balances` gives them as they are. With
    none of the three, a camt.053 or camt.052 opens at 1000.00 and closes at what its
    payments make of it (a statement needs a balance); a camt.054 has none.
    `page_number` and `last_page` paginate it. The statement covers `statement_date` (the day it was
    created by default), and so do its entries and balances."""
    day = statement_date or created.date()
    if balances is None and opening is None and closing is None and message_type is not MessageType.CAMT_054:
        # A statement or report needs a balance: opening 1000.00, closing what the payments make of it.
        opening = Decimal("1000.00")
        closing = opening + sum(
            (Decimal(p.amount) if p.credit_debit == CreditDebit.CREDIT else -Decimal(p.amount) for p in payments),
            Decimal("0"))
    if balances is None:
        balances = [Balance(code, Decimal(value), currency, CreditDebit.CREDIT, day)
                    for code, value in (("OPBD", opening), ("CLBD", closing)) if value is not None]
    is_iban = account[:2].isalpha() and account[2:4].isdigit()
    return validate(build_bytes(Document(
        message_type=message_type, message_id=message_id, creation_datetime=created, page_number=page_number,
        last_page=last_page,
        statements=[Statement(
            id=statement_id or f"{message_id}-01", creation_datetime=created,
            from_date=None if message_type is MessageType.CAMT_054 else day,
            to_date=None if message_type is MessageType.CAMT_054 else day,
            account_iban=account if is_iban else None, account_other_id=None if is_iban else account,
            account_currency=currency, account_owner=Party(name=owner_name, bic=owner_bic) if owner_name or owner_bic else None,
            servicer_bic=servicer_bic, balances=list(balances),
            entries=[_entry(payment, day) for payment in payments])])))


def notification_xml(payment: Payment | None = None, *, message_id: str = "TEST-NTF-0001", **options) -> bytes:
    """A valid camt.054 debit/credit notification of one payment on an account; `options` as `statement_xml`
    (`account`, `created`, `owner_name`, ...)."""
    return statement_xml([payment or Payment()], message_type=MessageType.CAMT_054, message_id=message_id, **options)


def account_report_xml(
    dean: str = "DEAN-IT-0001-ALPHA", *, iban: str | None = None, status: str | None = "ENABLED",
    balance: str | Decimal = "2850.10", hold_limit: str | Decimal | None = "3000.00", currency: str = "EUR",
    original_message_id: str | None = "TEST-QRY-0001", message_id: str = "TEST-RESP-0001",
    created: str = CREATED_TEXT, balance_date: str = "2026-10-10", account_type: str = "DESP-DCA",
    owner_name: str = "MultiCredit SpA", owner_bic: str = "UNCRITM1XXX", servicer_name: str = "DESP - Banca d'Italia",
    account_scheme: str | None = "DEAN",
) -> bytes:
    """A valid camt.004 saying `dean` (and its `iban`) is in `status` with a closing balance (CLBD) of
    `balance` and a holding limit of `hold_limit`: the answer to a camt.003, or, with
    `original_message_id=None`, an alert nobody asked for."""
    return validate(build_return_account_bytes(Camt004Response(
        response_msg_id=message_id, original_msg_id=original_message_id, created_at=created,
        account=AccountReport(
            dean=dean, iban=iban, currency=currency, status=status, psp_bic=owner_bic, psp_name=owner_name,
            servicer_name=servicer_name, account_type=account_type,
            balances=[AccountBalance("CLBD", float(balance), currency, balance_date)],
            hold_limit=float(hold_limit) if hold_limit is not None else None, hold_limit_ccy=currency)),
        account_scheme=account_scheme))


def account_error_xml(
    dean: str = "DEAN-UNKNOWN", *, code: str = "NFND", description: str | None = None,
    original_message_id: str | None = "TEST-QRY-0001", message_id: str = "TEST-RESP-0001", created: str = CREATED_TEXT,
) -> bytes:
    """A valid camt.004 reporting a business error (default NFND, not found) about the account `dean`."""
    return validate(build_return_account_bytes(Camt004Response(
        response_msg_id=message_id, original_msg_id=original_message_id, created_at=created, error_code=code,
        error_description=description or f"Account not found: {dean}"), error_account_id=dean))


def receipt_xml(
    *, original_message_id: str, status: str = SETTLED, reject_code: str | None = None,
    reject_desc: str | None = None, receipt_id: str = "TEST-RCPT-0001", created: str = "2026-10-10T09:15:02",
) -> bytes:
    """A valid camt.025 receipt for the camt.050 `original_message_id`: STLD settled by default, PDNG pending,
    or RJCT rejected with a `reject_code` such as AM04."""
    if status == REJECTED and reject_code is None:
        reject_code = "AM04"
    return validate(build_receipt_bytes(ReceiptResult(
        receipt_msg_id=receipt_id, created_at=created, status=status, original_msg_id=original_message_id,
        reject_code=reject_code, reject_desc=reject_desc)))
