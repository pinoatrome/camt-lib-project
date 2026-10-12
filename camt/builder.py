"""Serialize `camt.models.Document` objects into ISO 20022 CAMT XML.

Generation targets schema version .001.14 of each message family (camt.052.001.14,
camt.053.001.14, camt.054.001.14: `enums.STATEMENT_VARIANT`), the newest of the ISO
20022 catalogue; tests/test_schemas.py checks the output against its XSDs.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from lxml import etree

from .enums import MessageType
from .exceptions import CamtError
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


def _build_account_id(parent: etree._Element, iban: str | None, other_id: str | None) -> None:
    id_elem = sub(parent, "Id")
    if iban:
        sub(id_elem, "IBAN", iban)
    else:
        sub(sub(id_elem, "Othr"), "Id", other_id)


def _build_account(parent: etree._Element, statement: Statement) -> None:
    acct = sub(parent, "Acct")
    if statement.account_iban or statement.account_other_id:
        _build_account_id(acct, statement.account_iban, statement.account_other_id)
    if statement.account_currency:
        sub(acct, "Ccy", statement.account_currency)
    if _has_party(statement.account_owner):
        _build_party(sub(acct, "Ownr"), statement.account_owner)
    if statement.servicer_bic:
        sub(sub(sub(acct, "Svcr"), "FinInstnId"), "BICFI", statement.servicer_bic)


def _build_balance(parent: etree._Element, balance: Balance) -> None:
    bal = sub(parent, "Bal")
    sub(sub(sub(bal, "Tp"), "CdOrPrtry"), "Cd", balance.code)
    _build_amount(bal, "Amt", balance.amount, balance.currency)
    sub(bal, "CdtDbtInd", balance.credit_debit.value)
    sub(sub(bal, "Dt"), "Dt", iso_date(balance.date))


def _has_party(party: Party | None) -> bool:
    return party is not None and bool(party.name or party.bic)


def _build_party(pty: etree._Element, party: Party) -> None:
    """The party's name and BIC (PartyIdentification272): the BIC in `Id/OrgId/AnyBIC`."""
    if party.name:
        sub(pty, "Nm", party.name)
    if party.bic:
        sub(sub(sub(pty, "Id"), "OrgId"), "AnyBIC", party.bic)


def _build_party_and_account(
    parent: etree._Element, party_tag: str, acct_tag: str, party: Party | None
) -> None:
    """A related party (`Dbtr`/`Cdtr`, a Party50Choice: the party in `Pty`) and its account."""
    if party is None:
        return
    if _has_party(party):
        _build_party(sub(sub(parent, party_tag), "Pty"), party)
    if party.iban or party.other_id:
        _build_account_id(sub(parent, acct_tag), party.iban, party.other_id)


def _build_bank_transaction_code(parent: etree._Element, code: str | None) -> None:
    """`BkTxCd`: a domain code as the parser reads it (`PMNT-RCDT-ESCT`, three
    four-character codes: Domn/Cd, Fmly/Cd, Fmly/SubFmlyCd), else a proprietary one
    (Prtry/Cd); empty without one."""
    bk_tx_cd = sub(parent, "BkTxCd")
    if not code:
        return
    parts = code.split("-")
    if len(parts) == 3 and all(len(part) == 4 and part.isalnum() for part in parts):
        domn = sub(bk_tx_cd, "Domn")
        sub(domn, "Cd", parts[0])
        fmly = sub(domn, "Fmly")
        sub(fmly, "Cd", parts[1])
        sub(fmly, "SubFmlyCd", parts[2])
    else:
        sub(sub(bk_tx_cd, "Prtry"), "Cd", code)


def _build_transaction_details(parent: etree._Element, tx: TransactionDetails) -> None:
    tx_dtls = sub(parent, "TxDtls")
    if tx.end_to_end_id or tx.instruction_id or tx.account_servicer_ref or tx.message_id:
        refs = sub(tx_dtls, "Refs")
        # TransactionReferences order: MsgId, AcctSvcrRef, PmtInfId, InstrId, EndToEndId.
        if tx.message_id:
            sub(refs, "MsgId", tx.message_id)
        if tx.account_servicer_ref:
            sub(refs, "AcctSvcrRef", tx.account_servicer_ref)
        if tx.instruction_id:
            sub(refs, "InstrId", tx.instruction_id)
        if tx.end_to_end_id:
            sub(refs, "EndToEndId", tx.end_to_end_id)
    if tx.amount is not None and tx.currency:
        _build_amount(tx_dtls, "Amt", tx.amount, tx.currency)
    if tx.credit_debit is not None:
        sub(tx_dtls, "CdtDbtInd", tx.credit_debit.value)
    if tx.bank_transaction_code:
        _build_bank_transaction_code(tx_dtls, tx.bank_transaction_code)
    if tx.debtor is not None or tx.creditor is not None:
        rltd_pties = sub(tx_dtls, "RltdPties")
        _build_party_and_account(rltd_pties, "Dbtr", "DbtrAcct", tx.debtor)
        _build_party_and_account(rltd_pties, "Cdtr", "CdtrAcct", tx.creditor)
    if tx.remittance_info:
        rmt_inf = sub(tx_dtls, "RmtInf")
        sub(rmt_inf, "Ustrd", tx.remittance_info)
    if tx.return_info is not None:
        rtr_inf = sub(tx_dtls, "RtrInf")
        if tx.return_info.reason_code or tx.return_info.reason_proprietary:
            rsn = sub(rtr_inf, "Rsn")
            if tx.return_info.reason_code:
                sub(rsn, "Cd", tx.return_info.reason_code)
            else:
                sub(rsn, "Prtry", tx.return_info.reason_proprietary)
        if tx.return_info.additional_info:
            sub(rtr_inf, "AddtlInf", tx.return_info.additional_info)


