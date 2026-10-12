"""Parse ISO 20022 camt.019 (ReturnBusinessDayInformation) messages.

camt.019 is the response half of the camt.018 GetBusinessDayInformation
request (see `camt.camt018`) -- not one of the bank-to-customer *report*
messages (camt.052/053/054) that `camt.parser`/`camt.builder` target, so,
like camt.004, it's parsed here directly rather than through that pair.

A response is `RtrBizDayInf`: a `MsgHdr` naming the query it answers
(`OrgnlBizQry/MsgId`), then `RptOrErr`, either operational errors (`OprlErr`)
or reports (`BizRpt`), each about a system (`SysId/MktInfrstrctrId`) and holding
either its business day (`BizDayOrErr/BizDayInf`: the date `SysDt`, the status
`SysSts/Sts`, e.g. ACTV, CLSD, and the events of each currency's day
`SysInfPerCcy/Evt`, by type and scheduled time) or an error about it
(`BizDayOrErr/BizErr`). Parsing matches elements by local name, so any camt.019
version reads; the library's checks use .001.07, the newest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from ._investigation import read_root
from .exceptions import CamtParseError
from .parser import _child, _children, _path, _text


@dataclass
class SystemEvent:
    """One scheduled event in a system's business day (e.g. a cut-off time)."""

    code: str | None  # Tp/Cd (up to 4 characters) or Tp/Prtry/Id, e.g. CUT-OFF-CUST
    event_datetime: str | None  # SchdldTm, when it's scheduled
    effective_datetime: str | None = None  # FctvTm, when it took effect


@dataclass
class BusinessDayInfo:
    """A successful camt.019 business-day record for one system."""

    system_id: str | None
    business_date: str | None
    status: str | None  # SysSts/Sts: ACTV, SUSP, CLSD, CLSG (or a proprietary one)
    events: list[SystemEvent] = field(default_factory=list)

    def event_time(self, code: str) -> str | None:
        """The datetime of the first event with this code (e.g.
        "CUT-OFF-CUST"), or None if the schedule doesn't carry it."""
        for event in self.events:
            if event.code == code:
                return event.event_datetime
        return None


@dataclass
class Camt019Response:
    """Top-level parsed camt.019 ReturnBusinessDayInformation message, from its
    first report.

    `original_msg_id` is the camt.018 request's message ID.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    business_day: BusinessDayInfo | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _choice(element: etree._Element | None) -> str | None:
    """The code of a Cd/Prtry choice, a GenericIdentification1 `Prtry` by its `Id`."""
    proprietary = _child(element, "Prtry")
    return _text(_child(element, "Cd")) or _text(_child(proprietary, "Id")) or _text(proprietary)


def _error(element: etree._Element) -> tuple[str | None, str | None]:
    return _choice(_child(element, "Err")), _text(_child(element, "Desc"))


def parse_camt019(xml_bytes: bytes) -> Camt019Response:
    """Parse a camt.019 ReturnBusinessDayInformation message (any version, a
    GetBusinessDayInformation response) into a `Camt019Response`. Raises
    `CamtParseError` if it isn't one."""
    message = read_root(xml_bytes, "camt.019", "RtrBizDayInf")
    header = _child(message, "MsgHdr")
    common = {
        "response_msg_id": _text(_child(header, "MsgId")),
        "original_msg_id": _text(_path(header, "OrgnlBizQry", "MsgId")),
        "created_at": _text(_child(header, "CreDtTm")),
    }
    report_or_error = _child(message, "RptOrErr")
    if report_or_error is None:
        raise CamtParseError("No <RptOrErr> in the camt.019 response.")

    operational = _child(report_or_error, "OprlErr")
    if operational is not None:
        code, description = _error(operational)
        return Camt019Response(**common, error_code=code, error_description=description)
    report = _child(report_or_error, "BizRpt")
    if report is None:
        raise CamtParseError("Neither <BizRpt> nor <OprlErr> in the camt.019 response.")
    error = _path(report, "BizDayOrErr", "BizErr")
    if error is not None:
        code, description = _error(error)
        return Camt019Response(**common, error_code=code, error_description=description)

    day = _path(report, "BizDayOrErr", "BizDayInf")
    date = _child(day, "SysDt")
    return Camt019Response(
        **common,
        business_day=BusinessDayInfo(
            system_id=_choice(_path(report, "SysId", "MktInfrstrctrId")),
            business_date=_text(_child(date, "Dt")) or _text(_child(date, "DtTm")),
            status=_choice(_path(day, "SysSts", "Sts")),
            events=[
                SystemEvent(
                    code=_choice(_child(event, "Tp")),
                    event_datetime=_text(_child(event, "SchdldTm")),
                    effective_datetime=_text(_child(event, "FctvTm")),
                )
                for per_currency in _children(day, "SysInfPerCcy")
                for event in _children(per_currency, "Evt")
            ],
        ),
    )
