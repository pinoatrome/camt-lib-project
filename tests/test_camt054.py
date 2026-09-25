from pathlib import Path

import pytest

from camt.camt054 import DebitCreditNotification, parse_debit_credit_notification
from camt.exceptions import CamtParseError

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_debit_notification():
    xml = (FIXTURES / "camt054_debit_notification.xml").read_bytes()
    notif = parse_debit_credit_notification(xml)

    assert isinstance(notif, DebitCreditNotification)
    assert notif.message_id == "NOTIF-DBIT-0001"
    assert notif.account_iban is None
    assert notif.account_other_id == "IT60X0542811101000000DCA001"
    assert notif.is_debit is True
    assert notif.is_credit is False
    assert notif.entry.amount == 100
    assert notif.end_to_end_id == "E2E-PAY-0001"


def test_parse_credit_notification():
    xml = (FIXTURES / "camt054_credit_notification.xml").read_bytes()
    notif = parse_debit_credit_notification(xml)

    assert notif.message_id == "NOTIF-CRDT-0001"
    assert notif.account_other_id == "IT60X0542811101000000DCA002"
    assert notif.is_credit is True
    assert notif.is_debit is False
    assert notif.end_to_end_id == "E2E-PAY-0001"


def test_debit_and_credit_notification_share_the_payment_end_to_end_id():
    debit = parse_debit_credit_notification(
        (FIXTURES / "camt054_debit_notification.xml").read_bytes()
    )
    credit = parse_debit_credit_notification(
        (FIXTURES / "camt054_credit_notification.xml").read_bytes()
    )
    assert debit.end_to_end_id == credit.end_to_end_id


def test_end_to_end_id_is_none_without_transaction_details():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr>
      <MsgId>NOTIF-0002</MsgId>
      <CreDtTm>2026-09-04T10:00:00</CreDtTm>
    </GrpHdr>
    <Ntfctn>
      <Id>NTFY-0002</Id>
      <Acct>
        <Id><Othr><Id>DCA-002</Id></Othr></Id>
      </Acct>
      <Ntry>
        <Amt Ccy="EUR">10.00</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <Sts>BOOK</Sts>
      </Ntry>
    </Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>"""
    notif = parse_debit_credit_notification(xml)
    assert notif.end_to_end_id is None


def test_parse_debit_credit_notification_rejects_multiple_notifications():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr>
      <MsgId>NOTIF-0003</MsgId>
      <CreDtTm>2026-09-04T10:00:00</CreDtTm>
    </GrpHdr>
    <Ntfctn>
      <Id>NTFY-A</Id>
      <Ntry><Amt Ccy="EUR">10.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts></Ntry>
    </Ntfctn>
    <Ntfctn>
      <Id>NTFY-B</Id>
      <Ntry><Amt Ccy="EUR">20.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts></Ntry>
    </Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>"""
    with pytest.raises(CamtParseError, match="one <Ntfctn>"):
        parse_debit_credit_notification(xml)


def test_parse_debit_credit_notification_rejects_multiple_entries():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr>
      <MsgId>NOTIF-0004</MsgId>
      <CreDtTm>2026-09-04T10:00:00</CreDtTm>
    </GrpHdr>
    <Ntfctn>
      <Id>NTFY-0004</Id>
      <Ntry><Amt Ccy="EUR">10.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts></Ntry>
      <Ntry><Amt Ccy="EUR">20.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts>BOOK</Sts></Ntry>
    </Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>"""
    with pytest.raises(CamtParseError, match="one <Ntry>"):
        parse_debit_credit_notification(xml)
