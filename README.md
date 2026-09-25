# camt-lib-project

Parse and generate ISO 20022 CAMT bank-statement XML (camt.052 Account Report,
camt.053 Bank-to-Customer Statement, camt.054 Debit/Credit Notification) as
typed Python objects.

Parsing matches elements by local name only, so a single code path handles
different schema versions of the same message family (e.g. camt.053.001.02 vs
.001.08) without per-version branches. XML generation targets the `.001.02`
variant of each family.

## Install

From the Django project's virtualenv, in editable mode:

```bash
pip install -e .
```

## Usage

```python
from camt import parse_file

document = parse_file("statement.xml")

for statement in document.statements:
    print(statement.id, statement.account_iban, statement.account_currency)
    print("opening:", statement.opening_balance.amount)
    print("closing:", statement.closing_balance.amount)
    for entry in statement.entries:
        print(entry.credit_debit, entry.amount, entry.additional_info)
```

Generating XML from Python objects:

```python
from datetime import date
from decimal import Decimal
from camt import Document, MessageType, Statement, Balance, CreditDebit, build_bytes

doc = Document(
    message_type=MessageType.CAMT_053,
    message_id="MSG-0001",
    statements=[
        Statement(
            id="STMT-0001",
            account_iban="IT60X0542811101000000123456",
            account_currency="EUR",
            balances=[
                Balance(code="OPBD", amount=Decimal("1000.00"), currency="EUR",
                        credit_debit=CreditDebit.CREDIT, date=date.today()),
            ],
        )
    ],
)
xml_bytes = build_bytes(doc)
```

## CAMT messages

CAMT ("Cash Management") is the ISO 20022 message set banks and PSPs use to
report on accounts and to move liquidity between them. Each message family has
a number (`camt.NNN`) and a schema variant (`.001.02`, `.001.08`, …). This
library covers the families below; everything else in the CAMT set is out of
scope.

| Message | Name | Direction | Handled by |
| --- | --- | --- | --- |
| camt.003 | GetAccount | outbound request | `camt.camt003.build_get_account_request_bytes()` |
| camt.004 | ReturnAccount | inbound response / alert | `camt.camt004.parse_camt004()` |
| camt.025 | Receipt | inbound response | `camt.camt025.parse_camt025()` |
| camt.050 | LiquidityCreditTransfer | outbound request | `camt.camt050.build_liquidity_transfer_bytes()` |
| camt.052 | Bank-to-Customer Account Report | inbound report | `parse_file()` / `build_bytes()` |
| camt.053 | Bank-to-Customer Statement | inbound report | `parse_file()` / `build_bytes()` |
| camt.054 | Bank-to-Customer Debit/Credit Notification | inbound report | `parse_file()` / `build_bytes()`, plus `camt.camt054` |

### Report messages (camt.052 / 053 / 054)

These three share one shape — a group header, then one or more
statement/report/notification blocks, each with an account, balances and
entries — so the generic `parse_*`/`build_*` functions and the `Document`,
`Statement`, `Balance`, `Entry` models handle all of them, with
`MessageType` selecting the family.

- **camt.052 — Account Report.** Intraday, provisional view of an account:
  movements booked so far today plus interim balances. Used for same-day cash
  positioning and early visibility on incoming funds; not authoritative, since
  figures can still change before end of day.
- **camt.053 — Bank-to-Customer Statement.** The definitive end-of-day (or
  end-of-period) statement: booked entries only, with mandatory opening
  (`OPBD`) and closing (`CLBD`) balances. This is the message to use for
  bookkeeping and account reconciliation. Large statements may be split across
  pages, which `merge_paginated_documents()` recombines into one `Document`.
- **camt.054 — Debit/Credit Notification.** A push notification that a single
  debit or credit happened, sent as it happens rather than on a schedule. Used
  to react to individual payments without polling. In the settled-payment flow
  each payment yields two notifications (a debit to the payer's PSP, a credit
  to the beneficiary's PSP), each with exactly one entry;
  `camt.camt054.parse_debit_credit_notification()` gives that single-entry view
  and exposes the entry's `EndToEndId` for matching back to the originating
  pacs.008 payment.

### Account query pair (camt.003 / camt.004)

- **camt.003 — GetAccount.** An outbound request asking the bank for the
  current state of one account, identified by IBAN or by a proprietary id
  (e.g. a DEAN). Used when the current balance or status is needed on demand,
  instead of waiting for the next report.
- **camt.004 — ReturnAccount.** The response to camt.003, carrying the
  account's identifiers, currency, status (`ENABLED` / `BLOCKED` /
  `SUSPENDED`), servicer details and balances. The same message also arrives
  unsolicited as an account alert (for example on a status change), so it is
  parsed the same way whether or not a camt.003 was sent.

### Liquidity transfer pair (camt.050 / camt.025)

- **camt.050 — LiquidityCreditTransfer.** An outbound instruction to move
  funds between two accounts held in the same system — for example funding a
  dedicated cash account from a main cash account. Used for liquidity
  management, not for customer payments.
- **camt.025 — Receipt.** The synchronous answer to a camt.050, reporting the
  outcome as settled (`STLD`), pending (`PDNG`) or rejected (`RJCT`), with the
  reject code and description when applicable, plus the original message and
  end-to-end ids so the receipt can be tied to its request.

## Scope

This library covers the fields commonly needed for bank-statement ingestion
and reconciliation (account identification, balances, entries, and entry
transaction details/remittance info). It does not implement the full CAMT XSD
(e.g. batched entry summaries, charges records, tax details).

## Tests

```bash
pip install -e .[test]
pytest tests
```
