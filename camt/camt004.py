"""Parse and build ISO 20022 camt.004 (ReturnAccount) messages.

camt.004 usually arrives as the response half of the camt.003 GetAccount
request/response pair (see `camt.camt003`), but the same message shape is also
pushed unsolicited as an account alert (e.g. a status change), independent of
any request. Either way it's not one of the bank-to-customer *report* messages
(camt.052/053/054) that `camt.parser`/`camt.builder` target, so it's parsed
here directly rather than through the library's parser.

A message is `RtrAcct`: a `MsgHdr` naming the query it answers
(`OrgnlBizQry/MsgId`, absent from an alert), then `RptOrErr`, either an
operational error (`OprlErr`) or an account report (`AcctRpt`): the account
(`AcctId`: `IBAN` or `Othr/Id`, the DEAN) and either its data (`AcctOrErr/Acct`)
or an error about it (`AcctOrErr/BizErr`). The data: the account's type
(`Tp`), currency (`Ccy`), its limit (`CurMulLmt`, the holding limit), owner
(`Ownr`: name and `Id/OrgId/AnyBIC`), servicer (`Svcr`) and balances (`MulBal`,
signed by `CdtDbtInd`, in the account's currency).

ISO's account has no element for two things DESP tells: the account's IBAN
next to its DEAN, read from the proxy (`Acct/Prxy` with type `IBAN`), and its
status (ENABLED, BLOCKED, ...), read from the supplementary data
(`SplmtryData/Envlp/AcctSts`, in any namespace). Parsing matches elements by
local name, so any camt.004 version reads; `build_return_account_bytes` writes
.001.10, the newest, which the library's checks use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from lxml import etree

from ._investigation import read_root
from .builder import sub
from .enums import iso20022_namespace
from .exceptions import CamtParseError
from .parser import _child, _children, _path, _text

VARIANT = "001.10"

# The supplementary data element carrying the account's status, and the proxy
# type naming its IBAN.
ACCOUNT_STATUS = "AcctSts"
IBAN_PROXY = "IBAN"


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
    status: str | None  # ENABLED | BLOCKED | SUSPENDED, from SplmtryData/Envlp/AcctSts
    psp_bic: str | None
    psp_name: str | None
    servicer_name: str | None
    account_type: str | None
    balances: list[Balance] = field(default_factory=list)
    hold_limit: float | None = None
    hold_limit_ccy: str | None = None

    def balance(self, type_code: str) -> Balance | None:
        return next((b for b in self.balances if b.type_code == type_code), None)

    @property
    def closing_balance(self) -> Balance | None:
        return self.balance("CLBD")

    @property
    def remaining_holding_capacity(self) -> Decimal | None:
        """How much more the account can hold before reaching its holding limit
        (`hold_limit` minus the closing booked balance), or None if either is missing.

        Computed in Decimal so the result is exact for the 2-decimal amounts involved.
        """
        closing = self.closing_balance
        if closing is None or self.hold_limit is None:
            return None
        return Decimal(str(self.hold_limit)) - Decimal(str(closing.amount))


@dataclass
class Camt004Response:
    """Top-level parsed camt.004 ReturnAccount message.

    `original_msg_id` is the camt.003 request's message ID when this is a
    response, and None for an unsolicited alert (no `<OrgnlBizQry>`).
    """

    response_msg_id: str | None
    original_msg_id: str | None
    created_at: str | None
    account: AccountReport | None = None  # None -> error response
    error_code: str | None = None
    error_description: str | None = None


def _choice(element: etree._Element | None) -> str | None:
    """The code of a Cd/Prtry choice."""
    return _text(_child(element, "Cd")) or _text(_child(element, "Prtry"))


def _number(value: str | None, what: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise CamtParseError(f"Invalid {what}: {value!r}") from exc


def _error(element: etree._Element) -> tuple[str | None, str | None]:
    """ErrorHandling5: the code (`Err/Cd` or `Err/Prtry`) and its description."""
    return _choice(_child(element, "Err")), _text(_child(element, "Desc"))


def _balance(element: etree._Element, currency: str) -> Balance:
    """A `MulBal` (CashBalance13): its amount is in the account's currency, negative for a debit."""
    amount = _number(_text(_child(element, "Amt")), "balance amount") or 0.0
    if _text(_child(element, "CdtDbtInd")) == "DBIT":
        amount = -amount
    value_date = _child(element, "ValDt")
    return Balance(
        type_code=_choice(_child(element, "Tp")),
        amount=amount,
        currency=currency,
        date=_text(_child(value_date, "Dt")) or _text(_child(value_date, "DtTm")),
    )


