"""Parse ISO 20022 camt.004.001.08 (ReturnAccount) messages.

camt.004 usually arrives as the response half of the camt.003 GetAccount
request/response pair (see `camt.camt003`), but the same message shape is also
pushed unsolicited as an account alert (e.g. a status change), independent of
any request. Either way it's not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so it's parsed
here directly rather than through the library's parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from .enums import iso20022_namespace

_NAMESPACE = iso20022_namespace("camt.004", "001.08")
_NS_PREFIX = f"{{{_NAMESPACE}}}"


@dataclass
class Balance:
    type_code: str | None  # e.g. "CLBD" (closing booked)
    amount: float
    currency: str
    date: str | None


@dataclass
class AccountReport:
    """A successful camt.004 account record."""

    dean: str | None
    iban: str | None
    currency: str | None
    status: str | None  # ENABLED | BLOCKED | SUSPENDED
    psp_bic: str | None
    psp_name: str | None
    servicer_name: str | None
    account_type: str | None
    balances: list[Balance] = field(default_factory=list)
    hold_limit: float | None = None
    hold_limit_ccy: str | None = None


@dataclass
class Camt004Response:
    """Top-level parsed camt.004.001.08 ReturnAccount message.

    `original_msg_id` is the camt.003 request's message ID when this is a
    response, and None for an unsolicited alert (no `<OrgnlBizInstr>`).
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    account: AccountReport | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _tag(name: str) -> str:
    return f"{_NS_PREFIX}{name}"


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text if found is not None else None


def parse_camt004(xml_bytes: bytes) -> Camt004Response:
    """Parse a camt.004.001.08 ReturnAccount message (a GetAccount response or an
    unsolicited account alert) into a `Camt004Response`."""
    root = etree.fromstring(xml_bytes)
    rtr = root.find(_tag("RtrAcct"))
    if rtr is None:
        raise ValueError("Root element <RtrAcct> not found in camt.004 response")

    hdr = rtr.find(_tag("MsgHdr"))
    resp_msg_id = _text(hdr, _tag("MsgId"))
    created_at = _text(hdr, _tag("CreDtTm"))
    orig_instr = hdr.find(_tag("OrgnlBizInstr")) if hdr is not None else None
    orig_msg_id = _text(orig_instr, _tag("MsgId")) if orig_instr is not None else None

    rpt_or_err = rtr.find(_tag("RptOrErr"))

    biz_err = rpt_or_err.find(_tag("BizErr")) if rpt_or_err is not None else None
    if biz_err is not None:
        err_code = _text(biz_err, f"{_tag('Err')}/{_tag('Prtry')}")
        err_desc = _text(biz_err, _tag("Desc"))
        return Camt004Response(
            response_msg_id=resp_msg_id,
            original_msg_id=orig_msg_id,
            created_at=created_at,
            error_code=err_code,
            error_description=err_desc,
        )

    acct_rpt = rpt_or_err.find(_tag("AcctRpt"))
    acct_el = acct_rpt.find(f"{_tag('AcctOrErr')}/{_tag('Acct')}")

    dean = _text(acct_rpt, f"{_tag('AcctId')}/{_tag('Othr')}/{_tag('Id')}")
    iban = _text(acct_el, f"{_tag('Id')}/{_tag('IBAN')}")
    ccy = _text(acct_el, _tag("Ccy"))
    status = _text(acct_el, f"{_tag('Sts')}/{_tag('Cd')}")

    owner = acct_el.find(f"{_tag('Ownr')}/{_tag('FinInstnId')}")
    psp_bic = _text(owner, _tag("BICFI")) if owner is not None else None
    psp_name = _text(owner, _tag("Nm")) if owner is not None else None

    svcr = acct_el.find(f"{_tag('Svcr')}/{_tag('FinInstnId')}")
    servicer_name = _text(svcr, _tag("Nm")) if svcr is not None else None

    account_type = _text(acct_el, f"{_tag('Tp')}/{_tag('Prtry')}")

    balances: list[Balance] = []
    for bal_el in acct_el.findall(_tag("HldgBal")):
        type_code = _text(
            bal_el, f"{_tag('Tp')}/{_tag('CdOrPrtry')}/{_tag('Cd')}"
        ) or _text(bal_el, f"{_tag('Tp')}/{_tag('CdOrPrtry')}/{_tag('Prtry')}")
        amt_el = bal_el.find(_tag("Amt"))
        amount = float(amt_el.text) if amt_el is not None else 0.0
        currency = amt_el.get("Ccy", "") if amt_el is not None else ""
        date = _text(bal_el, f"{_tag('Dt')}/{_tag('Dt')}") or _text(
            bal_el, f"{_tag('Dt')}/{_tag('DtTm')}"
        )
        balances.append(Balance(type_code=type_code, amount=amount, currency=currency, date=date))

    lmt_el = acct_el.find(f"{_tag('LmtBal')}/{_tag('Amt')}")
    hold_limit = float(lmt_el.text) if lmt_el is not None else None
    hold_limit_ccy = lmt_el.get("Ccy") if lmt_el is not None else None

    account = AccountReport(
        dean=dean,
        iban=iban,
        currency=ccy,
        status=status,
        psp_bic=psp_bic,
        psp_name=psp_name,
        servicer_name=servicer_name,
        account_type=account_type,
        balances=balances,
        hold_limit=hold_limit,
        hold_limit_ccy=hold_limit_ccy,
    )

    return Camt004Response(
        response_msg_id=resp_msg_id,
        original_msg_id=orig_msg_id,
        created_at=created_at,
        account=account,
    )
