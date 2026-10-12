"""Build ISO 20022 camt.005.001.11 (GetTransaction) request documents.

Like camt.003 (see `camt.camt003`), this is the outbound *request* half of a
Get/Return pair -- its response counterpart is camt.006 (see `camt.camt006`)
-- so, like that pair, it's built here directly rather than through
`camt.builder`.

Unlike camt.003, camt.005 supports the ISO 20022 "delta" query pattern: a
first request registers its search criteria under a name (`NewQryNm`); any
later request can then reference that name alone (`QryNm`) instead of
repeating the criteria, asking the bank for only what changed -- new,
modified, or cancelled transactions -- since that named query was last
answered, rather than resending the whole result set every time.
`build_get_transaction_request_*` builds the first kind (optionally naming
itself for later delta follow-ups); `build_get_transaction_delta_request_*`
builds the second, its query type (`TxQryDef/QryTp`) saying which changes:
CHNG (all of them, the default), MODF (modified) or DELD (deleted).

The criteria go in `TxQryDef/TxCrit/NewCrit/SchCrit/AcctNtrySch`, the search
on the account's entries: the account (`AcctId/EQ`), the entry status
(`NtrySts`: BOOK, PDNG or FUTR) and the entry date-time window
(`NtryDt/DtTmSch`).
"""
from __future__ import annotations

from datetime import datetime

from lxml import etree

from .builder import sub
from .enums import iso20022_namespace
from .exceptions import CamtError

VARIANT = "001.11"
ENTRY_STATUSES = ("BOOK", "PDNG", "FUTR")  # EntryStatus1Code
QUERY_TYPES = ("ALLL", "CHNG", "MODF", "DELD")  # QueryType2Code


def _account_search_element(parent: etree._Element, account_id: str, id_type: str) -> None:
    id_elem = sub(sub(parent, "AcctId"), "EQ")
    if id_type == "IBAN":
        sub(id_elem, "IBAN", account_id)
    else:
        othr = sub(id_elem, "Othr")
        sub(othr, "Id", account_id)
        sub(sub(othr, "SchmeNm"), "Prtry", id_type)


def build_get_transaction_request_element(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    from_datetime: datetime | None = None,
    to_datetime: datetime | None = None,
    entry_status: str | None = None,
    new_query_name: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
) -> etree._Element:
    """Build the `<Document>` tree for a camt.005 GetTransaction request,
    querying one account's transactions.

    `id_type` selects how `account_id` is encoded, same as
    `camt.camt003.build_get_account_request_element`. `from_datetime`/
    `to_datetime` restrict the search to an entry date-time window; `entry_status`
    restricts it to one status ("BOOK", "PDNG" or "FUTR"; anything else raises
    `CamtError`).

    Pass `new_query_name` to register these criteria under that name, so a
    later `build_get_transaction_delta_request_element` call can ask for only
    what changed since this query was last answered instead of repeating the
    full criteria.
    """
    namespace = iso20022_namespace("camt.005", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    get_tx = sub(root, "GetTx")

    msg_hdr = sub(get_tx, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    new_crit = sub(sub(sub(get_tx, "TxQryDef"), "TxCrit"), "NewCrit")
    if new_query_name:
        sub(new_crit, "NewQryNm", new_query_name)

    search = sub(sub(new_crit, "SchCrit"), "AcctNtrySch")
    _account_search_element(search, account_id, id_type)

    if entry_status:
        if entry_status not in ENTRY_STATUSES:
            raise CamtError(f"The entry status must be one of {', '.join(ENTRY_STATUSES)}: {entry_status!r}")
        sub(search, "NtrySts", entry_status)

    if from_datetime or to_datetime:
        window = sub(sub(search, "NtryDt"), "DtTmSch")
        if from_datetime and to_datetime:
            period = sub(window, "DtTmRg")
            sub(period, "FrDtTm", from_datetime.isoformat())
            sub(period, "ToDtTm", to_datetime.isoformat())
        elif from_datetime:
            sub(window, "FrDtTm", from_datetime.isoformat())
        else:
            sub(window, "ToDtTm", to_datetime.isoformat())

    return root


def build_get_transaction_request_bytes(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    from_datetime: datetime | None = None,
    to_datetime: datetime | None = None,
    entry_status: str | None = None,
    new_query_name: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.005 GetTransaction request, to query an account's
    transactions, as XML bytes."""
    root = build_get_transaction_request_element(
        account_id,
        msg_id,
        id_type=id_type,
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        entry_status=entry_status,
        new_query_name=new_query_name,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_get_transaction_request_string(
    account_id: str,
    msg_id: str,
    *,
    id_type: str = "IBAN",
    from_datetime: datetime | None = None,
    to_datetime: datetime | None = None,
    entry_status: str | None = None,
    new_query_name: str | None = None,
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> str:
    """Build a camt.005 GetTransaction request, to query an account's
    transactions, as an XML string."""
    return build_get_transaction_request_bytes(
        account_id,
        msg_id,
        id_type=id_type,
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        entry_status=entry_status,
        new_query_name=new_query_name,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")


def build_get_transaction_delta_request_element(
    query_name: str,
    msg_id: str,
    *,
    query_type: str = "CHNG",
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
) -> etree._Element:
    """Build the `<Document>` tree for a camt.005 GetTransaction *delta*
    follow-up request.

    Instead of repeating search criteria, it references a query previously
    registered with `new_query_name` (see
    `build_get_transaction_request_element`) by name, asking the bank for
    only the transactions that changed since that named query was last
    answered: `query_type` CHNG (any change, the default), MODF (modified) or
    DELD (deleted); ALLL asks for them all again. Anything else raises
    `CamtError`.
    """
    if query_type not in QUERY_TYPES:
        raise CamtError(f"The query type must be one of {', '.join(QUERY_TYPES)}: {query_type!r}")
    namespace = iso20022_namespace("camt.005", schema_variant)
    root = etree.Element("Document", nsmap={None: namespace})
    get_tx = sub(root, "GetTx")

    msg_hdr = sub(get_tx, "MsgHdr")
    sub(msg_hdr, "MsgId", msg_id)
    sub(msg_hdr, "CreDtTm", (creation_datetime or datetime.now()).isoformat())

    query = sub(get_tx, "TxQryDef")
    sub(query, "QryTp", query_type)
    sub(sub(query, "TxCrit"), "QryNm", query_name)

    return root


def build_get_transaction_delta_request_bytes(
    query_name: str,
    msg_id: str,
    *,
    query_type: str = "CHNG",
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> bytes:
    """Build a camt.005 GetTransaction delta follow-up request, asking for
    only what changed since `query_name` was last answered, as XML bytes."""
    root = build_get_transaction_delta_request_element(
        query_name,
        msg_id,
        query_type=query_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
    )
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=pretty_print
    )


def build_get_transaction_delta_request_string(
    query_name: str,
    msg_id: str,
    *,
    query_type: str = "CHNG",
    creation_datetime: datetime | None = None,
    schema_variant: str = VARIANT,
    pretty_print: bool = True,
) -> str:
    """Build a camt.005 GetTransaction delta follow-up request, asking for
    only what changed since `query_name` was last answered, as an XML
    string."""
    return build_get_transaction_delta_request_bytes(
        query_name,
        msg_id,
        query_type=query_type,
        creation_datetime=creation_datetime,
        schema_variant=schema_variant,
        pretty_print=pretty_print,
    ).decode("utf-8")
