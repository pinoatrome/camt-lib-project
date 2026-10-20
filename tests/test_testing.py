"""The documents `camt.testing` makes: valid, and what the test asked for."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from camt import CreditDebit, MessageType, Party, parse_bytes, schema_errors
from camt.camt004 import parse_camt004
from camt.camt025 import parse_camt025
from camt.testing import (
    Payment,
    account_error_xml,
    account_report_xml,
    notification_xml,
    receipt_xml,
    statement_xml,
)

PAYER = Party(name="Payer", other_id="EU2700000000000009")


@pytest.mark.parametrize("make", [
    lambda: notification_xml(),
    lambda: notification_xml(Payment("45.50", CreditDebit.DEBIT, counterparty=Party(other_id="EU5400000000000008"))),
    lambda: notification_xml(Payment(counterparty=PAYER, remittance_info="Order 7", additional_info="Received", message_id="PSP-1")),
    lambda: notification_xml(account="IT60X0542811101000000123456"),
    lambda: statement_xml(),
    lambda: statement_xml([Payment(), Payment("5.00", CreditDebit.DEBIT, "E2E-2", "TX-2")], opening="1000.00", closing="1074.50"),
    lambda: statement_xml([Payment()], message_type=MessageType.CAMT_052, opening="1.00"),
    lambda: statement_xml([Payment()], page_number=1, last_page=False, opening="1000.00"),
    lambda: account_report_xml(),
    lambda: account_report_xml(iban="IT60X0542811101000000123456", status="BLOCKED", hold_limit=None),
    lambda: account_report_xml(original_message_id=None, account_scheme=None),
    lambda: account_error_xml(),
    lambda: account_error_xml(code="AC01", description="Closed"),
    lambda: receipt_xml(original_message_id="PSPLT-1"),
    lambda: receipt_xml(original_message_id="PSPLT-1", status="PDNG"),
    lambda: receipt_xml(original_message_id="PSPLT-1", status="RJCT", reject_desc="No funds"),
])
def test_every_sample_is_valid_against_the_schema(make):
    assert schema_errors(make()) == []


def test_a_notification_is_what_was_asked():
    document = parse_bytes(notification_xml(
        Payment("120.00", CreditDebit.CREDIT, "E2E-1", "TX-1", PAYER, "Order 7"), account="EU4900000000000001",
        message_id="NTF-9", created=datetime(2026, 10, 6, 10, 12, 31)))
    [statement] = document.statements
    [entry] = statement.entries
    [details] = entry.transaction_details
    assert (document.message_type, document.message_id, statement.account_other_id) == (
        MessageType.CAMT_054, "NTF-9", "EU4900000000000001")
    assert (entry.amount, entry.credit_debit, entry.account_servicer_ref) == (Decimal("120.00"), CreditDebit.CREDIT, "TX-1")
    assert (details.end_to_end_id, details.debtor, details.remittance_info) == ("E2E-1", PAYER, "Order 7")


def test_a_debit_names_its_counterparty_as_creditor():
    [details] = parse_bytes(notification_xml(Payment(credit_debit=CreditDebit.DEBIT, counterparty=PAYER))
                            ).statements[0].entries[0].transaction_details
    assert details.creditor == PAYER and details.debtor is None


def test_a_statement_has_its_balances_entries_and_pages():
    document = parse_bytes(statement_xml(
        [Payment(), Payment("45.50", CreditDebit.DEBIT, "E2E-2", "TX-2")], opening="1000.00", closing="1074.50",
        page_number=2, last_page=True))
    [statement] = document.statements
    assert (document.page_number, document.last_page) == (2, True)
    assert (statement.opening_balance.amount, statement.closing_balance.amount) == (Decimal("1000.00"), Decimal("1074.50"))
    assert [entry.amount for entry in statement.entries] == [Decimal("120.00"), Decimal("45.50")]


def test_an_iban_account_is_written_as_an_iban():
    [statement] = parse_bytes(statement_xml(account="IT60X0542811101000000123456")).statements
    assert (statement.account_iban, statement.account_other_id) == ("IT60X0542811101000000123456", None)


def test_an_account_report_is_what_was_asked():
    response = parse_camt004(account_report_xml(
        "EU2200000000000002", iban="IT60X0542811101000000123456", status="SUSPENDED", balance="10.50",
        hold_limit="3000.00", original_message_id="PSPQRY-9", message_id="RESP-9"))
    account = response.account
    assert (response.response_msg_id, response.original_msg_id) == ("RESP-9", "PSPQRY-9")
    assert (account.dean, account.iban, account.status) == ("EU2200000000000002", "IT60X0542811101000000123456", "SUSPENDED")
    assert (account.closing_balance.amount, account.hold_limit) == (10.5, 3000.0)


def test_an_alert_has_no_original_query():
    assert parse_camt004(account_report_xml(original_message_id=None)).original_msg_id is None


def test_an_account_error_carries_its_code():
    response = parse_camt004(account_error_xml("EU1500000000777777", code="NFND"))
    assert response.account is None and response.error_code == "NFND" and "EU1500000000777777" in response.error_description


def test_a_receipt_is_what_was_asked():
    settled = parse_camt025(receipt_xml(original_message_id="PSPLT-1"))
    rejected = parse_camt025(receipt_xml(original_message_id="PSPLT-1", status="RJCT", reject_desc="No funds"))
    assert (settled.status, settled.original_msg_id) == ("STLD", "PSPLT-1")
    assert (rejected.status, rejected.reject_code, rejected.reject_desc) == ("RJCT", "AM04", "No funds")


def test_an_entry_can_have_no_transaction_details():
    [entry] = parse_bytes(statement_xml([Payment(with_details=False, bank_transaction_code="PMNT-ICDT-ESCT")])).statements[0].entries
    assert entry.transaction_details == [] and entry.bank_transaction_code == "PMNT-ICDT-ESCT"


def test_a_statement_covers_its_date_and_a_notification_has_no_period():
    statement = parse_bytes(statement_xml(created=datetime(2026, 1, 5, 8, 0), statement_date=date(2026, 1, 4))).statements[0]
    assert (statement.from_date, statement.to_date) == (date(2026, 1, 4), date(2026, 1, 4))
    notification = parse_bytes(notification_xml()).statements[0]
    assert (notification.from_date, notification.to_date) == (None, None)
