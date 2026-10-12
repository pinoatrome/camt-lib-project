"""Parse ISO 20022 camt.047 (ReturnReservation) messages.

camt.047 is the response half of the camt.046 GetReservation request (see
`camt.camt046`) -- not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so, like
camt.004, it's parsed here directly rather than through that pair.

A response is `RtrRsvatn`: a `MsgHdr` naming the query it answers
(`OrgnlBizQry/MsgId`), then `RptOrErr`, either an operational error
(`OprlErr`) or a report (`BizRpt`) of the current (`CurRsvatn`) and default
(`DfltRsvatn`) reservations. Each names its type and account (`RsvatnId`) and
holds either the reservation (`RsvatnOrErr/Rsvatn`: amount, status, start) or
an error about it (`RsvatnOrErr/BizErr`). Parsing matches elements by local
name, so any camt.047 version reads; the library's checks use .001.08, the newest.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from ._investigation import read_root
from .exceptions import CamtParseError
from .parser import _child, _children, _path, _text


@dataclass
class ReservationRecord:
    """One reservation held against an account (an amount earmarked for a
    specific purpose, e.g. a minimum reserve requirement or a standing
    facility), or the error the reporter gave about it (`error_code`)."""

    type_code: str | None  # Tp/Cd (or Tp/Prtry), e.g. UPAR, MMR
    amount: float
    currency: str
    status: str | None  # Sts/Cd: ENAB, DISA, DELD, REQD, BLKD (or Sts/Prtry)
    from_date: str | None = None  # StartDtTm, as a date or a date-time
    to_date: str | None = None  # not in ISO's reservation: always None
    default: bool = False  # a default reservation (DfltRsvatn), not a current one
    error_code: str | None = None  # RsvatnOrErr/BizErr/Err
    error_description: str | None = None


@dataclass
class Camt047Response:
    """Top-level parsed camt.047 ReturnReservation message.

    `original_msg_id` is the camt.046 request's message ID. `reservations` is
    None for an operational error (`error_code`, `error_description`). The
    account is the first reservation's.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    account_iban: str | None = None
    account_other_id: str | None = None
    reservations: list[ReservationRecord] | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _choice(element: etree._Element | None) -> str | None:
    """The code of a Cd/Prtry choice."""
    return _text(_child(element, "Cd")) or _text(_child(element, "Prtry"))


def _amount(element: etree._Element | None) -> tuple[float, str]:
    """Amount2Choice: `AmtWthCcy` with its currency, or `AmtWthtCcy` without one."""
    with_currency = _child(element, "AmtWthCcy")
    amount = with_currency if with_currency is not None else _child(element, "AmtWthtCcy")
    if amount is None or _text(amount) is None:
        return 0.0, ""
    try:
        return float(_text(amount)), amount.get("Ccy", "")
    except ValueError as exc:
        raise CamtParseError(f"Invalid reservation amount: {_text(amount)!r}") from exc


def _parse_reservation(report: etree._Element, default: bool) -> ReservationRecord:
    reservation_id = _child(report, "RsvatnId")
    outcome = _child(report, "RsvatnOrErr")
    reservation = _child(outcome, "Rsvatn")
    error = _child(outcome, "BizErr")
    amount, currency = _amount(_child(reservation, "Amt"))
    start = _child(reservation, "StartDtTm")
    return ReservationRecord(
        type_code=_choice(_child(reservation_id, "Tp")),
        amount=amount,
        currency=currency,
        status=_choice(_child(reservation, "Sts")),
        from_date=_text(_child(start, "Dt")) or _text(_child(start, "DtTm")),
        default=default,
        error_code=_choice(_child(error, "Err")),
        error_description=_text(_child(error, "Desc")),
    )


def parse_camt047(xml_bytes: bytes) -> Camt047Response:
    """Parse a camt.047 ReturnReservation message (any version, a GetReservation
    response) into a `Camt047Response`. Raises `CamtParseError` if it isn't one."""
    response = read_root(xml_bytes, "camt.047", "RtrRsvatn")
    header = _child(response, "MsgHdr")
    common = {
        "response_msg_id": _text(_child(header, "MsgId")),
        "original_msg_id": _text(_path(header, "OrgnlBizQry", "MsgId")),
        "created_at": _text(_child(header, "CreDtTm")),
    }
    report_or_error = _child(response, "RptOrErr")
    if report_or_error is None:
        raise CamtParseError("No <RptOrErr> in the camt.047 response.")

    error = _child(report_or_error, "OprlErr")
    if error is not None:
        return Camt047Response(
            **common, error_code=_choice(_child(error, "Err")), error_description=_text(_child(error, "Desc")),
        )

    report = _child(report_or_error, "BizRpt")
    if report is None:
        raise CamtParseError("Neither <BizRpt> nor <OprlErr> in the camt.047 response.")
    reports = [(r, False) for r in _children(report, "CurRsvatn")] + [(r, True) for r in _children(report, "DfltRsvatn")]
    account = _path(reports[0][0], "RsvatnId", "AcctId") if reports else None
    return Camt047Response(
        **common,
        account_iban=_text(_child(account, "IBAN")),
        account_other_id=_text(_path(account, "Othr", "Id")),
        reservations=[_parse_reservation(r, default) for r, default in reports],
    )
