from pathlib import Path

import pytest

from camt import CamtParseError
from camt.camt047 import Camt047Response, parse_camt047

FIXTURES = Path(__file__).parent / "fixtures"
SUCCESS = (FIXTURES / "camt047_success_sample.xml").read_bytes()
ERROR = (FIXTURES / "camt047_error_sample.xml").read_bytes()


def test_parse_camt047_success_response():
    result = parse_camt047(SUCCESS)

    assert isinstance(result, Camt047Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-25T08:00:00"
    assert result.account_iban == "IT60X0542811101000000123456"
    assert result.account_other_id is None
    assert result.error_code is None
    assert result.error_description is None


def test_parse_camt047_reads_all_reservations():
    reservations = parse_camt047(SUCCESS).reservations

    assert [(r.type_code, r.default) for r in reservations] == [
        ("MMR", False), ("STO", False), ("HPAR", False), ("MMR", True),
    ]
    mmr, sto, _, default = reservations
    assert (mmr.amount, mmr.currency, mmr.status) == (50000.00, "EUR", "ENAB")
    assert mmr.from_date == "2026-09-01"
    assert mmr.to_date is None
    assert (sto.amount, sto.status, sto.from_date) == (1200.00, "DISA", None)
    assert (default.amount, default.status) == (40000.00, None)


def test_parse_camt047_reservation_reported_with_an_error():
    hpar = parse_camt047(SUCCESS).reservations[2]

    assert (hpar.error_code, hpar.error_description) == ("NOT_SET", "No such reservation on the account")
    assert (hpar.amount, hpar.currency, hpar.status) == (0.0, "", None)


def test_parse_camt047_error_response_has_no_reservations():
    result = parse_camt047(ERROR)

    assert result.response_msg_id == "RESP-0002"
    assert result.original_msg_id == "REQ-0002"
    assert result.reservations is None
    assert result.error_code == "NOT_FOUND"
    assert result.error_description == "Account not found"


def test_parse_camt047_start_as_a_date_time():
    xml = SUCCESS.replace(b"<Dt>2026-09-01</Dt>", b"<DtTm>2026-09-01T07:00:00</DtTm>")

    assert parse_camt047(xml).reservations[0].from_date == "2026-09-01T07:00:00"


def test_parse_camt047_amount_without_currency():
    xml = SUCCESS.replace(b'<AmtWthCcy Ccy="EUR">1200.00</AmtWthCcy>', b"<AmtWthtCcy>1200.00</AmtWthtCcy>")

    sto = parse_camt047(xml).reservations[1]
    assert (sto.amount, sto.currency) == (1200.00, "")


def test_parse_camt047_any_version():
    assert parse_camt047(SUCCESS.replace(b"camt.047.001.08", b"camt.047.001.05")).response_msg_id == "RESP-0001"


def test_parse_camt047_not_a_camt047_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(CamtParseError, match="camt.047"):
        parse_camt047(bogus)


def test_parse_camt047_neither_report_nor_error_raises():
    xml = SUCCESS.split(b"<RptOrErr>")[0] + b"<RptOrErr/></RtrRsvatn></Document>"
    with pytest.raises(CamtParseError, match="BizRpt"):
        parse_camt047(xml)


def test_parse_camt047_report_with_no_reservations():
    xml = SUCCESS.split(b"<BizRpt>")[0] + b"<BizRpt/></RptOrErr></RtrRsvatn></Document>"

    result = parse_camt047(xml)

    assert result.reservations == []
    assert (result.account_iban, result.account_other_id) == (None, None)
