"""Serialize `camt.models.Document` objects into ISO 20022 CAMT XML.

Generation targets schema version .001.02 for each message family (camt.052.001.02,
camt.053.001.02, camt.054.001.02), which is a widely supported, stable version.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from lxml import etree


from .models import Balance, Document, Entry, Party, Statement, TransactionDetails


def iso_date(value: date) -> str:
    return value.isoformat()


def iso_datetime(value: datetime) -> str:
    return value.isoformat()


def sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    elem = etree.SubElement(parent, tag)
    if text is not None:
        elem.text = text
    return elem


def _build_amount(parent: etree._Element, tag: str, amount: Decimal, currency: str) -> None:
    elem = sub(parent, tag, str(amount))
    elem.set("Ccy", currency)


def _build_account(parent: etree._Element, statement: Statement) -> None:
    acct = sub(parent, "Acct")
    id_elem = sub(acct, "Id")
    if statement.account_iban:
        sub(id_elem, "IBAN", statement.account_iban)
    elif statement.account_other_id:
        othr = sub(id_elem, "Othr")
        sub(othr, "Id", statement.account_other_id)
    if statement.account_currency:
        sub(acct, "Ccy", statement.account_currency)
    if statement.account_owner is not None and statement.account_owner.name:
        ownr = sub(acct, "Ownr")
        sub(ownr, "Nm", statement.account_owner.name)
    if statement.servicer_bic:
        svcr = sub(acct, "Svcr")
        fin_instn_id = sub(svcr, "FinInstnId")
        sub(fin_instn_id, "BICFI", statement.servicer_bic)


def _build_balance(parent: etree._Element, balance: Balance) -> None:
    bal = sub(parent, "Bal")
    tp = sub(bal, "Tp")
    cd_or_prtry = sub(tp, "CdOrPrtry")
    sub(cd_or_prtry, "Cd", balance.code)
    _build_amount(bal, "Amt", balance.amount, balance.currency)
    sub(bal, "CdtDbtInd", balance.credit_debit.value)
    dt = sub(bal, "Dt")
    sub(dt, "Dt", iso_date(balance.date))


def _build_party_and_account(
    parent: etree._Element, party_tag: str, acct_tag: str, party: Party | None
) -> None:
    if party is None:
        return
    if party.name:
        pty = sub(parent, party_tag)
        sub(pty, "Nm", party.name)
    if party.iban or party.other_id:
        acct = sub(parent, acct_tag)
        id_elem = sub(acct, "Id")
        if party.iban:
            sub(id_elem, "IBAN", party.iban)
        else:
            othr = sub(id_elem, "Othr")
            sub(othr, "Id", party.other_id)


def _build_transaction_details(parent: etree._Element, tx: TransactionDetails) -> None:
    tx_dtls = sub(parent, "TxDtls")
    if tx.end_to_end_id or tx.instruction_id or tx.account_servicer_ref:
        refs = sub(tx_dtls, "Refs")
        if tx.instruction_id:
            sub(refs, "InstrId", tx.instruction_id)
        if tx.end_to_end_id:
            sub(refs, "EndToEndId", tx.end_to_end_id)
        if tx.account_servicer_ref:
            sub(refs, "AcctSvcrRef", tx.account_servicer_ref)
    if tx.amount is not None and tx.currency:
        _build_amount(tx_dtls, "Amt", tx.amount, tx.currency)
    if tx.credit_debit is not None:
        sub(tx_dtls, "CdtDbtInd", tx.credit_debit.value)
    if tx.debtor is not None or tx.creditor is not None:
        rltd_pties = sub(tx_dtls, "RltdPties")
        _build_party_and_account(rltd_pties, "Dbtr", "DbtrAcct", tx.debtor)
        _build_party_and_account(rltd_pties, "Cdtr", "CdtrAcct", tx.creditor)
    if tx.remittance_info:
        rmt_inf = sub(tx_dtls, "RmtInf")
        sub(rmt_inf, "Ustrd", tx.remittance_info)


def _build_entry(parent: etree._Element, entry: Entry) -> None:
    ntry = sub(parent, "Ntry")
    if entry.account_servicer_ref:
        sub(ntry, "AcctSvcrRef", entry.account_servicer_ref)
    _build_amount(ntry, "Amt", entry.amount, entry.currency)
    sub(ntry, "CdtDbtInd", entry.credit_debit.value)
    sub(ntry, "Sts", entry.status.value)
    if entry.booking_date is not None:
        bookg_dt = sub(ntry, "BookgDt")
        sub(bookg_dt, "Dt", iso_date(entry.booking_date))
    if entry.value_date is not None:
        val_dt = sub(ntry, "ValDt")
        sub(val_dt, "Dt", iso_date(entry.value_date))
    if entry.additional_info:
        sub(ntry, "AddtlNtryInf", entry.additional_info)
    if entry.transaction_details:
        ntry_dtls = sub(ntry, "NtryDtls")
        for tx in entry.transaction_details:
            _build_transaction_details(ntry_dtls, tx)


def _build_statement(parent: etree._Element, tag: str, statement: Statement) -> None:
    stmt = sub(parent, tag)
    sub(stmt, "Id", statement.id)
    if statement.creation_datetime is not None:
        sub(stmt, "CreDtTm", iso_datetime(statement.creation_datetime))
    if statement.from_date is not None or statement.to_date is not None:
        fr_to_dt = sub(stmt, "FrToDt")
        if statement.from_date is not None:
            sub(fr_to_dt, "FrDtTm", iso_datetime(datetime.combine(statement.from_date, datetime.min.time())))
        if statement.to_date is not None:
            sub(fr_to_dt, "ToDtTm", iso_datetime(datetime.combine(statement.to_date, datetime.min.time())))
    _build_account(stmt, statement)
    for balance in statement.balances:
        _build_balance(stmt, balance)
    for entry in statement.entries:
        _build_entry(stmt, entry)


def build_element(document: Document) -> etree._Element:
    """Build the lxml `<Document>` tree for a `Document` model."""
    namespace = document.message_type.namespace
    root = etree.Element("Document", nsmap={None: namespace})
    wrapper = sub(root, document.message_type.group_wrapper_tag)

    grp_hdr = sub(wrapper, "GrpHdr")
    sub(grp_hdr, "MsgId", document.message_id)
    sub(grp_hdr, "CreDtTm", iso_datetime(document.creation_datetime or datetime.now()))

    entry_tag = document.message_type.entry_group_tag
    for statement in document.statements:
        _build_statement(wrapper, entry_tag, statement)

    return root


def build_bytes(document: Document, *, pretty_print: bool = True) -> bytes:
    """Serialize a `Document` model to CAMT XML bytes."""
    root = build_element(document)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_string(document: Document, *, pretty_print: bool = True) -> str:
    return build_bytes(document, pretty_print=pretty_print).decode("utf-8")
