"""Parse ISO 20022 camt.025.001.05 (Receipt) messages.

camt.025 is the synchronous response to a camt.050 LiquidityCreditTransfer
request (see `camt.camt050`) — settled, pending, or rejected — so, like that
request, it's parsed here directly rather than through `camt.parser`.
"""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from .enums import iso20022_namespace

_NAMESPACE = iso20022_namespace("camt.025", "001.05")
_NS_PREFIX = f"{{{_NAMESPACE}}}"


@dataclass
class ReceiptResult:
    """Parsed camt.025.001.05 Receipt for a camt.050 LiquidityCreditTransfer."""

    receipt_msg_id: str | None
    created_at: str | None
    status: str  # STLD | PDNG | RJCT | UNKN
    original_msg_id: str | None = None
    original_e2e_id: str | None = None
    reject_code: str | None = None
    reject_desc: str | None = None


def _tag(name: str) -> str:
    return f"{_NS_PREFIX}{name}"


def _text(el: etree._Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text if found is not None else None


def parse_camt025(xml_bytes: bytes) -> ReceiptResult:
    """Parse a camt.025.001.05 Receipt into a `ReceiptResult`.

    Three outcome paths:
      `<RctDtls>` with status code STLD -> settled
      `<RctDtls>` with status code PDNG -> pending/queued
      `<ReqRjctd>`                      -> rejected, with a reason code/description
    """
    root = etree.fromstring(xml_bytes)
    rcpt = root.find(_tag("Receipt"))
    if rcpt is None:
        raise ValueError("<Receipt> root element not found in camt.025")

    hdr = rcpt.find(_tag("MsgHdr"))
    receipt_msg_id = _text(hdr, _tag("MsgId"))
    created_at = _text(hdr, _tag("CreDtTm"))

    rjctd = rcpt.find(_tag("ReqRjctd"))
    if rjctd is not None:
        return ReceiptResult(
            receipt_msg_id=receipt_msg_id,
            created_at=created_at,
            status="RJCT",
            original_msg_id=_text(rjctd, _tag("RjctdReqRef")),
            reject_code=_text(rjctd, f"{_tag('StsRsn')}/{_tag('Cd')}"),
            reject_desc=_text(rjctd, f"{_tag('StsRsn')}/{_tag('AddtlInf')}"),
        )

    rct_dtls = rcpt.find(_tag("RctDtls"))
    if rct_dtls is None:
        raise ValueError("Neither <RctDtls> nor <ReqRjctd> found in camt.025")

    orig_instr = rct_dtls.find(_tag("OrgnlBizInstr"))
    return ReceiptResult(
        receipt_msg_id=receipt_msg_id,
        created_at=created_at,
        status=_text(rct_dtls, f"{_tag('ReqHdlg')}/{_tag('StsRsn')}/{_tag('Cd')}") or "UNKN",
        original_msg_id=_text(orig_instr, _tag("MsgId")),
        original_e2e_id=_text(rct_dtls, _tag("OrgnlEndToEndId")),
    )
