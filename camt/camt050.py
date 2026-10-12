"""Build ISO 20022 camt.050.001.07 (LiquidityCreditTransfer) request documents.

Like camt.003/camt.004 (see `camt.camt003`, `camt.camt004`), this moves
liquidity between two accounts (e.g. a PSP's MCA and its DESP DCA) rather than
reporting on one, and it's paired with a camt.025 Receipt response (see
`camt.camt025`) instead of another report message — so, like the GetAccount
pair, it's built here directly rather than through `camt.builder`.

The document is `LqdtyCdtTrf` with a `MsgHdr` and one `LqdtyCdtTrf`: the
transfer's id (`LqdtyTrfId/EndToEndId`), the creditor and its account, the
amount (`TrfdAmt/AmtWthCcy`), then the debtor and its account.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from lxml import etree

from .builder import sub
from .enums import iso20022_namespace
from .exceptions import CamtError

VARIANT = "001.07"
_NAMESPACE = iso20022_namespace("camt.050", VARIANT)
_BIC = re.compile(r"^[A-Z0-9]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")


def _is_iban(account_id: str) -> bool:
    return len(account_id) <= 34 and account_id[:2].isalpha() and account_id[2:4].isdigit()


def _account_element(parent: etree._Element, tag: str, account_id: str) -> None:
    id_elem = sub(sub(parent, tag), "Id")
    if _is_iban(account_id):
        sub(id_elem, "IBAN", account_id)
    else:
        sub(sub(id_elem, "Othr"), "Id", account_id)


def _agent_element(parent: etree._Element, tag: str, agent_id: str) -> None:
    """The agent by its BIC (`FinInstnId/BICFI`) when it is one, else `FinInstnId/Othr/Id`."""
    fin_instn_id = sub(sub(parent, tag), "FinInstnId")
    if _BIC.match(agent_id):
        sub(fin_instn_id, "BICFI", agent_id)
    else:
        sub(sub(fin_instn_id, "Othr"), "Id", agent_id)


def build_liquidity_transfer_element(
    debtor_account_id: str,
    creditor_account_id: str,
    amount: float,
    currency: str = "EUR",
    *,
    debtor_agent_id: str = "SELF",
    creditor_agent_id: str = "DESP",
    msg_id: str | None = None,
    end_to_end_id: str | None = None,
    creation_datetime: datetime | None = None,
) -> etree._Element:
    """Build the `<Document>` tree for a camt.050 LiquidityCreditTransfer request,
    moving `amount` `currency` from `debtor_account_id` to `creditor_account_id`.

    Each account ID is encoded as `<IBAN>` when it looks like one (two letters
    followed by two digits), otherwise as a proprietary `<Othr><Id>`; each agent
    as `<BICFI>` when it's a BIC, otherwise as `<Othr><Id>`. Raises `CamtError`
    for an amount that isn't positive.
    """
    if amount <= 0:
        raise CamtError(f"The transferred amount must be positive: {amount}")
    msg_id = msg_id or f"LT-{uuid.uuid4().hex[:16].upper()}"
    end_to_end_id = end_to_end_id or f"E2E-{uuid.uuid4().hex[:16].upper()}"

    root = etree.Element("Document", nsmap={None: _NAMESPACE})
    message = sub(root, "LqdtyCdtTrf")

    msg_hdr = sub(message, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    transfer = sub(message, "LqdtyCdtTrf")
    sub(sub(transfer, "LqdtyTrfId"), "EndToEndId", end_to_end_id)
    _agent_element(transfer, "Cdtr", creditor_agent_id)
    _account_element(transfer, "CdtrAcct", creditor_account_id)
    sub(sub(transfer, "TrfdAmt"), "AmtWthCcy", f"{amount:.2f}").set("Ccy", currency)
    _agent_element(transfer, "Dbtr", debtor_agent_id)
    _account_element(transfer, "DbtrAcct", debtor_account_id)

    return root


def build_liquidity_transfer_bytes(
    debtor_account_id: str,
    creditor_account_id: str,
    amount: float,
    currency: str = "EUR",
    *,
    debtor_agent_id: str = "SELF",
    creditor_agent_id: str = "DESP",
    msg_id: str | None = None,
    end_to_end_id: str | None = None,
    creation_datetime: datetime | None = None,
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.050 LiquidityCreditTransfer request as XML bytes."""
    root = build_liquidity_transfer_element(
        debtor_account_id,
        creditor_account_id,
        amount,
        currency,
        debtor_agent_id=debtor_agent_id,
        creditor_agent_id=creditor_agent_id,
        msg_id=msg_id,
        end_to_end_id=end_to_end_id,
        creation_datetime=creation_datetime,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_liquidity_transfer_string(
    debtor_account_id: str,
    creditor_account_id: str,
    amount: float,
    currency: str = "EUR",
    *,
    debtor_agent_id: str = "SELF",
    creditor_agent_id: str = "DESP",
    msg_id: str | None = None,
    end_to_end_id: str | None = None,
    creation_datetime: datetime | None = None,
    pretty_print: bool = True,
) -> str:
    """Build a camt.050 LiquidityCreditTransfer request as an XML string."""
    return build_liquidity_transfer_bytes(
        debtor_account_id,
        creditor_account_id,
        amount,
        currency,
        debtor_agent_id=debtor_agent_id,
        creditor_agent_id=creditor_agent_id,
        msg_id=msg_id,
        end_to_end_id=end_to_end_id,
        creation_datetime=creation_datetime,
        pretty_print=pretty_print,
    ).decode("utf-8")
