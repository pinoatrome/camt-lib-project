"""Build ISO 20022 camt.018.001.04 (GetBusinessDayInformation) request documents.

Like camt.003 (see `camt.camt003`), this is the outbound *request* half of a
Get/Return pair -- its response counterpart is camt.019 (see `camt.camt019`)
-- so, like that pair, it's built here directly rather than through
`camt.builder`.

A business-day query asks a settlement system (e.g. TARGET2/T2, CLM, TIPS)
for the status of one business day -- open/closed/changeover -- and the
schedule of its key events (start of day, cut-off times, end of day). Used
to check operating hours and cut-off deadlines before submitting a payment or
liquidity instruction, rather than assuming a fixed calendar.
"""
from __future__ import annotations

from datetime import date, datetime

from lxml import etree

from .builder import sub
from .enums import iso20022_namespace


def build_get_business_day_request_element(
    system_id: str,
    msg_id: str,
    *,
    business_date: date | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.04",
) -> etree._Element:
    """Build the `<Document>` tree for a camt.018 GetBusinessDayInformation
    request, querying one system's business-day status and event schedule.

    `system_id` is the settlement system's short code (e.g. "TARGET2",
    "CLM", "TIPS"). `business_date` restricts the query to that date; when
    omitted, it asks for the current business day.
    """
    namespace = iso20022_namespace("camt.018", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    get_biz_day_inf = sub(root, "GetBizDayInf")

    msg_hdr = sub(get_biz_day_inf, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    sch_crit = sub(
        sub(sub(sub(get_biz_day_inf, "BizDayInfQryDef"), "SysCrit"), "NewCrit"),
        "SchCrit",
    )
    sub(sub(sch_crit, "SysId"), "Cd", system_id)
    if business_date:
        sub(sch_crit, "SysDt", business_date.isoformat())

    return root


def build_get_business_day_request_bytes(
    system_id: str,
    msg_id: str,
    *,
    business_date: date | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.04",
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.018 GetBusinessDayInformation request, to query a
    system's business-day status and event schedule, as XML bytes."""
    root = build_get_business_day_request_element(
        system_id,
        msg_id,
        business_date=business_date,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_get_business_day_request_string(
    system_id: str,
    msg_id: str,
    *,
    business_date: date | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.04",
    pretty_print: bool = True,
) -> str:
    """Build a camt.018 GetBusinessDayInformation request, to query a
    system's business-day status and event schedule, as an XML string."""
    return build_get_business_day_request_bytes(
        system_id,
        msg_id,
        business_date=business_date,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")
