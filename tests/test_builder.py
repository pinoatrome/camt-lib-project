import re
from datetime import date, datetime
from decimal import Decimal

import pytest
from lxml import etree

from camt import (
    Balance,
    CamtError,
    CreditDebit,
    Document,
    Entry,
    EntryStatus,
    MessageType,
    Party,
    ReturnInfo,
    Statement,
    TransactionDetails,
    build_bytes,
    parse_bytes,
)


def _sample_document() -> Document:
    return Document(
        message_type=MessageType.CAMT_053,
        message_id="MSG-BUILD-1",
        creation_datetime=datetime(2026, 1, 5, 8, 0, 0),
        statements=[
            Statement(
                id="STMT-BUILD-1",
                creation_datetime=datetime(2026, 1, 5, 8, 0, 0),
                from_date=date(2026, 1, 4),
                to_date=date(2026, 1, 4),
                account_iban="IT60X0542811101000000123456",
                account_currency="EUR",
                account_owner=Party(name="Acme S.r.l.", bic="ACMEITMMXXX"),
                servicer_bic="BPMOIT22XXX",
                balances=[
                    Balance(
                        code="OPBD",
                        amount=Decimal("1000.00"),
                        currency="EUR",
                        credit_debit=CreditDebit.CREDIT,
                        date=date(2026, 1, 4),
                    ),
                    Balance(
                        code="CLBD",
                        amount=Decimal("1250.50"),
                        currency="EUR",
                        credit_debit=CreditDebit.CREDIT,
                        date=date(2026, 1, 4),
                    ),
                ],
                entries=[
                    Entry(
                        amount=Decimal("300.50"),
                        currency="EUR",
                        credit_debit=CreditDebit.CREDIT,
                        status=EntryStatus.BOOKED,
                        booking_date=date(2026, 1, 4),
                        value_date=date(2026, 1, 4),
                        account_servicer_ref="SVCR-REF-1",
                        additional_info="Invoice payment",
                        transaction_details=[
                            TransactionDetails(
                                amount=Decimal("300.50"),
                                currency="EUR",
                                credit_debit=CreditDebit.CREDIT,
                                end_to_end_id="E2E-1",
                                remittance_info="Invoice 2026-042",
                                debtor=Party(name="Widget Buyer Ltd", iban="GB29NWBK60161331926819", bic="NWBKGB2LXXX"),
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_build_produces_well_formed_xml_with_expected_namespace():
    xml_bytes = build_bytes(_sample_document())
    assert b"urn:iso:std:iso:20022:tech:xsd:camt.053.001.14" in xml_bytes
    assert b"<MsgId>MSG-BUILD-1</MsgId>" in xml_bytes


def test_round_trip_parse_build_parse():
    original = _sample_document()
    xml_bytes = build_bytes(original)
    reparsed = parse_bytes(xml_bytes)

    assert reparsed.message_type == original.message_type
    assert reparsed.message_id == original.message_id
    assert len(reparsed.statements) == 1

    stmt = reparsed.statements[0]
    orig_stmt = original.statements[0]
    assert stmt.id == orig_stmt.id
    assert stmt.account_iban == orig_stmt.account_iban
    assert (stmt.from_date, stmt.to_date) == (orig_stmt.from_date, orig_stmt.to_date)
    assert stmt.opening_balance.amount == orig_stmt.opening_balance.amount
    assert stmt.closing_balance.amount == orig_stmt.closing_balance.amount

    entry = stmt.entries[0]
    orig_entry = orig_stmt.entries[0]
    assert entry.amount == orig_entry.amount
    assert entry.credit_debit == orig_entry.credit_debit
    assert entry.transaction_details[0].end_to_end_id == "E2E-1"
    assert entry.transaction_details[0].debtor.name == "Widget Buyer Ltd"
    assert entry.transaction_details[0].debtor.bic == "NWBKGB2LXXX"
    assert stmt.account_owner == orig_stmt.account_owner


def test_party_bic_is_built_in_its_newer_form():
    xml_bytes = build_bytes(_sample_document())

    assert b"<AnyBIC>ACMEITMMXXX</AnyBIC>" in xml_bytes
    assert b"BICOrBEI" not in xml_bytes


def test_related_parties_are_built_in_pty():
    root = etree.fromstring(build_bytes(_sample_document()))
    ns = {"n": root.nsmap[None]}

    assert root.xpath("//n:TxDtls/n:RltdPties/n:Dbtr/n:Pty/n:Nm/text()", namespaces=ns) == ["Widget Buyer Ltd"]
    assert root.xpath("//n:TxDtls/n:RltdPties/n:DbtrAcct/n:Id/n:IBAN/text()", namespaces=ns) == ["GB29NWBK60161331926819"]


def _with_return_info(return_info: ReturnInfo) -> Document:
    document = _sample_document()
    document.statements[0].entries[0].transaction_details[0].return_info = return_info
    return document


def test_return_info_round_trips():
    reparsed = parse_bytes(build_bytes(_with_return_info(ReturnInfo(reason_code="AC04", additional_info="Closed"))))

    tx = reparsed.statements[0].entries[0].transaction_details[0]
    assert tx.is_return is True
    assert tx.return_info == ReturnInfo(reason_code="AC04", additional_info="Closed")


def test_a_proprietary_return_reason_round_trips():
    xml_bytes = build_bytes(_with_return_info(ReturnInfo(reason_proprietary="DESP-TIMEOUT")))

    assert b"<Prtry>DESP-TIMEOUT</Prtry>" in xml_bytes
    tx = parse_bytes(xml_bytes).statements[0].entries[0].transaction_details[0]
    assert tx.return_info == ReturnInfo(reason_proprietary="DESP-TIMEOUT")


def test_a_payment_without_return_info_writes_none():
    assert b"RtrInf" not in build_bytes(_sample_document())


def test_the_original_message_id_round_trips_in_refs_order():
    document = _sample_document()
    tx = document.statements[0].entries[0].transaction_details[0]
    tx.message_id = "PSPPAY-0001"
    tx.account_servicer_ref = "REF-1"
    xml_bytes = build_bytes(document)

    reparsed = parse_bytes(xml_bytes).statements[0].entries[0].transaction_details[0]
    assert (reparsed.message_id, reparsed.account_servicer_ref) == ("PSPPAY-0001", "REF-1")
    refs = xml_bytes[xml_bytes.index(b"<Refs>"):xml_bytes.index(b"</Refs>")]
    order = [tag for tag in (b"<MsgId>", b"<AcctSvcrRef>", b"<InstrId>", b"<EndToEndId>") if tag in refs]
    assert order == sorted(order, key=refs.index)
    assert order[:2] == [b"<MsgId>", b"<AcctSvcrRef>"]


def _entry_xml(document: Document) -> etree._Element:
    root = etree.fromstring(build_bytes(document, pretty_print=False))
    return root.xpath("//n:Ntry", namespaces={"n": root.nsmap[None]})[0]


@pytest.mark.parametrize("code, built", [
    ("PMNT-RCDT-ESCT", "<BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>RCDT</Cd><SubFmlyCd>ESCT</SubFmlyCd></Fmly></Domn></BkTxCd>"),
    ("PROP-CODE-1", "<BkTxCd><Prtry><Cd>PROP-CODE-1</Cd></Prtry></BkTxCd>"),
    (None, "<BkTxCd/>"),
])
def test_bank_transaction_code_round_trips(code, built):
    document = _sample_document()
    document.statements[0].entries[0].bank_transaction_code = code

    bk_tx_cd = _entry_xml(document).find("{*}BkTxCd")
    assert re.sub(r' xmlns="[^"]*"', "", etree.tostring(bk_tx_cd).decode()) == built
    assert parse_bytes(build_bytes(document)).statements[0].entries[0].bank_transaction_code == code


def test_entry_status_is_a_code():
    assert _entry_xml(_sample_document()).findtext("{*}Sts/{*}Cd") == "BOOK"


def test_pagination_round_trips():
    document = _sample_document()
    document.page_number, document.last_page = 2, False

    reparsed = parse_bytes(build_bytes(document))

    assert (reparsed.page_number, reparsed.last_page) == (2, False)


@pytest.mark.parametrize("page_number, last_page", [(1, None), (None, True)])
def test_pagination_takes_both_values(page_number, last_page):
    document = _sample_document()
    document.page_number, document.last_page = page_number, last_page

    with pytest.raises(CamtError, match="MsgPgntn takes both"):
        build_bytes(document)


def test_statement_period_takes_both_dates():
    document = _sample_document()
    document.statements[0].to_date = None

    with pytest.raises(CamtError, match="FrToDt takes both"):
        build_bytes(document)


def test_a_notification_has_no_balances():
    document = _sample_document()
    document.message_type = MessageType.CAMT_054

    with pytest.raises(CamtError, match="a camt.054 carries no balances"):
        build_bytes(document)
