"""Parse ISO 20022 camt.006 (ReturnTransaction) messages.

camt.006 is the response half of the camt.005 GetTransaction request (see
`camt.camt005`) -- not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so, like
camt.004, it's parsed here directly rather than through that pair.

A response is `RtrTx`: a `MsgHdr` naming the query it answers
(`OrgnlBizQry/MsgId`) and, for a named one, its name (`QryNm`), then
`RptOrErr`, either operational errors (`OprlErr`) or a report (`BizRpt`) of
transactions (`TxRpt`). Each names its payment (`PmtId`) and holds either the
transaction (`TxOrErr/Tx`: its direction, the payment with its ids, amount and
status, the account entry with its amount, date and status) or an error about
it (`TxOrErr/BizErr`). For a delta follow-up (see
`camt.camt005.build_get_transaction_delta_request_element`) the report lists
just what changed; a payment's status says how (e.g. `CAND`, cancelled).
Parsing matches elements by local name, so any camt.006 version reads; the
library's checks use .001.11, the newest.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from ._investigation import read_root
from .exceptions import CamtParseError
from .parser import _child, _children, _path, _text

# The payment status choice (PaymentStatusCode6Choice): pending, final, or another scheme's.
_PAYMENT_STATUS_TAGS = ("Fnl", "Pdg", "RTGS", "Sttlm", "Prtry")


@dataclass
class TransactionRecord:
    """One transaction a camt.006 reports, or the error the reporter gave about it."""

    tx_id: str | None  # PmtId/TxId, else the payment's TxId
    end_to_end_id: str | None
    amount: float
    currency: str
    credit_debit: str | None  # CRDT | DBIT
    status: str | None  # the entry's: BOOK, PDNG, FUTR
    booking_date: str | None  # the entry's date (Dt or DtTm)
    additional_info: str | None = None  # the entry's AddtlNtryInf lines, joined
    payment_status: str | None = None  # the payment's: e.g. STLD, RJTD, CAND (final), ACPD (pending)
    message_id: str | None = None  # the payment's MsgId
    error_code: str | None = None  # TxOrErr/BizErr/Err
    error_description: str | None = None


@dataclass
class Camt006Response:
    """Top-level parsed camt.006 ReturnTransaction message.

    `original_msg_id` is the camt.005 request's message ID. `query_name` is
    the named query (see
    `camt.camt005.build_get_transaction_request_element`'s `new_query_name`)
    this response reports against, if any -- pass it into
    `camt.camt005.build_get_transaction_delta_request_element` for the next
    delta follow-up. `transactions` is None for an operational error.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    query_name: str | None
    transactions: list[TransactionRecord] | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _choice(element: etree._Element | None) -> str | None:
    """The code of a Cd/Prtry choice."""
    return _text(_child(element, "Cd")) or _text(_child(element, "Prtry"))


def _amount(element: etree._Element | None) -> tuple[float | None, str]:
    if element is None or _text(element) is None:
        return None, ""
    try:
        return float(_text(element)), element.get("Ccy", "")
    except ValueError as exc:
        raise CamtParseError(f"Invalid transaction amount: {_text(element)!r}") from exc


def _payment_status(payment: etree._Element | None) -> str | None:
    code = _path(payment, "Sts", "Cd")
    return next((_text(_child(code, tag)) for tag in _PAYMENT_STATUS_TAGS if _child(code, tag) is not None), None)


def _parse_transaction(report: etree._Element) -> TransactionRecord:
    outcome = _child(report, "TxOrErr")
    transaction = _child(outcome, "Tx")
    error = _child(outcome, "BizErr")
    payment = _child(transaction, "Pmt")
    entry = _path(transaction, "AcctNtry", "Ntry")
    amount, currency = _amount(_child(entry, "Amt"))
    if amount is None:
        settlement = _child(payment, "IntrBkSttlmAmt")
        amount, currency = _amount(_child(settlement, "AmtWthCcy"))
        if amount is None:
            amount, currency = _amount(_child(settlement, "AmtWthtCcy"))
    date = _child(entry, "Dt")
    lines = [_text(line) for line in _children(entry, "AddtlNtryInf")]
    return TransactionRecord(
        tx_id=_text(_path(report, "PmtId", "TxId")) or _text(_child(payment, "TxId")),
        end_to_end_id=_text(_child(payment, "EndToEndId")),
        amount=amount or 0.0,
        currency=currency,
        credit_debit=_text(_child(transaction, "CdtDbtInd")),
        status=_text(_child(entry, "Sts")),
        booking_date=_text(_child(date, "Dt")) or _text(_child(date, "DtTm")),
        additional_info=" ".join(line for line in lines if line) or None,
        payment_status=_payment_status(payment),
        message_id=_text(_child(payment, "MsgId")),
        error_code=_choice(_child(error, "Err")),
        error_description=_text(_child(error, "Desc")),
    )


def parse_camt006(xml_bytes: bytes) -> Camt006Response:
    """Parse a camt.006 ReturnTransaction message (any version: a GetTransaction
    response, full or delta) into a `Camt006Response`. Raises `CamtParseError` if
    it isn't one."""
    message = read_root(xml_bytes, "camt.006", "RtrTx")
    header = _child(message, "MsgHdr")
    common = {
        "response_msg_id": _text(_child(header, "MsgId")),
        "original_msg_id": _text(_path(header, "OrgnlBizQry", "MsgId")),
        "created_at": _text(_child(header, "CreDtTm")),
        "query_name": _text(_child(header, "QryNm")),
    }
    report_or_error = _child(message, "RptOrErr")
    if report_or_error is None:
        raise CamtParseError("No <RptOrErr> in the camt.006 response.")

    error = _child(report_or_error, "OprlErr")
    if error is not None:
        return Camt006Response(
            **common, error_code=_choice(_child(error, "Err")), error_description=_text(_child(error, "Desc")),
        )
    report = _child(report_or_error, "BizRpt")
    if report is None:
        raise CamtParseError("Neither <BizRpt> nor <OprlErr> in the camt.006 response.")
    return Camt006Response(**common, transactions=[_parse_transaction(r) for r in _children(report, "TxRpt")])
