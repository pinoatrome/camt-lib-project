"""Parse ISO 20022 camt.006.001.08 (ReturnTransaction) messages.

camt.006 is the response half of the camt.005 GetTransaction request (see
`camt.camt005`) -- not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so, like
camt.004, it's parsed here directly rather than through that pair.

For a delta follow-up request (see
`camt.camt005.build_get_transaction_delta_request_element`), the response
groups its transactions into three sets -- new, modified, and cancelled since
the named query was last answered -- instead of repeating the full result
set every time; `DeltaTransactionSet` models that grouping. A first,
non-delta response reports its whole result set as `new`, leaving
`modified`/`cancelled` empty.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .enums import iso20022_namespace

_NAMESPACE = iso20022_namespace("camt.006", "001.08")
_NS_PREFIX = f"{{{_NAMESPACE}}}"


@dataclass
class TransactionRecord:
    """One transaction inside a camt.006 New/Modified/Cancelled set."""

    tx_id: str | None
    end_to_end_id: str | None
    amount: float
    currency: str
    credit_debit: str | None  # CRDT | DBIT
    status: str | None  # e.g. BOOK, PDNG, RJCT
    booking_date: str | None
    additional_info: str | None = None


@dataclass
class DeltaTransactionSet:
    """The three transaction groups a camt.006 response reports: new since
    the last query, modified since the last query (e.g. a status change),
    and cancelled since the last query. A first, non-delta response reports
    its full result set as `new`, leaving `modified`/`cancelled` empty."""

    new: list[TransactionRecord] = field(default_factory=list)
    modified: list[TransactionRecord] = field(default_factory=list)
    cancelled: list[TransactionRecord] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.new or self.modified or self.cancelled)


@dataclass
class Camt006Response:
    """Top-level parsed camt.006.001.08 ReturnTransaction message.

    `original_msg_id` is the camt.005 request's message ID. `query_name` is
    the named query (see
    `camt.camt005.build_get_transaction_request_element`'s `new_query_name`)
    this response reports against, if any -- pass it into
    `camt.camt005.build_get_transaction_delta_request_element` for the next
    delta follow-up.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    query_name: str | None
    transactions: DeltaTransactionSet | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _tag(name: str) -> str:
    return f"{_NS_PREFIX}{name}"


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text if found is not None else None


def _parse_tx_details(tx_el: etree._Element) -> TransactionRecord:
    refs = tx_el.find(_tag("Refs"))
    tx_id = _text(refs, _tag("TxId")) or _text(refs, _tag("AcctSvcrRef"))
    end_to_end_id = _text(refs, _tag("EndToEndId"))

    amt_el = tx_el.find(_tag("Amt"))
    amount = float(amt_el.text) if amt_el is not None else 0.0
    currency = amt_el.get("Ccy", "") if amt_el is not None else ""

    credit_debit = _text(tx_el, _tag("CdtDbtInd"))
    status = _text(tx_el, f"{_tag('Sts')}/{_tag('Cd')}")
    booking_date = _text(tx_el, f"{_tag('BookgDt')}/{_tag('Dt')}") or _text(
        tx_el, f"{_tag('BookgDt')}/{_tag('DtTm')}"
    )
    additional_info = _text(tx_el, _tag("AddtlTxInf"))

    return TransactionRecord(
        tx_id=tx_id,
        end_to_end_id=end_to_end_id,
        amount=amount,
        currency=currency,
        credit_debit=credit_debit,
        status=status,
        booking_date=booking_date,
        additional_info=additional_info,
    )


def _parse_tx_group(parent: etree._Element | None, group_tag: str) -> list[TransactionRecord]:
    group_el = parent.find(_tag(group_tag)) if parent is not None else None
    if group_el is None:
        return []
    return [_parse_tx_details(tx_el) for tx_el in group_el.findall(_tag("TxDtls"))]


def parse_camt006(xml_bytes: bytes) -> Camt006Response:
    """Parse a camt.006.001.08 ReturnTransaction message (a GetTransaction
    response, full or delta) into a `Camt006Response`."""
    root = etree.fromstring(xml_bytes)
    rtr = root.find(_tag("RtrTx"))
    if rtr is None:
        raise ValueError("Root element <RtrTx> not found in camt.006 response")

    hdr = rtr.find(_tag("MsgHdr"))
    resp_msg_id = _text(hdr, _tag("MsgId"))
    created_at = _text(hdr, _tag("CreDtTm"))
    orig_qry = hdr.find(_tag("OrgnlBizQry")) if hdr is not None else None
    orig_msg_id = _text(orig_qry, _tag("MsgId")) if orig_qry is not None else None
    query_name = _text(orig_qry, _tag("QryNm")) if orig_qry is not None else None

    rpt_or_err = rtr.find(_tag("RptOrErr"))

    biz_err = rpt_or_err.find(_tag("BizErr")) if rpt_or_err is not None else None
    if biz_err is not None:
        return Camt006Response(
            response_msg_id=resp_msg_id,
            original_msg_id=orig_msg_id,
            created_at=created_at,
            query_name=query_name,
            error_code=_text(biz_err, f"{_tag('Err')}/{_tag('Prtry')}"),
            error_description=_text(biz_err, _tag("Desc")),
        )

    tx_rpt = rpt_or_err.find(_tag("TxRpt"))
    query_name = _text(tx_rpt, _tag("QryNm")) or query_name

    tx_rpt_or_err = tx_rpt.find(_tag("TxRptOrErr")) if tx_rpt is not None else None
    tx_grp = tx_rpt_or_err.find(_tag("TxRpt")) if tx_rpt_or_err is not None else None

    transactions = DeltaTransactionSet(
        new=_parse_tx_group(tx_grp, "New"),
        modified=_parse_tx_group(tx_grp, "Mod"),
        cancelled=_parse_tx_group(tx_grp, "Canc"),
    )

    return Camt006Response(
        response_msg_id=resp_msg_id,
        original_msg_id=orig_msg_id,
        created_at=created_at,
        query_name=query_name,
        transactions=transactions,
    )
