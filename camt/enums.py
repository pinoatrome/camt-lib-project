from enum import Enum


class MessageType(str, Enum):
    """Supported ISO 20022 CAMT message families."""

    CAMT_052 = "camt.052"  # Bank-to-Customer Account Report (intraday)
    CAMT_053 = "camt.053"  # Bank-to-Customer Statement
    CAMT_054 = "camt.054"  # Bank-to-Customer Debit/Credit Notification

    @property
    def group_wrapper_tag(self) -> str:
        return {
            MessageType.CAMT_052: "BkToCstmrAcctRpt",
            MessageType.CAMT_053: "BkToCstmrStmt",
            MessageType.CAMT_054: "BkToCstmrDbtCdtNtfctn",
        }[self]

    @property
    def entry_group_tag(self) -> str:
        """The repeated element that holds one statement/report/notification."""
        return {
            MessageType.CAMT_052: "Rpt",
            MessageType.CAMT_053: "Stmt",
            MessageType.CAMT_054: "Ntfctn",
        }[self]


class CreditDebit(str, Enum):
    CREDIT = "CRDT"
    DEBIT = "DBIT"


class EntryStatus(str, Enum):
    BOOKED = "BOOK"
    PENDING = "PDNG"
    INFO = "INFO"
