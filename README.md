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
