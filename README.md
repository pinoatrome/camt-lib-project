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
| camt.005 | GetTransaction | outbound request | `camt.camt005.build_get_transaction_request_bytes()` |
| camt.006 | ReturnTransaction | inbound response | `camt.camt006.parse_camt006()` |
| camt.018 | GetBusinessDayInformation | outbound request | `camt.camt018.build_get_business_day_request_bytes()` |
| camt.019 | ReturnBusinessDayInformation | inbound response | `camt.camt019.parse_camt019()` |
| camt.025 | Receipt | inbound response | `camt.camt025.parse_camt025()` |
| camt.046 | GetReservation | outbound request | `camt.camt046.build_get_reservation_request_bytes()` |
| camt.047 | ReturnReservation | inbound response | `camt.camt047.parse_camt047()` |
| camt.048 | ModifyReservation | outbound request | `camt.camt048.build_modify_reservation_request_bytes()` |
| camt.049 | DeleteReservation | outbound request | `camt.camt049.build_delete_reservation_request_bytes()` |
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
  bookkeeping and account reconciliation. Large statements (and camt.052
  reports) may be split by the sender across pages (`GrpHdr/MsgPgntn`), which
  `merge_paginated_documents()` recombines into one `Document` — matching
  statements across pages by id, filling in whichever header fields (account
  id, currency, owner, ...) a sparser page left out, and raising a clear
  `CamtParseError` if two pages disagree on a header field or a balance for
  what's meant to be the same statement, or if the page sequence has a gap or
  a duplicate page number. `LastPgInd` may be omitted (instead of sent as
  explicit `false`) on every page but the last.
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

### Transaction query pair (camt.005 / camt.006)

- **camt.005 — GetTransaction.** An outbound request asking the bank for one
  account's transactions, filtered by booking-date window and/or status. Used
  when transaction-level detail is needed on demand, instead of waiting for
  the next camt.052/053/054 report.

  camt.005 also supports the ISO 20022 **delta query pattern**, for polling an
  account without re-fetching and re-diffing the full result set each time:
  the first request names its search criteria (`new_query_name`, built with
  `build_get_transaction_request_*`); every later poll then sends a *delta*
  follow-up (`build_get_transaction_delta_request_*`) that references that
  name alone, asking for only what changed since the named query was last
  answered.
- **camt.006 — ReturnTransaction.** The response to camt.005. For an initial,
  non-delta request, the transactions are reported as a single set. For a
  delta follow-up, `parse_camt006()` splits them into a `DeltaTransactionSet`
  of three groups — `new`, `modified` (e.g. a status change) and `cancelled`
  — since the named query was last answered, and it also carries the query's
  name back (`query_name`) so it can be fed straight into the next delta
  follow-up.

### Business day query pair (camt.018 / camt.019)

- **camt.018 — GetBusinessDayInformation.** An outbound request asking a
  settlement system (e.g. TARGET2/T2, CLM, TIPS) for the status of one
  business day, optionally for a specific date (defaulting to the current
  business day otherwise). Used to check whether the system is open and what
  its cut-off schedule is before submitting a payment or liquidity
  instruction.
- **camt.019 — ReturnBusinessDayInformation.** The response to camt.018,
  carrying the system's status (`OPEN` / `CLOSED` / `CHANGEOVER`) for that
  date plus its ordered list of scheduled events (start of day, cut-off
  times, end of day). `BusinessDayInfo.event_time()` looks up one event's
  timestamp by code (e.g. `"CUT-OFF-CUST"`).

### Reservation management (camt.046 / 047 / 048 / 049)

A reservation is an amount an account holds aside against a specific purpose
(e.g. a minimum reserve requirement, a standing facility) rather than the
account's overall balance, which camt.003/004 report on instead.

- **camt.046 — GetReservation.** An outbound request asking for an account's
  current reservations, optionally filtered to one reservation type code
  (e.g. `"MMR"`). Used to check how much of an account's balance is earmarked
  and unavailable for ordinary payments.
- **camt.047 — ReturnReservation.** The response to camt.046, listing each
  matching reservation's type, amount/currency, status (`ACTV` / `CLSD`) and,
  where applicable, its validity window (`from_date`/`to_date`).
- **camt.048 — ModifyReservation.** An outbound instruction changing the
  amount of one existing reservation, identified by account and reservation
  type. Like camt.050 below, its synchronous response is a camt.025 Receipt
  rather than a dedicated Return message.
- **camt.049 — DeleteReservation.** An outbound instruction removing one
  existing reservation entirely, identified the same way as camt.048 but
  with no amount to carry; also answered with a camt.025 Receipt.

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
