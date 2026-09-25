import pytest

from camt import CamtParseError, merge_paginated_documents, parse_bytes, parse_file
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _camt053(bal_block: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr>
      <MsgId>MSG-0001</MsgId>
      <CreDtTm>2026-09-04T23:00:00</CreDtTm>
    </GrpHdr>
    <Stmt>
      <Id>STMT-0001</Id>
      <Acct>
        <Id><IBAN>IT60X0542811101000000123456</IBAN></Id>
      </Acct>
      {bal_block}
      <Ntry>
        <Amt Ccy="EUR">10.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>""".encode("utf-8")


_OPBD = """
      <Bal>
        <Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2026-09-04</Dt></Dt>
      </Bal>"""

_CLBD = """
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1010.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2026-09-04</Dt></Dt>
      </Bal>"""


def test_camt053_with_opening_and_closing_balance_parses():
    doc = parse_bytes(_camt053(_OPBD + _CLBD))
    stmt = doc.statements[0]
    assert stmt.opening_balance is not None
    assert stmt.closing_balance is not None


def test_camt053_missing_closing_balance_raises():
    with pytest.raises(CamtParseError, match="STMT-0001"):
        parse_bytes(_camt053(_OPBD))


def test_camt053_missing_opening_balance_raises():
    with pytest.raises(CamtParseError, match="STMT-0001"):
        parse_bytes(_camt053(_CLBD))


def test_camt053_missing_both_balances_raises():
    with pytest.raises(CamtParseError, match="mandatory"):
        parse_bytes(_camt053(""))


def test_camt052_without_opening_or_closing_balance_does_not_raise():
    # camt052_sample.xml only carries an ITBD balance, no OPBD/CLBD -- fine
    # for camt.052, where balance is optional.
    doc = parse_file(FIXTURES / "camt052_sample.xml")
    stmt = doc.statements[0]
    assert stmt.opening_balance is None
    assert stmt.closing_balance is None


def test_paginated_page_is_not_checked_individually():
    # page1 only has OPBD, page2 only has CLBD -- neither is a complete
    # camt.053 statement on its own, so parsing each page must not raise.
    parse_file(FIXTURES / "camt053_paginated_page1.xml")
    parse_file(FIXTURES / "camt053_paginated_page2.xml")


def test_merge_raises_when_merged_statement_still_lacks_a_balance():
    page1 = parse_bytes(_paginated(_OPBD, page_number=1, last_page=False))
    page2 = parse_bytes(_paginated("", page_number=2, last_page=True))

    with pytest.raises(CamtParseError, match="mandatory"):
        merge_paginated_documents([page1, page2])


def _paginated(bal_block: str, *, page_number: int, last_page: bool) -> bytes:
    last_page_text = "true" if last_page else "false"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr>
      <MsgId>MSG-0002</MsgId>
      <CreDtTm>2026-09-04T23:00:00</CreDtTm>
      <MsgPgntn>
        <PgNb>{page_number}</PgNb>
        <LastPgInd>{last_page_text}</LastPgInd>
      </MsgPgntn>
    </GrpHdr>
    <Stmt>
      <Id>STMT-0002</Id>
      <Acct>
        <Id><IBAN>IT60X0542811101000000123456</IBAN></Id>
      </Acct>
      {bal_block}
      <Ntry>
        <Amt Ccy="EUR">10.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>""".encode("utf-8")
