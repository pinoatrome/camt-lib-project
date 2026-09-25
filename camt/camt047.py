"""Parse ISO 20022 camt.047.001.05 (ReturnReservation) messages.

camt.047 is the response half of the camt.046 GetReservation request (see
`camt.camt046`) -- not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so, like
camt.004, it's parsed here directly rather than through that pair.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .enums import iso20022_namespace

_NAMESPACE = iso20022_namespace("camt.047", "001.05")
_NS_PREFIX = f"{{{_NAMESPACE}}}"


@dataclass
class ReservationRecord:
    """One reservation held against an account (an amount earmarked for a
    specific purpose, e.g. a minimum reserve requirement or a standing
    facility)."""

    type_code: str | None  # e.g. MMR (minimum reserve), STO (standing facility)
    amount: float
    currency: str
    status: str | None  # e.g. ACTV, CLSD
    from_date: str | None = None
    to_date: str | None = None


@dataclass
class Camt047Response:
    """Top-level parsed camt.047.001.05 ReturnReservation message.

    `original_msg_id` is the camt.046 request's message ID.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    account_iban: str | None = None
    account_other_id: str | None = None
    reservations: list[ReservationRecord] | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _tag(name: str) -> str:
    return f"{_NS_PREFIX}{name}"


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text if found is not None else None


def _parse_reservation(rsvatn_el: etree._Element) -> ReservationRecord:
    type_code = _text(rsvatn_el, f"{_tag('Tp')}/{_tag('Cd')}")
    amt_el = rsvatn_el.find(_tag("Amt"))
    amount = float(amt_el.text) if amt_el is not None else 0.0
    currency = amt_el.get("Ccy", "") if amt_el is not None else ""
    status = _text(rsvatn_el, f"{_tag('Sts')}/{_tag('Cd')}")
    from_date = _text(rsvatn_el, _tag("FrDt"))
    to_date = _text(rsvatn_el, _tag("ToDt"))

    return ReservationRecord(
        type_code=type_code,
        amount=amount,
        currency=currency,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )


def parse_camt047(xml_bytes: bytes) -> Camt047Response:
    """Parse a camt.047.001.05 ReturnReservation message (a GetReservation
    response) into a `Camt047Response`."""
    root = etree.fromstring(xml_bytes)
    rtr = root.find(_tag("RtrRsvatn"))
    if rtr is None:
        raise ValueError("Root element <RtrRsvatn> not found in camt.047 response")

    hdr = rtr.find(_tag("MsgHdr"))
    resp_msg_id = _text(hdr, _tag("MsgId"))
    created_at = _text(hdr, _tag("CreDtTm"))
    orig_qry = hdr.find(_tag("OrgnlBizQry")) if hdr is not None else None
    orig_msg_id = _text(orig_qry, _tag("MsgId")) if orig_qry is not None else None

    rpt_or_err = rtr.find(_tag("RptOrErr"))

    biz_err = rpt_or_err.find(_tag("BizErr")) if rpt_or_err is not None else None
    if biz_err is not None:
        return Camt047Response(
            response_msg_id=resp_msg_id,
            original_msg_id=orig_msg_id,
            created_at=created_at,
            error_code=_text(biz_err, f"{_tag('Err')}/{_tag('Prtry')}"),
            error_description=_text(biz_err, _tag("Desc")),
        )

    rsvatn_rpt = rpt_or_err.find(_tag("RsvatnRpt"))

    account_iban = _text(rsvatn_rpt, f"{_tag('AcctId')}/{_tag('IBAN')}")
    account_other_id = _text(rsvatn_rpt, f"{_tag('AcctId')}/{_tag('Othr')}/{_tag('Id')}")

    reservations = [
        _parse_reservation(rsvatn_el)
        for rsvatn_el in rsvatn_rpt.findall(_tag("Rsvatn"))
    ]

    return Camt047Response(
        response_msg_id=resp_msg_id,
        original_msg_id=orig_msg_id,
        created_at=created_at,
        account_iban=account_iban,
        account_other_id=account_other_id,
        reservations=reservations,
    )
