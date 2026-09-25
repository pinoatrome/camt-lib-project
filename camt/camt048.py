"""Build ISO 20022 camt.048.001.05 (ModifyReservation) request documents.

Like camt.050 (see `camt.camt050`), this is an outbound *instruction* rather
than a Get/Return query -- it changes the amount of a reservation already
held against an account (see `camt.camt046`/`camt.camt047` for querying
existing reservations) instead of asking for its current state. Like
camt.050, its synchronous response is a camt.025 Receipt (see
`camt.camt025`), so it's built here directly rather than through
`camt.builder`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from lxml import etree

from .builder import sub
from .enums import iso20022_namespace


def _account_element(parent: etree._Element, account_id: str, id_type: str) -> None:
    id_elem = sub(parent, "Id")
    if id_type == "IBAN":
        sub(id_elem, "IBAN", account_id)
    else:
        othr = sub(id_elem, "Othr")
        sub(othr, "Id", account_id)
        sub(sub(othr, "SchmeNm"), "Prtry", id_type)


def build_modify_reservation_request_element(
    account_id: str,
    reservation_type: str,
    new_amount: float,
    currency: str = "EUR",
    *,
    id_type: str = "IBAN",
    msg_id: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.05",
) -> etree._Element:
    """Build the `<Document>` tree for a camt.048 ModifyReservation request,
    changing the amount of one account's `reservation_type` reservation
    (e.g. "MMR" for a minimum reserve requirement) to `new_amount`.

    `id_type` selects how `account_id` is encoded, same as
    `camt.camt003.build_get_account_request_element`.
    """
    msg_id = msg_id or f"MODRSV-{uuid.uuid4().hex[:16].upper()}"
    created_at = (creation_datetime or datetime.now()).isoformat()

    namespace = iso20022_namespace("camt.048", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    modfy_rsvatn = sub(root, "ModfyRsvatn")

    msg_hdr = sub(modfy_rsvatn, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", created_at)

    instr = sub(modfy_rsvatn, "RsvatnModfyInstr")
    sub(instr, "MsgId", msg_id)
    sub(instr, "CreDtTm", created_at)

    _account_element(sub(instr, "AcctId"), account_id, id_type)
    sub(sub(instr, "RsvatnTp"), "Cd", reservation_type)

    new_amt = sub(instr, "NewRsvatnAmt", f"{new_amount:.2f}")
    new_amt.set("Ccy", currency)

    return root


def build_modify_reservation_request_bytes(
    account_id: str,
    reservation_type: str,
    new_amount: float,
    currency: str = "EUR",
    *,
    id_type: str = "IBAN",
    msg_id: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.05",
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.048 ModifyReservation request as XML bytes."""
    root = build_modify_reservation_request_element(
        account_id,
        reservation_type,
        new_amount,
        currency,
        id_type=id_type,
        msg_id=msg_id,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_modify_reservation_request_string(
    account_id: str,
    reservation_type: str,
    new_amount: float,
    currency: str = "EUR",
    *,
    id_type: str = "IBAN",
    msg_id: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.05",
    pretty_print: bool = True,
) -> str:
    """Build a camt.048 ModifyReservation request as an XML string."""
    return build_modify_reservation_request_bytes(
        account_id,
        reservation_type,
        new_amount,
        currency,
        id_type=id_type,
        msg_id=msg_id,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")
