"""Parse ISO 20022 camt.019.001.06 (ReturnBusinessDayInformation) messages.

camt.019 is the response half of the camt.018 GetBusinessDayInformation
request (see `camt.camt018`) -- not one of the bank-to-customer *report*
messages (camt.052/053/054) that `camt.parser`/`camt.builder` target, so,
like camt.004, it's parsed here directly rather than through that pair.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .enums import iso20022_namespace

_NAMESPACE = iso20022_namespace("camt.019", "001.06")
_NS_PREFIX = f"{{{_NAMESPACE}}}"


@dataclass
class SystemEvent:
    """One scheduled event in a system's business day (e.g. a cut-off time)."""

    code: str  # e.g. START, CUT-OFF-CUST, CUT-OFF-BANK, END
    event_datetime: str | None


@dataclass
class BusinessDayInfo:
    """A successful camt.019 business-day record for one system."""

    system_id: str | None
    business_date: str | None
    status: str | None  # e.g. OPEN, CLOSED, CHANGEOVER
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
    """Top-level parsed camt.019.001.06 ReturnBusinessDayInformation message.

    `original_msg_id` is the camt.018 request's message ID.
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    business_day: BusinessDayInfo | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _tag(name: str) -> str:
    return f"{_NS_PREFIX}{name}"


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text if found is not None else None


def parse_camt019(xml_bytes: bytes) -> Camt019Response:
    """Parse a camt.019.001.06 ReturnBusinessDayInformation message (a
    GetBusinessDayInformation response) into a `Camt019Response`."""
    root = etree.fromstring(xml_bytes)
    rtr = root.find(_tag("RtrBizDayInf"))
    if rtr is None:
        raise ValueError("Root element <RtrBizDayInf> not found in camt.019 response")

    hdr = rtr.find(_tag("MsgHdr"))
    resp_msg_id = _text(hdr, _tag("MsgId"))
    created_at = _text(hdr, _tag("CreDtTm"))
    orig_qry = hdr.find(_tag("OrgnlBizQry")) if hdr is not None else None
    orig_msg_id = _text(orig_qry, _tag("MsgId")) if orig_qry is not None else None

    rpt_or_err = rtr.find(_tag("RptOrErr"))

    biz_err = rpt_or_err.find(_tag("BizErr")) if rpt_or_err is not None else None
    if biz_err is not None:
        return Camt019Response(
            response_msg_id=resp_msg_id,
            original_msg_id=orig_msg_id,
            created_at=created_at,
            error_code=_text(biz_err, f"{_tag('Err')}/{_tag('Prtry')}"),
            error_description=_text(biz_err, _tag("Desc")),
        )

    biz_day_rpt = rpt_or_err.find(_tag("BizDayInfRpt"))

    system_id = _text(biz_day_rpt, f"{_tag('SysId')}/{_tag('Cd')}")
    business_date = _text(biz_day_rpt, _tag("SysDt"))
    status = _text(biz_day_rpt, f"{_tag('SysSts')}/{_tag('Cd')}")

    events = [
        SystemEvent(
            code=_text(evt_el, _tag("EvtCd")),
            event_datetime=_text(evt_el, _tag("EvtTm")),
        )
        for evt_el in biz_day_rpt.findall(_tag("SysEvt"))
    ]

    business_day = BusinessDayInfo(
        system_id=system_id,
        business_date=business_date,
        status=status,
        events=events,
    )

    return Camt019Response(
        response_msg_id=resp_msg_id,
        original_msg_id=orig_msg_id,
        created_at=created_at,
        business_day=business_day,
    )
