"""Parse ISO 20022 camt.025 (Receipt) messages.

camt.025 is the synchronous response to a camt.050 LiquidityCreditTransfer
request (see `camt.camt050`) — settled, pending, or rejected — so, like that
request, it's parsed here directly rather than through `camt.parser`.

A receipt is `Rct`: a `MsgHdr`, then `RctDtls` with the request it answers
(`OrgnlMsgId/MsgId`) and how it was handled (`ReqHdlg`: the status code
`Sts/Cd`, and for a rejection the reason `StsRsn/Rsn/Cd` with its `AddtlInf`).
Parsing matches elements by local name, so any camt.025 version reads; the
library's checks use .001.09, the newest.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._investigation import read_root
from .exceptions import CamtParseError
from .parser import _child, _children, _path, _text

SETTLED = "STLD"
PENDING = "PDNG"
REJECTED = "RJCT"


@dataclass
class ReceiptResult:
    """Parsed camt.025 Receipt for a camt.050 LiquidityCreditTransfer."""

    receipt_msg_id: str | None
    created_at: str | None
    status: str  # STLD | PDNG | RJCT | UNKN
    original_msg_id: str | None = None
    original_e2e_id: str | None = None
    reject_code: str | None = None
    reject_desc: str | None = None


def parse_camt025(xml_bytes: bytes) -> ReceiptResult:
    """Parse a camt.025 Receipt (any version) into a `ReceiptResult`, from its first
    `RctDtls` and that one's first `ReqHdlg`:

      `Sts/Cd` STLD -> settled
      `Sts/Cd` PDNG -> pending/queued
      `Sts/Cd` RJCT -> rejected, with `StsRsn/Rsn/Cd` and its `AddtlInf` lines (or `Desc`)

    `original_e2e_id` is the `OrgnlPmtId/LngBizId/EndToEndId`, when the receipt has one.
    Raises `CamtParseError` if it isn't a readable camt.025 receipt.
    """
    receipt = read_root(xml_bytes, "camt.025", "Rct")
    header = _child(receipt, "MsgHdr")
    details = _child(receipt, "RctDtls")
    if details is None:
        raise CamtParseError("No <RctDtls> in the camt.025 receipt.")
    handling = _child(details, "ReqHdlg")
    reason = _child(handling, "StsRsn")
    lines = [_text(line) for line in _children(reason, "AddtlInf")]
    return ReceiptResult(
        receipt_msg_id=_text(_child(header, "MsgId")),
        created_at=_text(_child(header, "CreDtTm")),
        status=_text(_path(handling, "Sts", "Cd")) or _text(_path(handling, "Sts", "Prtry")) or "UNKN",
        original_msg_id=_text(_path(details, "OrgnlMsgId", "MsgId")),
        original_e2e_id=_text(_path(details, "OrgnlPmtId", "LngBizId", "EndToEndId")),
        reject_code=_text(_path(reason, "Rsn", "Cd")) or _text(_path(reason, "Rsn", "Prtry")),
        reject_desc=" ".join(line for line in lines if line) or _text(_child(handling, "Desc")),
    )
