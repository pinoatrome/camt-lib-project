from pathlib import Path

import pytest

from camt.camt006 import Camt006Response, parse_camt006

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_camt006_full_response_reports_query_name_and_new_transactions():
    xml = (FIXTURES / "camt006_full_sample.xml").read_bytes()
    result = parse_camt006(xml)

    assert isinstance(result, Camt006Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-02T10:00:00"
    assert result.query_name == "DAILY-RECON"
    assert result.error_code is None
    assert result.error_description is None

    txs = result.transactions
    assert txs is not None
    assert not txs.is_empty
    assert len(txs.new) == 2
    assert txs.modified == []
    assert txs.cancelled == []

    first, second = txs.new
    assert first.tx_id == "TX-0001"
    assert first.end_to_end_id == "E2E-0001"
    assert first.amount == 150.00
    assert first.currency == "EUR"
    assert first.credit_debit == "CRDT"
    assert first.status == "BOOK"
    assert first.booking_date == "2026-09-01"
    assert first.additional_info == "Invoice 1001"

    assert second.tx_id == "TX-0002"
    assert second.credit_debit == "DBIT"
    assert second.additional_info is None


def test_parse_camt006_delta_response_splits_new_modified_and_cancelled():
    xml = (FIXTURES / "camt006_delta_sample.xml").read_bytes()
    result = parse_camt006(xml)

    assert result.query_name == "DAILY-RECON"

    txs = result.transactions
    assert [tx.tx_id for tx in txs.new] == ["TX-0003"]
    assert [tx.tx_id for tx in txs.modified] == ["TX-0002"]
    assert [tx.tx_id for tx in txs.cancelled] == ["TX-0001"]

    modified = txs.modified[0]
    assert modified.status == "RJCT"
    assert modified.additional_info == "Returned by beneficiary bank"

    cancelled = txs.cancelled[0]
    assert cancelled.status == "CANC"


def test_parse_camt006_error_response_has_no_transactions():
    xml = (FIXTURES / "camt006_error_sample.xml").read_bytes()
    result = parse_camt006(xml)

    assert result.response_msg_id == "RESP-0003"
    assert result.original_msg_id == "REQ-0003"
    assert result.query_name == "UNKNOWN-QUERY"
    assert result.transactions is None
    assert result.error_code == "QUERY_NOT_FOUND"
    assert result.error_description == "Named query not found"


def test_parse_camt006_missing_root_element_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(ValueError, match="RtrTx"):
        parse_camt006(bogus)


def test_delta_transaction_set_is_empty_when_no_transactions():
    from camt.camt006 import DeltaTransactionSet

    assert DeltaTransactionSet().is_empty
