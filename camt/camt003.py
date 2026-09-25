"""Build ISO 20022 camt.003.001.02 (GetAccount) request documents.

The `camt.parser`/`camt.builder` pair only parses/builds camt.052/053/054
(bank-to-customer *reports*). camt.003 is the outbound *request* half of the
GetAccount flow ("ask the bank for an account's current state") — a different
shape with its own module here. Its counterpart camt.004 (see `camt.camt004`)
carries the response to that request, but can also arrive unsolicited as an
account alert; either way, it's built/parsed directly rather than through
that pair.
"""
from __future__ import annotations

from datetime import datetime

from lxml import etree

from .builder import sub
from .enums import iso20022_namespace


def build_get_account_request_element(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.02",
) -> etree._Element:
    """Build the `<Document>` tree for a camt.003 GetAccount request, querying one account's state.

    `id_type` selects how `account_id` is encoded in the search criterion: "IBAN"
    encodes it as `<IBAN>`; any other value encodes it as a proprietary identifier
    (`<Othr><Id>`) with `<SchmeNm><Prtry>` set to `id_type` (e.g. "DEAN").
    """
    namespace = iso20022_namespace("camt.003", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    get_acct = sub(root, "GetAcct")

    msg_hdr = sub(get_acct, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    new_crit = sub(sub(sub(get_acct, "AcctQryDef"), "AcctCrit"), "NewCrit")
    sch_crit = sub(new_crit, "SchCrit")
    id_elem = sub(sub(sub(sch_crit, "AcctId"), "EQ"), "Id")
    if id_type == "IBAN":
        sub(id_elem, "IBAN", account_id)
    else:
        othr = sub(id_elem, "Othr")
        sub(othr, "Id", account_id)
        sub(sub(othr, "SchmeNm"), "Prtry", id_type)

    return root


def build_get_account_request_bytes(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.02",
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.003 GetAccount request, to query an account's current state, as XML bytes."""
    root = build_get_account_request_element(
        account_id,
        msg_id,
        id_type=id_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_get_account_request_string(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    creation_datetime: datetime | None = None,
    schema_variant: str = "001.02",
    pretty_print: bool = True,
) -> str:
    """Build a camt.003 GetAccount request, to query an account's current state, as an XML string."""
    return build_get_account_request_bytes(
        account_id,
        msg_id,
        id_type=id_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")
