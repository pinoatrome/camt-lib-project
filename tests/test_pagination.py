from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from camt import (
    Balance,
    CamtParseError,
    CreditDebit,
    Document,
    Entry,
    EntryStatus,
    MessageType,
    Statement,
    merge_paginated_documents,
    parse_file,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_file_reads_pagination_metadata():
    page1 = parse_file(FIXTURES / "camt053_paginated_page1.xml")
    page2 = parse_file(FIXTURES / "camt053_paginated_page2.xml")

    assert page1.page_number == 1
    assert page1.last_page is False
    assert page2.page_number == 2
    assert page2.last_page is True


def test_parse_file_leaves_pagination_none_for_non_paginated_document():
    doc = parse_file(FIXTURES / "camt053_sample.xml")
    assert doc.page_number is None
    assert doc.last_page is None


def test_merge_paginated_documents_concatenates_entries_and_balances():
    page1 = parse_file(FIXTURES / "camt053_paginated_page1.xml")
    page2 = parse_file(FIXTURES / "camt053_paginated_page2.xml")

    merged = merge_paginated_documents([page1, page2])

    assert merged.page_number is None
    assert merged.last_page is None
    assert merged.message_type is MessageType.CAMT_053
    assert len(merged.statements) == 1

    stmt = merged.statements[0]
    assert stmt.id == "STMT-EOD-0001"
    assert [e.amount for e in stmt.entries] == [
        Decimal("100.00"),
        Decimal("50.00"),
        Decimal("25.00"),
    ]
    assert stmt.opening_balance.amount == Decimal("1000.00")
    assert stmt.closing_balance.amount == Decimal("1050.00")


def test_merge_paginated_documents_accepts_pages_out_of_order():
    page1 = parse_file(FIXTURES / "camt053_paginated_page1.xml")
    page2 = parse_file(FIXTURES / "camt053_paginated_page2.xml")

    merged = merge_paginated_documents([page2, page1])

    assert [e.amount for e in merged.statements[0].entries] == [
        Decimal("100.00"),
        Decimal("50.00"),
        Decimal("25.00"),
    ]


def _entry(amount: str) -> Entry:
    return Entry(
        amount=Decimal(amount),
        currency="EUR",
        credit_debit=CreditDebit.CREDIT,
        status=EntryStatus.BOOKED,
    )


def _page(msg_type: MessageType, page_number: int | None, last_page: bool | None) -> Document:
    return Document(
        message_type=msg_type,
        message_id="MSG-1",
        statements=[Statement(id="STMT-1", entries=[_entry("1.00")])],
        page_number=page_number,
        last_page=last_page,
    )


def test_merge_paginated_documents_rejects_empty_list():
    with pytest.raises(CamtParseError, match="No documents to merge"):
        merge_paginated_documents([])


def test_merge_paginated_documents_rejects_mixed_message_types():
    pages = [
        _page(MessageType.CAMT_053, 1, False),
        _page(MessageType.CAMT_052, 2, True),
    ]
    with pytest.raises(CamtParseError, match="different message types"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_rejects_missing_page_number():
    pages = [
        _page(MessageType.CAMT_053, 1, False),
        _page(MessageType.CAMT_053, None, True),
    ]
    with pytest.raises(CamtParseError, match="page number"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_rejects_non_contiguous_pages():
    pages = [
        _page(MessageType.CAMT_053, 1, False),
        _page(MessageType.CAMT_053, 3, True),
    ]
    with pytest.raises(CamtParseError, match="contiguous"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_rejects_missing_last_page_flag():
    pages = [
        _page(MessageType.CAMT_053, 1, False),
        _page(MessageType.CAMT_053, 2, False),
    ]
    with pytest.raises(CamtParseError, match="LastPgInd"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_rejects_multiple_last_page_flags():
    pages = [
        _page(MessageType.CAMT_053, 1, True),
        _page(MessageType.CAMT_053, 2, True),
    ]
    with pytest.raises(CamtParseError, match="LastPgInd"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_rejects_duplicate_page_numbers():
    pages = [
        _page(MessageType.CAMT_053, 1, False),
        _page(MessageType.CAMT_053, 2, False),
        _page(MessageType.CAMT_053, 2, True),
    ]
    with pytest.raises(CamtParseError, match="Duplicate page number"):
        merge_paginated_documents(pages)


def test_merge_paginated_documents_accepts_a_single_page_delivery():
    # A delivery small enough to fit on one page still carries MsgPgntn
    # (PgNb=1, LastPgInd=true) -- merging a list of exactly one such page
    # should just hand back that page's statement.
    merged = merge_paginated_documents([_page(MessageType.CAMT_052, 1, True)])

    assert merged.page_number is None
    assert len(merged.statements) == 1
    assert merged.statements[0].id == "STMT-1"


def test_parse_file_treats_omitted_last_pg_ind_as_not_the_last_page():
    # Some senders omit <LastPgInd> entirely on non-final pages instead of
    # sending it as explicit "false".
    page1 = parse_file(FIXTURES / "camt053_paginated_page1_no_last_pg_ind.xml")
    assert page1.last_page is None

    page2 = parse_file(FIXTURES / "camt053_paginated_page2_no_last_pg_ind.xml")
    merged = merge_paginated_documents([page1, page2])

    assert merged.statements[0].id == "STMT-EOD-0002"
    assert merged.statements[0].opening_balance.amount == Decimal("200.00")
    assert merged.statements[0].closing_balance.amount == Decimal("210.00")


def test_merge_paginated_documents_backfills_missing_statement_metadata():
    # Page 1 carries the full account block; page 2 (for the same statement)
    # only repeats the bare minimum. The merge should keep page 1's details
    # rather than losing them.
    full = Statement(
        id="STMT-1",
        account_iban="IT60X0542811101000000123456",
        account_currency="EUR",
        servicer_bic="PSPXITMMXXX",
        entries=[_entry("1.00")],
    )
    sparse = Statement(id="STMT-1", entries=[_entry("2.00")])

    # camt.052 (no mandatory OPBD/CLBD) keeps this test focused on metadata
    # backfill rather than also having to satisfy the camt.053 balance mandate.
    page1 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[full],
        page_number=1,
        last_page=False,
    )
    page2 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[sparse],
        page_number=2,
        last_page=True,
    )

    merged = merge_paginated_documents([page1, page2])
    stmt = merged.statements[0]
    assert stmt.account_iban == "IT60X0542811101000000123456"
    assert stmt.account_currency == "EUR"
    assert stmt.servicer_bic == "PSPXITMMXXX"
    assert [e.amount for e in stmt.entries] == [Decimal("1.00"), Decimal("2.00")]


def test_merge_paginated_documents_rejects_conflicting_account_iban_across_pages():
    page1 = _page(MessageType.CAMT_053, 1, False)
    page1.statements[0].account_iban = "IT60X0542811101000000111111"
    page2 = _page(MessageType.CAMT_053, 2, True)
    page2.statements[0].account_iban = "IT60X0542811101000000222222"

    with pytest.raises(CamtParseError, match="conflicting account_iban"):
        merge_paginated_documents([page1, page2])


def test_merge_paginated_documents_tolerates_identical_duplicate_balance():
    opbd = Balance(
        code="OPBD",
        amount=Decimal("1000.00"),
        currency="EUR",
        credit_debit=CreditDebit.CREDIT,
        date=date(2026, 9, 4),
    )
    page1 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[Statement(id="STMT-1", balances=[opbd], entries=[_entry("1.00")])],
        page_number=1,
        last_page=False,
    )
    # Some senders redundantly repeat OPBD, identically, on every page.
    page2 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[Statement(id="STMT-1", balances=[opbd], entries=[_entry("2.00")])],
        page_number=2,
        last_page=True,
    )

    merged = merge_paginated_documents([page1, page2])
    stmt = merged.statements[0]
    assert stmt.balances == [opbd]
    assert [e.amount for e in stmt.entries] == [Decimal("1.00"), Decimal("2.00")]


def test_merge_paginated_documents_rejects_conflicting_balance_across_pages():
    page1 = Document(
        message_type=MessageType.CAMT_053,
        message_id="MSG-1",
        statements=[
            Statement(
                id="STMT-1",
                balances=[
                    Balance(
                        code="OPBD",
                        amount=Decimal("1000.00"),
                        currency="EUR",
                        credit_debit=CreditDebit.CREDIT,
                        date=date(2026, 9, 4),
                    )
                ],
                entries=[_entry("1.00")],
            )
        ],
        page_number=1,
        last_page=False,
    )
    page2 = Document(
        message_type=MessageType.CAMT_053,
        message_id="MSG-1",
        statements=[
            Statement(
                id="STMT-1",
                balances=[
                    Balance(
                        code="OPBD",
                        amount=Decimal("999.00"),  # disagrees with page1
                        currency="EUR",
                        credit_debit=CreditDebit.CREDIT,
                        date=date(2026, 9, 4),
                    )
                ],
                entries=[_entry("2.00")],
            )
        ],
        page_number=2,
        last_page=True,
    )

    with pytest.raises(CamtParseError, match="conflicting 'OPBD' balance"):
        merge_paginated_documents([page1, page2])


def test_merge_paginated_documents_works_for_camt052_reports():
    # camt.052 has no mandatory opening/closing balance, but pagination and
    # merging still apply the same way as camt.053.
    pages = [
        _page(MessageType.CAMT_052, 1, False),
        _page(MessageType.CAMT_052, 2, True),
    ]
    merged = merge_paginated_documents(pages)

    assert merged.message_type is MessageType.CAMT_052
    assert len(merged.statements[0].entries) == 2


def test_merge_paginated_documents_includes_a_statement_introduced_on_a_later_page():
    page1 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[Statement(id="STMT-A", entries=[_entry("1.00")])],
        page_number=1,
        last_page=False,
    )
    page2 = Document(
        message_type=MessageType.CAMT_052,
        message_id="MSG-1",
        statements=[
            Statement(id="STMT-A", entries=[_entry("2.00")]),
            Statement(id="STMT-B", entries=[_entry("3.00")]),  # new on page 2
        ],
        page_number=2,
        last_page=True,
    )

    merged = merge_paginated_documents([page1, page2])
    assert [s.id for s in merged.statements] == ["STMT-A", "STMT-B"]
    assert [e.amount for e in merged.statements[1].entries] == [Decimal("3.00")]
