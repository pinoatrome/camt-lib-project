from pathlib import Path

import pytest

from camt.camt004 import Camt004Response, parse_camt004

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_camt004_success_response():
    xml = (FIXTURES / "camt004_success_sample.xml").read_bytes()
    result = parse_camt004(xml)

    assert isinstance(result, Camt004Response)
    assert result.response_msg_id == "RESP-0001"
    assert result.original_msg_id == "REQ-0001"
    assert result.created_at == "2026-09-02T10:00:00"
    assert result.error_code is None
    assert result.error_description is None

    account = result.account
    assert account is not None
    assert account.dean == "DEAN-IT-0001-ALPHA"
    assert account.iban == "IT60X0542811101000000123456"
    assert account.currency == "EUR"
    assert account.status == "ENABLED"
    assert account.psp_bic == "PSPXITMMXXX"
    assert account.psp_name == "Alpha PSP"
    assert account.servicer_name == "DESP Servicer"
    assert account.account_type == "PAYM"
    assert account.hold_limit == 5000.00
    assert account.hold_limit_ccy == "EUR"


def test_parse_camt004_reads_all_holding_balances():
    xml = (FIXTURES / "camt004_success_sample.xml").read_bytes()
    balances = parse_camt004(xml).account.balances

    assert len(balances) == 2

    closing, available = balances
    assert closing.type_code == "CLBD"
    assert closing.amount == 1250.50
    assert closing.currency == "EUR"
    assert closing.date == "2026-09-01"

    # Second balance's <Tp><CdOrPrtry> uses <Prtry> instead of <Cd>, and its
    # <Dt> uses <DtTm> instead of <Dt> -- both fall back correctly.
    assert available.type_code == "AVLB"
    assert available.amount == 900.00
    assert available.date == "2026-09-02T09:00:00"


def test_parse_camt004_error_response_has_no_account():
    xml = (FIXTURES / "camt004_error_sample.xml").read_bytes()
    result = parse_camt004(xml)

    assert result.response_msg_id == "RESP-0002"
    assert result.original_msg_id == "REQ-0002"
    assert result.account is None
    assert result.error_code == "NOT_FOUND"
    assert result.error_description == "Account not found"


def test_parse_camt004_missing_root_element_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(ValueError, match="RtrAcct"):
        parse_camt004(bogus)


def test_parse_camt004_account_without_holding_balances_or_limit():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.004.001.08">
  <RtrAcct>
    <MsgHdr>
      <MsgId>RESP-0003</MsgId>
      <CreDtTm>2026-09-02T10:10:00</CreDtTm>
    </MsgHdr>
    <RptOrErr>
      <AcctRpt>
        <AcctId>
          <Othr>
            <Id>DEAN-IT-0003-GAMMA</Id>
          </Othr>
        </AcctId>
        <AcctOrErr>
          <Acct>
            <Id>
              <IBAN>IT60X0542811101000000999999</IBAN>
            </Id>
            <Ccy>EUR</Ccy>
            <Sts>
              <Cd>SUSPENDED</Cd>
            </Sts>
          </Acct>
        </AcctOrErr>
      </AcctRpt>
    </RptOrErr>
  </RtrAcct>
</Document>"""
    result = parse_camt004(xml)

    assert result.original_msg_id is None  # no <OrgnlBizInstr>
    account = result.account
    assert account.status == "SUSPENDED"
    assert account.balances == []
    assert account.hold_limit is None
    assert account.hold_limit_ccy is None
    assert account.psp_bic is None
    assert account.servicer_name is None
