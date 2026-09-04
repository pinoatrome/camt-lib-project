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
