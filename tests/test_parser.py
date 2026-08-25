from decimal import Decimal
from pathlib import Path

import pytest

from camt import CreditDebit, EntryStatus, MessageType, UnsupportedMessageType, parse_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_camt053():
    doc = parse_file(FIXTURES / "camt053_sample.xml")

    assert doc.message_type is MessageType.CAMT_053
    assert doc.message_id == "MSG-0001"
    assert len(doc.statements) == 1

    stmt = doc.statements[0]
    assert stmt.id == "STMT-0001"
    assert stmt.account_iban == "IT60X0542811101000000123456"
    assert stmt.account_currency == "EUR"
    assert stmt.account_owner.name == "Acme S.r.l."
    assert stmt.servicer_bic == "BPMOIT22XXX"

    assert stmt.opening_balance.amount == Decimal("1000.00")
    assert stmt.closing_balance.amount == Decimal("1250.50")
    assert stmt.closing_balance.credit_debit is CreditDebit.CREDIT

    assert len(stmt.entries) == 2
    credit_entry, debit_entry = stmt.entries

    assert credit_entry.amount == Decimal("300.50")
    assert credit_entry.credit_debit is CreditDebit.CREDIT
    assert credit_entry.status is EntryStatus.BOOKED
    assert credit_entry.bank_transaction_code == "PMNT-RCDT-ESCT"
    assert credit_entry.additional_info == "Invoice payment"

    assert len(credit_entry.transaction_details) == 1
    tx = credit_entry.transaction_details[0]
    assert tx.end_to_end_id == "E2E-1"
    assert tx.remittance_info == "Invoice 2026-042"
    assert tx.debtor.name == "Widget Buyer Ltd"
    assert tx.debtor.iban == "GB29NWBK60161331926819"

    assert debit_entry.credit_debit is CreditDebit.DEBIT
    assert debit_entry.amount == Decimal("50.00")
    assert debit_entry.transaction_details == []


def test_parse_camt052():
    doc = parse_file(FIXTURES / "camt052_sample.xml")

    assert doc.message_type is MessageType.CAMT_052
    stmt = doc.statements[0]
    assert stmt.id == "RPT-0001"
    assert stmt.balances[0].code == "ITBD"
    assert stmt.entries[0].status is EntryStatus.PENDING
    assert stmt.entries[0].bank_transaction_code == "PROP-CODE-1"
    # camt.052 GrpHdr/Rpt use DtTm-only dates in this fixture; still normalized to date.
    assert stmt.entries[0].booking_date is not None


def test_parse_camt054():
    doc = parse_file(FIXTURES / "camt054_sample.xml")

    assert doc.message_type is MessageType.CAMT_054
    stmt = doc.statements[0]
    assert stmt.id == "NTFY-0001"
    entry = stmt.entries[0]
    assert entry.amount == Decimal("75.25")
    assert entry.transaction_details[0].debtor.name == "Some Payer"


def test_parse_bytes_and_string_helpers():
    from camt import parse_bytes, parse_string

    xml_bytes = (FIXTURES / "camt053_sample.xml").read_bytes()
    assert parse_bytes(xml_bytes).message_id == "MSG-0001"
    assert parse_string(xml_bytes.decode("utf-8")).message_id == "MSG-0001"


def test_parse_file_accepts_open_binary_handle():
    with open(FIXTURES / "camt053_sample.xml", "rb") as f:
        doc = parse_file(f)
    assert doc.message_id == "MSG-0001"


def test_unsupported_message_type_raises():
    from camt.exceptions import CamtParseError

    with pytest.raises(CamtParseError):
        parse_file(FIXTURES / "not_xml.txt")


def test_unrecognized_wrapper_raises(tmp_path):
    bogus = tmp_path / "bogus.xml"
    bogus.write_text(
        '<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    )
    with pytest.raises(UnsupportedMessageType):
        parse_file(bogus)
