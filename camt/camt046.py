"""Build ISO 20022 camt.046.001.08 (GetReservation) request documents.

Like camt.003 (see `camt.camt003`), this is the outbound *request* half of a
Get/Return pair -- its response counterpart is camt.047 (see `camt.camt047`)
-- so, like that pair, it's built here directly rather than through
`camt.builder`.

A reservation query asks for the amounts an account has set aside against a
specific purpose (e.g. a minimum reserve requirement, a standing facility),
as opposed to camt.003/004 which reports the account's overall balance. Used
to check how much of an account's balance is earmarked and unavailable for
ordinary payments.

The query is `RsvatnQryDef/RsvatnCrit/NewCrit/SchCrit`: the reservation type
(`CurRsvatnTp`), when given, and the account (`AcctId`).
"""
from __future__ import annotations

from datetime import datetime

from lxml import etree

from ._reservation import build_account_id, build_reservation_type
from .builder import sub
from .enums import iso20022_namespace

VARIANT = "001.08"


def build_get_reservation_request_element(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    reservation_type: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
) -> etree._Element:
    """Build the `<Document>` tree for a camt.046 GetReservation request,
    querying one account's reservations.

    `id_type` selects how `account_id` is encoded, same as
    `camt.camt003.build_get_account_request_element`. `reservation_type`
    restricts the search to one reservation type code (e.g. "MMR" for a
    minimum reserve requirement, as `Cd`; a longer one as `Prtry`); omitted, all reservation types are
    returned.
    """
    namespace = iso20022_namespace("camt.046", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    get_rsvatn = sub(root, "GetRsvatn")

    msg_hdr = sub(get_rsvatn, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    sch_crit = sub(
        sub(sub(sub(get_rsvatn, "RsvatnQryDef"), "RsvatnCrit"), "NewCrit"),
        "SchCrit",
    )
    if reservation_type:
        build_reservation_type(sch_crit, "CurRsvatnTp", reservation_type)
    build_account_id(sch_crit, account_id, id_type)

    return root


def build_get_reservation_request_bytes(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    reservation_type: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.046 GetReservation request, to query an account's
    reservations, as XML bytes."""
    root = build_get_reservation_request_element(
        account_id,
        msg_id,
        id_type=id_type,
        reservation_type=reservation_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_get_reservation_request_string(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    reservation_type: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> str:
    """Build a camt.046 GetReservation request, to query an account's
    reservations, as an XML string."""
    return build_get_reservation_request_bytes(
        account_id,
        msg_id,
        id_type=id_type,
        reservation_type=reservation_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")
