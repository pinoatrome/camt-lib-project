from pathlib import Path

import pytest

from camt import CamtParseError
from camt.camt025 import PENDING, REJECTED, SETTLED, ReceiptResult, parse_camt025

FIXTURES = Path(__file__).parent / "fixtures"
SETTLED_XML = (FIXTURES / "camt025_settled_sample.xml").read_bytes()
REJECTED_XML = (FIXTURES / "camt025_rejected_sample.xml").read_bytes()


def test_parse_camt025_settled_receipt():
    result = parse_camt025(SETTLED_XML)

    assert isinstance(result, ReceiptResult)
    assert result.receipt_msg_id == "RCPT-0001"
    assert result.created_at == "2026-09-02T10:05:00"
    assert result.status == SETTLED
    assert result.original_msg_id == "LT-0001"
    assert result.original_e2e_id is None
    assert result.reject_code is None
    assert result.reject_desc is None


def test_parse_camt025_pending_receipt():
    result = parse_camt025(SETTLED_XML.replace(b"<Cd>STLD</Cd>", b"<Cd>PDNG</Cd>"))

    assert result.status == PENDING
    assert result.original_msg_id == "LT-0001"


def test_parse_camt025_rejected_receipt():
    result = parse_camt025(REJECTED_XML)

    assert result.status == REJECTED
    assert result.original_msg_id == "LT-0003"
    assert result.reject_code == "AM04"
    assert result.reject_desc == "Insufficient funds on DCA-IT-UNCRITM1-0001."


def test_parse_camt025_rejection_described_in_desc():
    xml = REJECTED_XML.replace(b"<AddtlInf>Insufficient funds</AddtlInf>", b"").replace(
        b"<AddtlInf>on DCA-IT-UNCRITM1-0001.</AddtlInf>", b""
    ).replace(b"</StsRsn>", b"</StsRsn>\n        <Desc>Insufficient funds</Desc>")

    assert parse_camt025(xml).reject_desc == "Insufficient funds"


def test_parse_camt025_reads_the_end_to_end_id_when_there_is_one():
    xml = SETTLED_XML.replace(b"</OrgnlMsgId>", b"""</OrgnlMsgId>
      <OrgnlPmtId><LngBizId><IntrBkSttlmAmt>10</IntrBkSttlmAmt><IntrBkSttlmDt>2026-09-02</IntrBkSttlmDt>
        <InstgAgt><FinInstnId><BICFI>UNCRITM1XXX</BICFI></FinInstnId></InstgAgt>
        <InstdAgt><FinInstnId><BICFI>DESPEUFFXXX</BICFI></FinInstnId></InstdAgt>
        <EndToEndId>E2E-0001</EndToEndId></LngBizId></OrgnlPmtId>""")

    assert parse_camt025(xml).original_e2e_id == "E2E-0001"


def test_parse_camt025_any_version():
    assert parse_camt025(SETTLED_XML.replace(b"camt.025.001.09", b"camt.025.001.05")).status == SETTLED


def test_parse_camt025_not_a_receipt_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(CamtParseError, match="camt.025"):
        parse_camt025(bogus)


def test_parse_camt025_missing_rct_dtls_raises():
    xml = SETTLED_XML.split(b"<RctDtls>")[0] + b"</Rct></Document>"
    with pytest.raises(CamtParseError, match="RctDtls"):
        parse_camt025(xml)


def test_parse_camt025_defaults_status_to_unkn_when_code_missing():
    xml = SETTLED_XML.replace(b"<Sts>\n          <Cd>STLD</Cd>\n        </Sts>", b"")

    assert parse_camt025(xml).status == "UNKN"


# ── Building ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("xml", [SETTLED_XML, REJECTED_XML])
def test_a_built_receipt_parses_back_to_the_same_and_is_valid(xml):
    from camt import schema_errors
    from camt.camt025 import build_receipt_bytes

    receipt = parse_camt025(xml)

    built = build_receipt_bytes(receipt)

    assert schema_errors(built) == []
    assert parse_camt025(built) == receipt


def test_a_receipt_with_an_end_to_end_id_cannot_be_built():
    from camt import CamtError
    from camt.camt025 import build_receipt_bytes

    receipt = parse_camt025(SETTLED_XML)
    receipt.original_e2e_id = "E2E-1"

    with pytest.raises(CamtError, match="long business id"):
        build_receipt_bytes(receipt)
