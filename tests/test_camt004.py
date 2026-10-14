from pathlib import Path

from decimal import Decimal

import pytest

from camt import CamtParseError
from camt.camt004 import Camt004Response, parse_camt004

FIXTURES = Path(__file__).parent / "fixtures"
SUCCESS = (FIXTURES / "camt004_success_sample.xml").read_bytes()


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


def test_parse_camt004_not_a_camt004_raises():
    bogus = b'<?xml version="1.0"?><Document xmlns="urn:example"><SomethingElse/></Document>'
    with pytest.raises(CamtParseError, match="camt.004"):
        parse_camt004(bogus)


def test_parse_camt004_operational_error():
    xml = SUCCESS.split(b"<RptOrErr>")[0] + b"""<RptOrErr>
      <OprlErr><Err><Cd>X020</Cd></Err><Desc>Service unavailable</Desc></OprlErr>
    </RptOrErr></RtrAcct></Document>"""

    result = parse_camt004(xml)

    assert result.account is None
    assert (result.error_code, result.error_description) == ("X020", "Service unavailable")


def test_parse_camt004_account_without_balances_limit_or_status():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.004.001.10">
  <RtrAcct>
    <MsgHdr>
      <MsgId>RESP-0003</MsgId>
      <CreDtTm>2026-09-02T10:10:00</CreDtTm>
    </MsgHdr>
    <RptOrErr>
      <AcctRpt>
        <AcctId>
          <IBAN>IT60X0542811101000000999999</IBAN>
        </AcctId>
        <AcctOrErr>
          <Acct>
            <Ccy>EUR</Ccy>
          </Acct>
        </AcctOrErr>
      </AcctRpt>
    </RptOrErr>
  </RtrAcct>
</Document>"""
    result = parse_camt004(xml)

    assert result.original_msg_id is None  # an alert: no <OrgnlBizQry>
    account = result.account
    assert (account.dean, account.iban) == (None, "IT60X0542811101000000999999")
    assert account.status is None
    assert account.balances == []
    assert account.hold_limit is None
    assert account.hold_limit_ccy is None
    assert account.psp_bic is None
    assert account.servicer_name is None


def test_parse_camt004_debit_balance_is_negative():
    xml = SUCCESS.replace(b"<CdtDbtInd>CRDT</CdtDbtInd>\n              <Tp>\n                <Cd>CLBD</Cd>",
                          b"<CdtDbtInd>DBIT</CdtDbtInd>\n              <Tp>\n                <Cd>CLBD</Cd>")
    assert xml != SUCCESS

    assert parse_camt004(xml).account.closing_balance.amount == -1250.50


def test_parse_camt004_any_version():
    assert parse_camt004(SUCCESS.replace(b"camt.004.001.10", b"camt.004.001.08")).account.status == "ENABLED"


def test_parse_camt004_status_in_any_namespace():
    xml = SUCCESS.replace(b' xmlns="urn:desp:supplementary"', b"")

    assert parse_camt004(xml).account.status == "ENABLED"


def test_account_report_balance_lookup_by_type_code():
    account = parse_camt004((FIXTURES / "camt004_success_sample.xml").read_bytes()).account

    assert account.balance("AVLB").amount == 900.00
    assert account.balance("OPBD") is None
    assert account.closing_balance.type_code == "CLBD"
    assert account.closing_balance.amount == 1250.50


def test_account_report_remaining_holding_capacity():
    account = parse_camt004((FIXTURES / "camt004_success_sample.xml").read_bytes()).account

    # 5000.00 limit - 1250.50 closing booked, exact (no float rounding).
    assert account.remaining_holding_capacity == Decimal("3749.50")


def test_account_report_remaining_holding_capacity_needs_limit_and_closing_balance():
    account = parse_camt004((FIXTURES / "camt004_success_sample.xml").read_bytes()).account

    account.hold_limit = None
    assert account.remaining_holding_capacity is None

    account.hold_limit = 5000.00
    account.balances = [b for b in account.balances if b.type_code != "CLBD"]
    assert account.closing_balance is None
    assert account.remaining_holding_capacity is None



# ── Building ─────────────────────────────────────────────────────────────────

ERROR_FIXTURES = ["camt004_success_sample.xml", "camt004_error_sample.xml"]


@pytest.mark.parametrize("name", ERROR_FIXTURES)
def test_a_built_response_parses_back_to_the_same_and_is_valid(name):
    from camt import schema_errors
    from camt.camt004 import build_return_account_bytes

    response = parse_camt004((FIXTURES / name).read_bytes())
    options = {"error_account_id": "DEAN-IT-0001-ALPHA"} if response.account is None and response.error_code != "SYST" else {}

    built = build_return_account_bytes(response, **options)

    assert schema_errors(built) == []
    assert parse_camt004(built) == response


def test_an_unsolicited_alert_is_built_without_the_original_query():
    from camt.camt004 import build_return_account_bytes

    response = parse_camt004(SUCCESS)
    response.original_msg_id = None

    assert b"OrgnlBizQry" not in build_return_account_bytes(response)


def test_the_account_is_identified_by_its_iban_when_it_has_no_dean():
    from camt import schema_errors
    from camt.camt004 import build_return_account_bytes

    response = parse_camt004(SUCCESS)
    response.account.dean = None

    built = build_return_account_bytes(response)

    assert schema_errors(built) == []
    assert parse_camt004(built).account.iban == response.account.iban