def _status(message: etree._Element) -> str | None:
    """The account's status, from the supplementary data (`Envlp/AcctSts`)."""
    for supplementary in _children(message, "SplmtryData"):
        envelope = _child(supplementary, "Envlp")
        for element in envelope if envelope is not None else []:
            if isinstance(element.tag, str) and etree.QName(element).localname == ACCOUNT_STATUS:
                return _text(element)
    return None


def parse_camt004(xml_bytes: bytes) -> Camt004Response:
    """Parse a camt.004 ReturnAccount message (any version: a GetAccount response or
    an unsolicited account alert) into a `Camt004Response`, from its first account
    report. Raises `CamtParseError` if it isn't a readable one."""
    message = read_root(xml_bytes, "camt.004", "RtrAcct")
    header = _child(message, "MsgHdr")
    common = {
        "response_msg_id": _text(_child(header, "MsgId")),
        "original_msg_id": _text(_path(header, "OrgnlBizQry", "MsgId")),
        "created_at": _text(_child(header, "CreDtTm")),
    }
    report_or_error = _child(message, "RptOrErr")
    if report_or_error is None:
        raise CamtParseError("No <RptOrErr> in the camt.004 message.")

    operational = _child(report_or_error, "OprlErr")
    if operational is not None:
        code, description = _error(operational)
        return Camt004Response(**common, error_code=code, error_description=description)

    report = _child(report_or_error, "AcctRpt")
    if report is None:
        raise CamtParseError("Neither <AcctRpt> nor <OprlErr> in the camt.004 message.")
    business = _path(report, "AcctOrErr", "BizErr")
    if business is not None:
        code, description = _error(business)
        return Camt004Response(**common, error_code=code, error_description=description)
    account = _path(report, "AcctOrErr", "Acct")
    if account is None:
        raise CamtParseError("Neither <Acct> nor <BizErr> in the camt.004 account report.")

    account_id = _child(report, "AcctId")
    proxy = _child(account, "Prxy")
    proxy_iban = _text(_child(proxy, "Id")) if _choice(_child(proxy, "Tp")) == IBAN_PROXY else None
    currency = _text(_child(account, "Ccy"))
    owner = _child(account, "Ownr")
    limit = _path(account, "CurMulLmt", "Amt")
    limit_amount = _child(limit, "AmtWthCcy")
    if limit_amount is None:
        limit_amount = _child(limit, "AmtWthtCcy")

    return Camt004Response(
        **common,
        account=AccountReport(
            dean=_text(_path(account_id, "Othr", "Id")),
            iban=_text(_child(account_id, "IBAN")) or proxy_iban,
            currency=currency,
            status=_status(message),
            psp_bic=_text(_path(owner, "Id", "OrgId", "AnyBIC")),
            psp_name=_text(_child(owner, "Nm")),
            servicer_name=_text(_path(account, "Svcr", "FinInstnId", "Nm")),
            account_type=_choice(_child(account, "Tp")),
            balances=[_balance(b, currency or "") for b in _children(account, "MulBal")],
            hold_limit=_number(_text(limit_amount), "holding limit"),
            hold_limit_ccy=(limit_amount.get("Ccy") or currency) if limit_amount is not None else None,
        ),
    )


# ── Building ─────────────────────────────────────────────────────────────────

SUPPLEMENTARY_NAMESPACE = "urn:desp:supplementary"
ACCOUNT_PLACE = "/Document/RtrAcct/RptOrErr/AcctRpt/AcctOrErr/Acct"


def _amount(value: float) -> str:
    return f"{abs(value):.2f}"


