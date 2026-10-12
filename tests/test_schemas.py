"""Every camt message the library builds, and every fixture, against ISO 20022's schemas.

The schemas in tests/xsd/ are the Cash Management message set of the ISO 20022
catalogue, 2025/2026 edition: the newest version of each family the library handles.
A message in an older version is checked against the newest with its namespace
changed to that version's: newer versions mostly add optional elements, so a
message valid in both is valid in its own version too.

What isn't valid yet is marked `xfail(strict=True)`, with the reason: fixing it makes
the test pass, and the strict mark then fails until it's removed. The messages are
moving to the newest versions family by family (camt.052/053/054 and the liquidity
transfers, camt.050/025, are there).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import cache
from pathlib import Path

import pytest
from lxml import etree

from camt import (
    Balance,
    CreditDebit,
    Document,
    Entry,
    EntryStatus,
    MessageType,
    Party,
    ReturnInfo,
    Statement,
    TransactionDetails,
    build_bytes,
)
from camt._investigation import CaseAssignment
from camt.camt003 import build_get_account_request_bytes
from camt.camt005 import build_get_transaction_delta_request_bytes, build_get_transaction_request_bytes
from camt.camt018 import build_get_business_day_request_bytes
from camt.camt029 import RecallAnswer, ResolutionOfInvestigation, build_resolution_bytes
from camt.camt046 import build_get_reservation_request_bytes
from camt.camt048 import build_modify_reservation_request_bytes
from camt.camt049 import build_delete_reservation_request_bytes
from camt.camt050 import build_liquidity_transfer_bytes
from camt.camt056 import PaymentCancellationRequest, RecalledPayment, build_cancellation_request_bytes

TESTS = Path(__file__).parent
SCHEMAS = TESTS / "xsd"
FIXTURES = TESTS / "fixtures"

# The newest version of each family in SCHEMAS: "camt.053" -> "camt.053.001.14".
NEWEST = {path.stem[:8]: path.stem for path in SCHEMAS.glob("camt.*.xsd")}

NOW = datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc)
ALPHA = "DEAN-IT-0001-ALPHA"
IBAN = "IT60X0542811101000000123456"

# Not valid yet: the structure the library writes or reads isn't ISO 20022's. Each
# family is to be rewritten to its newest version, with the mock DESP that speaks it.
RESERVATIONS = "reservations (camt.046 to camt.049): not ISO's structure yet"
ACCOUNTS = "account and business day services (camt.003 to camt.006, camt.018, camt.019): not ISO's structure yet"


@cache
def schema(version: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / f"{version}.xsd")))


def schema_errors(xml: bytes) -> list[str]:
    """What the newest schema of `xml`'s family finds wrong in it; empty when it's valid."""
    root = etree.fromstring(xml)
    own_version = etree.QName(root).namespace.rsplit(":", 1)[1]
    newest = NEWEST[own_version[:8]]
    checker = schema(newest)
    if checker.validate(etree.fromstring(xml.replace(own_version.encode(), newest.encode(), 1))):
        return []
    return [error.message for error in checker.error_log]


def _statement_document(message_type: MessageType) -> Document:
    """A statement, report or notification with every element the builder can write."""
    debtor = Party(name="Bruno Bianchi", other_id="DEAN-IT-0002-BETA", bic="BCITITMMXXX")
    creditor = Party(name="Alice Rossi", iban=IBAN)
    details = TransactionDetails(
        amount=Decimal("80.00"), currency="EUR", credit_debit=CreditDebit.CREDIT, end_to_end_id="E2E-0001",
        instruction_id="INSTR-0001", account_servicer_ref="DESP-TX-0001", message_id="BCIPAY-0001",
        remittance_info="Invoice 2026-042", bank_transaction_code="PMNT-RCDT-ESCT", debtor=debtor,
        creditor=creditor,
    )
    returned = TransactionDetails(
        amount=Decimal("20.00"), currency="EUR", credit_debit=CreditDebit.CREDIT, end_to_end_id="E2E-0002",
        bank_transaction_code="RTRN-0001",
        return_info=ReturnInfo(reason_code="FOCR", additional_info="Recall accepted"),
    )
    balances = [] if message_type is MessageType.CAMT_054 else [
        Balance("OPBD", Decimal("1000.00"), "EUR", CreditDebit.CREDIT, date(2026, 10, 12)),
        Balance("CLBD", Decimal("1100.00"), "EUR", CreditDebit.CREDIT, date(2026, 10, 12)),
    ]
    return Document(
        message_type=message_type,
        message_id="DESP-0001",
        creation_datetime=NOW,
        page_number=1,
        last_page=True,
        statements=[Statement(
            id="STMT-0001", creation_datetime=NOW, from_date=date(2026, 10, 12), to_date=date(2026, 10, 12),
            account_other_id=ALPHA, account_currency="EUR", account_owner=Party(name="Alice Rossi", bic="UNCRITM1XXX"),
            servicer_bic="DESPEUFFXXX", balances=balances,
            entries=[
                Entry(
                    Decimal("100.00"), "EUR", CreditDebit.CREDIT, EntryStatus.BOOKED, booking_date=date(2026, 10, 12),
                    value_date=date(2026, 10, 12), account_servicer_ref="DESP-0001", bank_transaction_code="PMNT-RCDT-ESCT",
                    additional_info="Two payments", transaction_details=[details, returned],
                ),
                Entry(Decimal("5.00"), "EUR", CreditDebit.DEBIT, EntryStatus.PENDING),
            ],
        )],
    )


# Each message with every optional element the library can write.
BUILT = {
    "camt.003": lambda: build_get_account_request_bytes(IBAN, "PSPQRY-0001", creation_datetime=NOW),
    "camt.005": lambda: build_get_transaction_request_bytes(
        IBAN, "PSPQRY-0002", from_datetime=NOW, to_datetime=NOW, entry_status="BOOK", new_query_name="QRY-1",
        creation_datetime=NOW,
    ),
    "camt.005 delta": lambda: build_get_transaction_delta_request_bytes("QRY-1", "PSPQRY-0003", creation_datetime=NOW),
    "camt.018": lambda: build_get_business_day_request_bytes(
        "DESP", "PSPQRY-0004", business_date=date(2026, 10, 12), creation_datetime=NOW,
    ),
    "camt.029": lambda: build_resolution_bytes(ResolutionOfInvestigation(
        assignment=CaseAssignment("RES-0001", "BCITITMMXXX", "UNCRITM1XXX", NOW),
        status="RJCR", resolved_case_id="CASE-0001", resolved_case_creator_bic="UNCRITM1XXX",
        answers=[RecallAnswer(
            original_message_id="PSPPAY-0001", original_end_to_end_id="E2E-0001", status="RJCR", reason_code="CUST",
            additional_info="Goods delivered", original_amount=Decimal("100.00"), cancellation_status_id="CXLSTS-0001",
        )],
    )),
    "camt.046": lambda: build_get_reservation_request_bytes(IBAN, "PSPQRY-0005", reservation_type="UPAR", creation_datetime=NOW),
    "camt.048": lambda: build_modify_reservation_request_bytes(IBAN, "UPAR", 500.0, msg_id="PSPRSV-0001", creation_datetime=NOW),
    "camt.049": lambda: build_delete_reservation_request_bytes(IBAN, "UPAR", msg_id="PSPRSV-0002", creation_datetime=NOW),
    "camt.050": lambda: build_liquidity_transfer_bytes(
        "MCA-IT-UNCRITM1-0001", "DCA-IT-UNCRITM1-0001", 1000.0, msg_id="PSPLT-0001", end_to_end_id="E2E-LT-0001",
        creation_datetime=NOW,
    ),
    "camt.052": lambda: build_bytes(_statement_document(MessageType.CAMT_052)),
    "camt.053": lambda: build_bytes(_statement_document(MessageType.CAMT_053)),
    "camt.054": lambda: build_bytes(_statement_document(MessageType.CAMT_054)),
    "camt.056": lambda: build_cancellation_request_bytes(PaymentCancellationRequest(
        assignment=CaseAssignment("RCL-0001", "UNCRITM1XXX", "BCITITMMXXX", NOW),
        case_id="CASE-0001",
        payments=[RecalledPayment(
            original_message_id="PSPPAY-0001", original_end_to_end_id="E2E-0001", reason_code="DUPL",
            original_amount=Decimal("100.00"), cancellation_id="CXL-0001", additional_info="Paid twice",
        )],
    )),
}

BUILT_NOT_VALID_YET = {
    "camt.003": ACCOUNTS,
    "camt.005": ACCOUNTS,
    "camt.018": ACCOUNTS,
    "camt.046": RESERVATIONS,
    "camt.048": RESERVATIONS,
    "camt.049": RESERVATIONS,
}

# Fixtures that are invalid on purpose: what the parser must tolerate.
INVALID_ON_PURPOSE = {
    "camt053_paginated_page1_no_last_pg_ind.xml",  # MsgPgntn without LastPgInd
}

FIXTURES_NOT_VALID_YET = {
    "camt004_error_sample.xml": ACCOUNTS,
    "camt004_success_sample.xml": ACCOUNTS,
    "camt006_delta_sample.xml": ACCOUNTS,
    "camt006_error_sample.xml": ACCOUNTS,
    "camt006_full_sample.xml": ACCOUNTS,
    "camt019_error_sample.xml": ACCOUNTS,
    "camt019_success_sample.xml": ACCOUNTS,
    "camt047_error_sample.xml": RESERVATIONS,
    "camt047_success_sample.xml": RESERVATIONS,
}

# Families no built message nor fixture checks yet: parsed only from inline XML.
NOT_CHECKED_YET: dict[str, str] = {}

FIXTURE_FILES = sorted(
    path.name for path in FIXTURES.glob("camt*.xml") if path.name not in INVALID_ON_PURPOSE
)


def _not_valid_yet(name: str, known: dict[str, str]):
    reason = known.get(name, known.get(name.split()[0]))  # "camt.005 delta" goes with camt.005
    return pytest.param(name, marks=pytest.mark.xfail(reason=reason, strict=True)) if reason else name


@pytest.mark.parametrize("message", [_not_valid_yet(name, BUILT_NOT_VALID_YET) for name in BUILT])
def test_built_messages_are_valid(message):
    assert schema_errors(BUILT[message]()) == []


@pytest.mark.parametrize("fixture", [_not_valid_yet(name, FIXTURES_NOT_VALID_YET) for name in FIXTURE_FILES])
def test_fixtures_are_valid(fixture):
    assert schema_errors((FIXTURES / fixture).read_bytes()) == []


def test_statements_are_built_in_the_newest_version():
    for message_type in MessageType:
        root = etree.fromstring(build_bytes(_statement_document(message_type)))
        assert etree.QName(root).namespace.endswith(NEWEST[message_type.value])


def test_every_schema_checks_something():
    checked = {name[:8] for name in BUILT} | {
        f"camt.{name[4:7]}" for name in FIXTURE_FILES
    }

    assert set(NEWEST) == checked | set(NOT_CHECKED_YET)
    assert not checked & set(NOT_CHECKED_YET)


def test_the_invalid_fixtures_are_refused():
    """A control: the check isn't vacuous, and these fixtures stay invalid on purpose."""
    for name in INVALID_ON_PURPOSE:
        assert schema_errors((FIXTURES / name).read_bytes())


def test_the_schemas_refuse_a_misplaced_element():
    xml = BUILT["camt.053"]()
    misplaced = xml.replace(b"<AcctSvcrRef>DESP-0001</AcctSvcrRef>", b"", 1).replace(
        b"<CdtDbtInd>CRDT</CdtDbtInd>\n        <Sts>", b"<AcctSvcrRef>DESP-0001</AcctSvcrRef>\n<CdtDbtInd>CRDT</CdtDbtInd>\n        <Sts>", 1
    )
    assert misplaced != xml

    errors = schema_errors(misplaced)

    assert errors and "AcctSvcrRef" in errors[0]
