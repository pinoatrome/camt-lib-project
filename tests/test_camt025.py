import pytest

from camt.camt025 import ReceiptResult, parse_camt025

_NS = "urn:iso:std:iso:20022:tech:xsd:camt.025.001.05"


def _receipt_xml(body: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="{_NS}">
  <Receipt>
    <MsgHdr>
      <MsgId>RCPT-0001</MsgId>
      <CreDtTm>2026-09-02T10:05:00</CreDtTm>
    </MsgHdr>
    {body}
  </Receipt>
</Document>""".encode("utf-8")


def test_parse_camt025_settled_receipt():
    xml = _receipt_xml(
        """
    <RctDtls>
      <OrgnlBizInstr>
        <MsgId>LT-0001</MsgId>
      </OrgnlBizInstr>
      <OrgnlEndToEndId>E2E-0001</OrgnlEndToEndId>
      <ReqHdlg>
        <StsRsn>
          <Cd>STLD</Cd>
        </StsRsn>
      </ReqHdlg>
    </RctDtls>
    """
    )
    result = parse_camt025(xml)

    assert isinstance(result, ReceiptResult)
    assert result.receipt_msg_id == "RCPT-0001"
    assert result.created_at == "2026-09-02T10:05:00"
    assert result.status == "STLD"
    assert result.original_msg_id == "LT-0001"
    assert result.original_e2e_id == "E2E-0001"
    assert result.reject_code is None
    assert result.reject_desc is None


def test_parse_camt025_pending_receipt():
    xml = _receipt_xml(
        """
    <RctDtls>
      <OrgnlBizInstr>
        <MsgId>LT-0002</MsgId>
      </OrgnlBizInstr>
      <OrgnlEndToEndId>E2E-0002</OrgnlEndToEndId>
      <ReqHdlg>
        <StsRsn>
          <Cd>PDNG</Cd>
        </StsRsn>
      </ReqHdlg>
    </RctDtls>
    """
    )
    result = parse_camt025(xml)

    assert result.status == "PDNG"
    assert result.original_msg_id == "LT-0002"
    assert result.original_e2e_id == "E2E-0002"


def test_parse_camt025_rejected_receipt():
    xml = _receipt_xml(
        """
    <ReqRjctd>
      <RjctdReqRef>LT-0003</RjctdReqRef>
      <StsRsn>
        <Cd>AC04</Cd>
        <AddtlInf>Insufficient funds</AddtlInf>
      </StsRsn>
    </ReqRjctd>
    """
    )
    result = parse_camt025(xml)

    assert result.status == "RJCT"
    assert result.original_msg_id == "LT-0003"
    assert result.reject_code == "AC04"
    assert result.reject_desc == "Insufficient funds"
    assert result.original_e2e_id is None


def test_parse_camt025_missing_root_element_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(ValueError, match="Receipt"):
        parse_camt025(bogus)


def test_parse_camt025_missing_rct_dtls_and_req_rjctd_raises():
    xml = _receipt_xml("<Other/>")
    with pytest.raises(ValueError, match="RctDtls"):
        parse_camt025(xml)


def test_parse_camt025_defaults_status_to_unkn_when_code_missing():
    xml = _receipt_xml(
        """
    <RctDtls>
      <OrgnlBizInstr>
        <MsgId>LT-0004</MsgId>
      </OrgnlBizInstr>
    </RctDtls>
    """
    )
    result = parse_camt025(xml)

    assert result.status == "UNKN"
    assert result.original_msg_id == "LT-0004"