def _build_entry(parent: etree._Element, entry: Entry) -> None:
    """One `Ntry` (ReportEntry16), its elements in the schema's order."""
    ntry = sub(parent, "Ntry")
    _build_amount(ntry, "Amt", entry.amount, entry.currency)
    sub(ntry, "CdtDbtInd", entry.credit_debit.value)
    sub(sub(ntry, "Sts"), "Cd", entry.status.value)
    if entry.booking_date is not None:
        sub(sub(ntry, "BookgDt"), "Dt", iso_date(entry.booking_date))
    if entry.value_date is not None:
        sub(sub(ntry, "ValDt"), "Dt", iso_date(entry.value_date))
    if entry.account_servicer_ref:
        sub(ntry, "AcctSvcrRef", entry.account_servicer_ref)
    _build_bank_transaction_code(ntry, entry.bank_transaction_code)
    if entry.transaction_details:
        ntry_dtls = sub(ntry, "NtryDtls")
        for tx in entry.transaction_details:
            _build_transaction_details(ntry_dtls, tx)
    if entry.additional_info:
        sub(ntry, "AddtlNtryInf", entry.additional_info)


def _build_statement(parent: etree._Element, message_type: MessageType, statement: Statement) -> None:
    stmt = sub(parent, message_type.entry_group_tag)
    sub(stmt, "Id", statement.id)
    if statement.creation_datetime is not None:
        sub(stmt, "CreDtTm", iso_datetime(statement.creation_datetime))
    if (statement.from_date is None) != (statement.to_date is None):
        raise CamtError(f"Statement {statement.id!r}: FrToDt takes both a from and a to date, or neither.")
    if statement.from_date is not None:
        fr_to_dt = sub(stmt, "FrToDt")
        sub(fr_to_dt, "FrDtTm", iso_datetime(datetime.combine(statement.from_date, datetime.min.time())))
        sub(fr_to_dt, "ToDtTm", iso_datetime(datetime.combine(statement.to_date, datetime.min.time())))
    _build_account(stmt, statement)
    if statement.balances and message_type is MessageType.CAMT_054:
        raise CamtError(f"Notification {statement.id!r}: a camt.054 carries no balances.")
    for balance in statement.balances:
        _build_balance(stmt, balance)
    for entry in statement.entries:
        _build_entry(stmt, entry)


def _build_group_header(wrapper: etree._Element, document: Document) -> None:
    grp_hdr = sub(wrapper, "GrpHdr")
    sub(grp_hdr, "MsgId", document.message_id)
    sub(grp_hdr, "CreDtTm", iso_datetime(document.creation_datetime or datetime.now()))
    if document.page_number is not None or document.last_page is not None:
        if document.page_number is None or document.last_page is None:
            raise CamtError("MsgPgntn takes both a page number and whether it's the last page, or neither.")
        pagination = sub(grp_hdr, "MsgPgntn")
        sub(pagination, "PgNb", str(document.page_number))
        sub(pagination, "LastPgInd", "true" if document.last_page else "false")


def build_element(document: Document) -> etree._Element:
    """Build the lxml `<Document>` tree for a `Document` model. Raises `CamtError` for
    what the schema can't hold: one of the FrToDt or MsgPgntn values without the
    other, balances in a camt.054."""
    root = etree.Element("Document", nsmap={None: document.message_type.namespace})
    wrapper = sub(root, document.message_type.group_wrapper_tag)
    _build_group_header(wrapper, document)
    for statement in document.statements:
        _build_statement(wrapper, document.message_type, statement)
    return root


def build_bytes(document: Document, *, pretty_print: bool = True) -> bytes:
    """Serialize a `Document` model to CAMT XML bytes."""
    root = build_element(document)
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_string(document: Document, *, pretty_print: bool = True) -> str:
    return build_bytes(document, pretty_print=pretty_print).decode("utf-8")
