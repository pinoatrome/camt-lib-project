"""Parse ISO 20022 CAMT (camt.052 / camt.053 / camt.054) XML into `camt.models` objects.

Element lookups match on local element name only (ignoring the namespace URI), so a
single code path handles the various schema versions (e.g. camt.053.001.02 vs .08)
without needing one branch per version.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import IO

from lxml import etree

from .enums import CreditDebit, EntryStatus, MessageType
from .exceptions import CamtParseError, UnsupportedMessageType
from .models import Balance, Document, Entry, Party, Statement, TransactionDetails


def _local(tag: str) -> str:
    return etree.QName(tag).localname


def _child(elem: etree._Element | None, name: str) -> etree._Element | None:
    if elem is None:
        return None
    for c in elem:
        if _local(c.tag) == name:
            return c
    return None


def _children(elem: etree._Element | None, name: str) -> list[etree._Element]:
    if elem is None:
        return []
    return [c for c in elem if _local(c.tag) == name]


def _path(elem: etree._Element | None, *names: str) -> etree._Element | None:
    cur = elem
    for name in names:
        cur = _child(cur, name)
        if cur is None:
            return None
    return cur


def _text(elem: etree._Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    value = elem.text.strip()
    return value or None


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise CamtParseError(f"Invalid decimal amount: {value!r}") from exc


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise CamtParseError(f"Invalid date: {value!r}") from exc


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise CamtParseError(f"Invalid datetime: {value!r}") from exc


def _parse_date_or_datetime(elem: etree._Element | None) -> date | datetime | None:
    """Handle <Dt><Dt>..</Dt></Dt> and <Dt><DtTm>..</DtTm></Dt> shapes."""
    if elem is None:
        return None
    dt_text = _text(_child(elem, "DtTm"))
    if dt_text is not None:
        return _parse_datetime(dt_text)
    d_text = _text(_child(elem, "Dt"))
    if d_text is not None:
        return _parse_date(d_text)
    return None


def _as_date(value: date | datetime | None) -> date | None:
    return value.date() if isinstance(value, datetime) else value


def _parse_amount(elem: etree._Element | None) -> tuple[Decimal | None, str | None]:
    amt_elem = _child(elem, "Amt")
    if amt_elem is None:
        return None, None
    return _decimal(_text(amt_elem)), amt_elem.get("Ccy")


def _parse_credit_debit(elem: etree._Element | None) -> CreditDebit | None:
    text = _text(_child(elem, "CdtDbtInd"))
    if text is None:
        return None
    try:
        return CreditDebit(text)
    except ValueError:
        return None


def _parse_status(entry_elem: etree._Element) -> EntryStatus:
    sts_elem = _child(entry_elem, "Sts")
    text = _text(sts_elem)
    if text is None:
        # Some schema versions wrap the code: <Sts><Cd>BOOK</Cd></Sts>
        text = _text(_child(sts_elem, "Cd"))
    try:
        return EntryStatus(text) if text else EntryStatus.INFO
    except ValueError:
        return EntryStatus.INFO


def _parse_bank_transaction_code(bktxcd_elem: etree._Element | None) -> str | None:
    if bktxcd_elem is None:
        return None
    domn = _child(bktxcd_elem, "Domn")
    if domn is not None:
        fmly = _child(domn, "Fmly")
        parts = [
            _text(_child(domn, "Cd")),
            _text(_child(fmly, "Cd")) if fmly is not None else None,
            _text(_child(fmly, "SubFmlyCd")) if fmly is not None else None,
        ]
        parts = [p for p in parts if p]
        if parts:
            return "-".join(parts)
    prtry = _child(bktxcd_elem, "Prtry")
    if prtry is not None:
        return _text(_child(prtry, "Cd"))
    return None


def _parse_party(pty_elem: etree._Element | None, acct_elem: etree._Element | None) -> Party | None:
    name = _text(_child(pty_elem, "Nm")) if pty_elem is not None else None
    iban = None
    other_id = None
    if acct_elem is not None:
        id_elem = _child(acct_elem, "Id")
        iban = _text(_child(id_elem, "IBAN"))
        if iban is None:
            othr = _child(id_elem, "Othr")
            other_id = _text(_child(othr, "Id"))
    if name is None and iban is None and other_id is None:
        return None
    return Party(name=name, iban=iban, other_id=other_id)


def _parse_balance(bal_elem: etree._Element) -> Balance:
    tp = _path(bal_elem, "Tp", "CdOrPrtry")
    code = _text(_child(tp, "Cd")) or _text(_child(tp, "Prtry")) or "UNKN"
    amount, currency = _parse_amount(bal_elem)
    credit_debit = _parse_credit_debit(bal_elem) or CreditDebit.CREDIT
    bal_date = _as_date(_parse_date_or_datetime(_child(bal_elem, "Dt")))
    return Balance(
        code=code,
        amount=amount if amount is not None else Decimal("0"),
        currency=currency or "",
        credit_debit=credit_debit,
        date=bal_date,
    )


def _parse_transaction_details(tx_elem: etree._Element) -> TransactionDetails:
    amount, currency = _parse_amount(tx_elem)
    refs = _child(tx_elem, "Refs")
    rltd_pties = _child(tx_elem, "RltdPties")
    rmt_inf = _child(tx_elem, "RmtInf")
    return TransactionDetails(
        amount=amount,
        currency=currency,
        credit_debit=_parse_credit_debit(tx_elem),
        end_to_end_id=_text(_child(refs, "EndToEndId")),
        instruction_id=_text(_child(refs, "InstrId")),
        account_servicer_ref=_text(_child(refs, "AcctSvcrRef")),
        remittance_info=_text(_child(rmt_inf, "Ustrd")),
        bank_transaction_code=_parse_bank_transaction_code(_child(tx_elem, "BkTxCd")),
        debtor=_parse_party(_child(rltd_pties, "Dbtr"), _child(rltd_pties, "DbtrAcct")),
        creditor=_parse_party(_child(rltd_pties, "Cdtr"), _child(rltd_pties, "CdtrAcct")),
    )


def _parse_entry(ntry_elem: etree._Element) -> Entry:
    amount, currency = _parse_amount(ntry_elem)
    if amount is None:
        raise CamtParseError("Entry (Ntry) is missing an Amt element")
    booking_date = _parse_date_or_datetime(_child(ntry_elem, "BookgDt"))
    value_date = _parse_date_or_datetime(_child(ntry_elem, "ValDt"))
    tx_details = [
        _parse_transaction_details(tx)
        for ntry_dtls in _children(ntry_elem, "NtryDtls")
        for tx in _children(ntry_dtls, "TxDtls")
    ]
    return Entry(
        amount=amount,
        currency=currency or "",
        credit_debit=_parse_credit_debit(ntry_elem) or CreditDebit.CREDIT,
        status=_parse_status(ntry_elem),
        booking_date=_as_date(booking_date),
        value_date=_as_date(value_date),
        account_servicer_ref=_text(_child(ntry_elem, "AcctSvcrRef")),
        bank_transaction_code=_parse_bank_transaction_code(_child(ntry_elem, "BkTxCd")),
        additional_info=_text(_child(ntry_elem, "AddtlNtryInf")),
        transaction_details=tx_details,
    )


def _parse_statement(stmt_elem: etree._Element) -> Statement:
    stmt_id = _text(_child(stmt_elem, "Id")) or ""
    creation_dt = _parse_datetime(_text(_child(stmt_elem, "CreDtTm")))

    fr_to_dt = _child(stmt_elem, "FrToDt")
    from_dt = _parse_date_or_datetime(_child(fr_to_dt, "FrDtTm")) if fr_to_dt is not None else None
    to_dt = _parse_date_or_datetime(_child(fr_to_dt, "ToDtTm")) if fr_to_dt is not None else None

    acct = _child(stmt_elem, "Acct")
    acct_id = _child(acct, "Id")
    account_iban = _text(_child(acct_id, "IBAN"))
    account_other_id = None
    if account_iban is None:
        account_other_id = _text(_child(_child(acct_id, "Othr"), "Id"))
    account_currency = _text(_child(acct, "Ccy"))
    account_owner = _parse_party(_child(acct, "Ownr"), None)
    servicer_bic = _text(_path(acct, "Svcr", "FinInstnId", "BICFI")) or _text(
        _path(acct, "Svcr", "FinInstnId", "BIC")
    )

    balances = [_parse_balance(b) for b in _children(stmt_elem, "Bal")]
    entries = [_parse_entry(n) for n in _children(stmt_elem, "Ntry")]

    return Statement(
        id=stmt_id,
        creation_datetime=creation_dt,
        from_date=_as_date(from_dt),
        to_date=_as_date(to_dt),
        account_iban=account_iban,
        account_other_id=account_other_id,
        account_currency=account_currency,
        account_owner=account_owner,
        servicer_bic=servicer_bic,
        balances=balances,
        entries=entries,
    )


def _detect_message_type(document_elem: etree._Element) -> tuple[MessageType, etree._Element]:
    for msg_type in MessageType:
        wrapper = _child(document_elem, msg_type.group_wrapper_tag)
        if wrapper is not None:
            return msg_type, wrapper
    found = ", ".join(_local(c.tag) for c in document_elem)
    raise UnsupportedMessageType(
        f"Root <Document> does not contain a supported CAMT wrapper element (found: {found or 'none'})"
    )


def parse_bytes(data: bytes) -> Document:
    """Parse raw CAMT XML bytes into a `Document`."""
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        raise CamtParseError(f"Malformed XML: {exc}") from exc

    if _local(root.tag) != "Document":
        raise CamtParseError(f"Expected root element <Document>, found <{_local(root.tag)}>")

    msg_type, wrapper = _detect_message_type(root)

    grp_hdr = _child(wrapper, "GrpHdr")
    message_id = _text(_child(grp_hdr, "MsgId")) or ""
    creation_dt = _parse_datetime(_text(_child(grp_hdr, "CreDtTm")))

    statements = [
        _parse_statement(elem) for elem in _children(wrapper, msg_type.entry_group_tag)
    ]

    return Document(
        message_type=msg_type,
        message_id=message_id,
        creation_datetime=creation_dt,
        statements=statements,
    )


def parse_string(text: str) -> Document:
    return parse_bytes(text.encode("utf-8"))


def parse_file(source: str | os.PathLike[str] | IO[bytes]) -> Document:
    """Parse a CAMT XML file given a path or an open binary file-like object."""
    if hasattr(source, "read"):
        return parse_bytes(source.read())
    with open(source, "rb") as f:
        return parse_bytes(f.read())