def build_return_account_element(
    response: Camt004Response,
    *,
    account_scheme: str | None = "DEAN",
    error_account_id: str | None = None,
    original_message_name_id: str = "camt.003.001.08",
) -> etree._Element:
    """The `<Document>` tree of a camt.004 ReturnAccount message, the inverse of `parse_camt004`.

    With `response.account`, an account report: the account's DEAN (`Othr/Id`, its scheme
    named `account_scheme`) or else its IBAN, and its data; the IBAN next to the DEAN in
    the proxy, the status in the supplementary data (see the module docstring). Without
    one, an error: about the account `error_account_id` (a business error) or, if there
    is none, operational. `original_msg_id` names the camt.003 it answers
    (`original_message_name_id`); none, an unsolicited alert.
    """
    root = etree.Element("Document", nsmap={None: iso20022_namespace("camt.004", VARIANT)})
    message = sub(root, "RtrAcct")
    header = sub(message, "MsgHdr")
    sub(header, "MsgId", response.response_msg_id)
    sub(header, "CreDtTm", response.created_at)
    if response.original_msg_id:
        query = sub(header, "OrgnlBizQry")
        sub(query, "MsgId", response.original_msg_id)
        sub(query, "MsgNmId", original_message_name_id)

    report_or_error = sub(message, "RptOrErr")
    account = response.account
    if account is None and error_account_id is None:
        operational = sub(report_or_error, "OprlErr")
        sub(sub(operational, "Err"), "Prtry", response.error_code)
        if response.error_description:
            sub(operational, "Desc", response.error_description)
        return root

    report = sub(report_or_error, "AcctRpt")
    account_id = sub(report, "AcctId")
    dean = account.dean if account else error_account_id
    if dean:
        other = sub(account_id, "Othr")
        sub(other, "Id", dean)
        if account_scheme:
            sub(sub(other, "SchmeNm"), "Prtry", account_scheme)
    else:
        sub(account_id, "IBAN", account.iban)

    outcome = sub(report, "AcctOrErr")
    if account is None:
        business = sub(outcome, "BizErr")
        sub(sub(business, "Err"), "Prtry", response.error_code)
        if response.error_description:
            sub(business, "Desc", response.error_description)
        return root

    data = sub(outcome, "Acct")
    if account.account_type:
        sub(sub(data, "Tp"), "Prtry", account.account_type)
    if account.currency:
        sub(data, "Ccy", account.currency)
    if account.iban and dean:
        proxy = sub(data, "Prxy")
        sub(sub(proxy, "Tp"), "Prtry", IBAN_PROXY)
        sub(proxy, "Id", account.iban)
    if account.hold_limit is not None:
        limit = sub(data, "CurMulLmt")
        wrapper = sub(sub(limit, "Amt"), "AmtWthCcy", _amount(account.hold_limit))
        wrapper.set("Ccy", account.hold_limit_ccy or account.currency or "EUR")
        sub(limit, "CdtDbtInd", "CRDT")
    if account.psp_name or account.psp_bic:
        owner = sub(data, "Ownr")
        if account.psp_name:
            sub(owner, "Nm", account.psp_name)
        if account.psp_bic:
            sub(sub(sub(owner, "Id"), "OrgId"), "AnyBIC", account.psp_bic)
    if account.servicer_name:
        sub(sub(sub(data, "Svcr"), "FinInstnId"), "Nm", account.servicer_name)
    for balance in account.balances:
        entry = sub(data, "MulBal")
        sub(entry, "Amt", _amount(balance.amount))
        sub(entry, "CdtDbtInd", "DBIT" if balance.amount < 0 else "CRDT")
        if balance.type_code:
            sub(sub(entry, "Tp"), "Cd", balance.type_code)
        if balance.date:
            sub(sub(entry, "ValDt"), "Dt" if len(balance.date) == 10 else "DtTm", balance.date)

    if account.status:
        supplementary = sub(message, "SplmtryData")
        sub(supplementary, "PlcAndNm", ACCOUNT_PLACE)
        status = etree.SubElement(sub(supplementary, "Envlp"), f"{{{SUPPLEMENTARY_NAMESPACE}}}{ACCOUNT_STATUS}")
        status.text = account.status
    return root


def build_return_account_bytes(response: Camt004Response, *, pretty_print: bool = True, **options) -> bytes:
    """A camt.004 ReturnAccount message as XML bytes; `options` as `build_return_account_element`."""
    return etree.tostring(
        build_return_account_element(response, **options), xml_declaration=True, encoding="UTF-8",
        pretty_print=pretty_print)
