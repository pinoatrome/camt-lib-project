from pathlib import Path

import pytest

from camt import CamtParseError
from camt.camt006 import Camt006Response, parse_camt006

FIXTURES = Path(__file__).parent / "fixtures"
FULL = (FIXTURES / "camt006_full_sample.xml").read_bytes()
DELTA = (FIXTURES / "camt006_delta_sample.xml").read_bytes()


def test_parse_camt006_full_response_reports_query_name_and_transactions():
    result = parse_camt006(FULL)

    assert isinstance(result, Camt006Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-02T10:00:00"
    assert result.query_name == "DAILY-RECON"
    assert result.error_code is None
    assert result.error_description is None

    first, second = result.transactions
    assert first.tx_id == "TX-0001"
    assert first.end_to_end_id == "E2E-0001"
    assert (first.amount, first.currency, first.credit_debit) == (150.00, "EUR", "CRDT")
    assert (first.status, first.payment_status) == ("BOOK", "STLD")
    assert first.booking_date == "2026-09-01"
    assert first.additional_info == "Invoice 1001"

    assert second.tx_id == "TX-0002"
    assert second.credit_debit == "DBIT"
    assert second.additional_info is None


def test_parse_camt006_delta_response_lists_what_changed():
    result = parse_camt006(DELTA)

    assert result.query_name == "DAILY-RECON"
    assert [(tx.tx_id, tx.payment_status) for tx in result.transactions] == [
        ("TX-0003", "STLD"), ("TX-0002", "RJTD"), ("TX-0001", "CAND"), ("TX-0009", None),
    ]
    rejected, cancelled = result.transactions[1:3]
    assert rejected.additional_info == "Returned by beneficiary bank"
    assert cancelled.status == "PDNG"


def test_parse_camt006_transaction_reported_with_an_error():
    unknown = parse_camt006(DELTA).transactions[3]

    assert (unknown.error_code, unknown.error_description) == ("TX_UNKNOWN", "No such transaction any more")
    assert (unknown.amount, unknown.currency, unknown.status) == (0.0, "", None)


def test_parse_camt006_amount_from_the_payment_without_an_entry():
    xml = FULL.split(b"<AcctNtry>")[0] + b"</Tx></TxOrErr></TxRpt></BizRpt></RptOrErr></RtrTx></Document>"

    only = parse_camt006(xml).transactions[0]
    assert (only.amount, only.currency, only.status) == (150.00, "EUR", None)


def test_parse_camt006_error_response_has_no_transactions():
    result = parse_camt006((FIXTURES / "camt006_error_sample.xml").read_bytes())

    assert result.response_msg_id == "RESP-0003"
    assert result.original_msg_id == "REQ-0003"
    assert result.query_name == "UNKNOWN-QUERY"
    assert result.transactions is None
    assert result.error_code == "QUERY_NOT_FOUND"
    assert result.error_description == "Named query not found"


def test_parse_camt006_any_version():
    assert len(parse_camt006(FULL.replace(b"camt.006.001.11", b"camt.006.001.08")).transactions) == 2


def test_parse_camt006_not_a_camt006_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(CamtParseError, match="camt.006"):
        parse_camt006(bogus)


def test_parse_camt006_neither_report_nor_error_raises():
    xml = FULL.split(b"<RptOrErr>")[0] + b"<RptOrErr/></RtrTx></Document>"
    with pytest.raises(CamtParseError, match="BizRpt"):
        parse_camt006(xml)
