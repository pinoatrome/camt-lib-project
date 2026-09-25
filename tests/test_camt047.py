from pathlib import Path

import pytest

from camt.camt047 import Camt047Response, parse_camt047

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_camt047_success_response():
    xml = (FIXTURES / "camt047_success_sample.xml").read_bytes()
    result = parse_camt047(xml)

    assert isinstance(result, Camt047Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-25T08:00:00"
    assert result.account_iban == "IT60X0542811101000000123456"
    assert result.account_other_id is None
    assert result.error_code is None
    assert result.error_description is None


def test_parse_camt047_reads_all_reservations():
    xml = (FIXTURES / "camt047_success_sample.xml").read_bytes()
    reservations = parse_camt047(xml).reservations

    assert len(reservations) == 2

    mmr, sto = reservations
    assert mmr.type_code == "MMR"
    assert mmr.amount == 50000.00
    assert mmr.currency == "EUR"
    assert mmr.status == "ACTV"
    assert mmr.from_date == "2026-09-01"
    assert mmr.to_date == "2026-09-30"

    assert sto.type_code == "STO"
    assert sto.amount == 1200.00
    assert sto.status == "CLSD"
    assert sto.from_date is None
    assert sto.to_date is None


def test_parse_camt047_error_response_has_no_reservations():
    xml = (FIXTURES / "camt047_error_sample.xml").read_bytes()
    result = parse_camt047(xml)

    assert result.response_msg_id == "RESP-0002"
    assert result.original_msg_id == "REQ-0002"
    assert result.reservations is None
    assert result.error_code == "NOT_FOUND"
    assert result.error_description == "Account not found"


def test_parse_camt047_missing_root_element_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(ValueError, match="RtrRsvatn"):
        parse_camt047(bogus)


def test_parse_camt047_account_with_no_reservations():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.047.001.05">
  <RtrRsvatn>
    <MsgHdr>
      <MsgId>RESP-0003</MsgId>
      <CreDtTm>2026-09-25T08:10:00</CreDtTm>
    </MsgHdr>
    <RptOrErr>
      <RsvatnRpt>
        <AcctId>
          <Othr>
            <Id>DEAN-IT-0003-GAMMA</Id>
          </Othr>
        </AcctId>
      </RsvatnRpt>
    </RptOrErr>
  </RtrRsvatn>
</Document>"""
    result = parse_camt047(xml)

    assert result.original_msg_id is None  # no <OrgnlBizQry>
    assert result.account_other_id == "DEAN-IT-0003-GAMMA"
    assert result.reservations == []
