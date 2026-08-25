from datetime import date, datetime
from decimal import Decimal

from camt import (
    Balance,
    CreditDebit,
    Document,
    Entry,
    EntryStatus,
    MessageType,
    Party,
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
                account_owner=Party(name="Acme S.r.l."),
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
                                debtor=Party(name="Widget Buyer Ltd", iban="GB29NWBK60161331926819"),
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_build_produces_well_formed_xml_with_expected_namespace():
    xml_bytes = build_bytes(_sample_document())
    assert b"urn:iso:std:iso:20022:tech:xsd:camt.053.001.02" in xml_bytes
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
    assert stmt.opening_balance.amount == orig_stmt.opening_balance.amount
    assert stmt.closing_balance.amount == orig_stmt.closing_balance.amount

    entry = stmt.entries[0]
    orig_entry = orig_stmt.entries[0]
    assert entry.amount == orig_entry.amount
    assert entry.credit_debit == orig_entry.credit_debit
    assert entry.transaction_details[0].end_to_end_id == "E2E-1"
    assert entry.transaction_details[0].debtor.name == "Widget Buyer Ltd"
