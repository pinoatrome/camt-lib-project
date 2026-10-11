"""What the recall messages share: the case assignment (who asks whom, about
which case), references to the original payment, reasons, and their checks.

camt.056 (`camt.camt056`) asks for a payment back; camt.029 (`camt.camt029`)
answers. Both open with an `Assgnmt` (CaseAssignment5): an id, the assigner
(the agent sending the message), the assignee (the agent it's sent to) and a
creation time; agents are identified by BIC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lxml import etree

from .builder import sub
from .exceptions import CamtError, CamtParseError
from .parser import _child, _children, _decimal, _parse_datetime, _path, _text

MAX_35 = 35  # Max35Text: the ids
MAX_105 = 105  # Max105Text: one AddtlInf line
_BIC = re.compile(r"^[A-Z0-9]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_CODE = re.compile(r"^[A-Z0-9]{1,4}$")


@dataclass
class CaseAssignment:
    """`Assgnmt`: the message's id, who sends it (assigner) to whom (assignee), and when."""

    id: str
    assigner_bic: str
    assignee_bic: str
    creation_datetime: datetime


# ── Checks ───────────────────────────────────────────────────────────────────


def check_id(name: str, value: str | None, *, required: bool = True) -> None:
    if value is None and not required:
        return
    if not value or len(value) > MAX_35:
        raise CamtError(f"{name} must be 1 to {MAX_35} characters: {value!r}")


def check_bic(name: str, value: str) -> None:
    if not _BIC.match(value or ""):
        raise CamtError(f"{name} must be a BIC (8 or 11 characters): {value!r}")


def check_code(name: str, value: str | None) -> None:
    if not _CODE.match(value or ""):
        raise CamtError(f"{name} must be a code of 1 to 4 letters or digits: {value!r}")


def check_info(value: str | None) -> None:
    if value is not None and len(value) > MAX_105:
        raise CamtError(f"Additional information is over {MAX_105} characters.")


def check_amount(name: str, value: Decimal | None, currency: str) -> None:
    if value is None:
        return
    if value <= 0 or value != value.quantize(Decimal("0.01")):
        raise CamtError(f"{name} must be positive, with at most 2 decimals: {value}")
    if len(currency or "") != 3:
        raise CamtError(f"Currency must be a 3-letter code: {currency!r}")


def check_assignment(assignment: CaseAssignment) -> None:
    check_id("The assignment id", assignment.id)
    check_bic("The assigner", assignment.assigner_bic)
    check_bic("The assignee", assignment.assignee_bic)


# ── Building ─────────────────────────────────────────────────────────────────


def agent(parent: etree._Element, tag: str, bic: str) -> None:
    """`<tag><Agt><FinInstnId><BICFI>` (a Party40Choice naming an agent)."""
    sub(sub(sub(sub(parent, tag), "Agt"), "FinInstnId"), "BICFI", bic)


def build_assignment(parent: etree._Element, assignment: CaseAssignment) -> None:
    element = sub(parent, "Assgnmt")
    sub(element, "Id", assignment.id)
    agent(element, "Assgnr", assignment.assigner_bic)
    agent(element, "Assgne", assignment.assignee_bic)
    sub(element, "CreDtTm", assignment.creation_datetime.isoformat(timespec="seconds"))


def build_original_references(
    parent: etree._Element,
    *,
    message_id: str,
    message_name_id: str,
    instruction_id: str | None,
    end_to_end_id: str,
    transaction_id: str | None,
) -> None:
    """`OrgnlGrpInf` (the original message), then the original payment's ids."""
    group = sub(parent, "OrgnlGrpInf")
    sub(group, "OrgnlMsgId", message_id)
    sub(group, "OrgnlMsgNmId", message_name_id)
    if instruction_id:
        sub(parent, "OrgnlInstrId", instruction_id)
    sub(parent, "OrgnlEndToEndId", end_to_end_id)
    if transaction_id:
        sub(parent, "OrgnlTxId", transaction_id)


def build_amount(parent: etree._Element, tag: str, amount: Decimal | None, currency: str) -> None:
    if amount is not None:
        sub(parent, tag, f"{amount:.2f}").set("Ccy", currency)


def build_reason(parent: etree._Element, tag: str, code: str | None, additional_info: str | None) -> None:
    """`<tag><Rsn><Cd>` and its `AddtlInf`, when there's either."""
    if code is None and additional_info is None:
        return
    reason = sub(parent, tag)
    if code:
        sub(sub(reason, "Rsn"), "Cd", code)
    if additional_info:
        sub(reason, "AddtlInf", additional_info)


# ── Parsing (by local name, so any version of the message reads) ─────────────


def read_root(data: bytes, message: str, wrapper: str) -> etree._Element:
    """The message wrapper (e.g. FIToFIPmtCxlReq) of a `Document` of `message` in any version."""
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        raise CamtParseError(f"Malformed XML: {exc}") from exc
    namespace = etree.QName(root).namespace or ""
    if etree.QName(root).localname != "Document" or f":{message}." not in namespace:
        raise CamtParseError(f"Not a {message} Document (root {root.tag}).")
    element = _child(root, wrapper)
    if element is None:
        raise CamtParseError(f"No <{wrapper}> in the {message} Document.")
    return element


def required(element: etree._Element | None, *names: str) -> str:
    value = _text(_path(element, *names))
    if value is None:
        raise CamtParseError(f"Missing {'/'.join(names)}.")
    return value


def read_assignment(wrapper: etree._Element) -> CaseAssignment:
    assignment = _child(wrapper, "Assgnmt")
    if assignment is None:
        raise CamtParseError("Missing Assgnmt.")
    created = _parse_datetime(required(assignment, "CreDtTm"))
    if created is None:
        raise CamtParseError("Invalid Assgnmt/CreDtTm.")
    return CaseAssignment(
        id=required(assignment, "Id"),
        assigner_bic=required(assignment, "Assgnr", "Agt", "FinInstnId", "BICFI"),
        assignee_bic=required(assignment, "Assgne", "Agt", "FinInstnId", "BICFI"),
        creation_datetime=created,
    )


def read_amount(element: etree._Element, tag: str) -> tuple[Decimal | None, str | None]:
    amount = _child(element, tag)
    if amount is None:
        return None, None
    value = _decimal(_text(amount))
    if value is None:
        raise CamtParseError(f"Invalid {tag}: {_text(amount)!r}")
    return value, amount.get("Ccy")


def read_reason(element: etree._Element | None) -> tuple[str | None, str | None]:
    """The reason code (or proprietary reason) and the AddtlInf lines, joined by a space."""
    if element is None:
        return None, None
    lines = [_text(line) for line in _children(element, "AddtlInf")]
    code = _text(_path(element, "Rsn", "Cd")) or _text(_path(element, "Rsn", "Prtry"))
    return code, " ".join(line for line in lines if line) or None
