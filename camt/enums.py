from enum import Enum


def iso20022_namespace(message_family: str, variant: str = "001.02") -> str:
    """Build the ISO 20022 XML namespace URI for a message family (e.g. "camt.053") and schema variant."""
    return f"urn:iso:std:iso:20022:tech:xsd:{message_family}.{variant}"


class MessageType(str, Enum):
    """Supported ISO 20022 CAMT message families."""

    CAMT_052 = "camt.052"  # Bank-to-Customer Account Report (intraday)
    CAMT_053 = "camt.053"  # Bank-to-Customer Statement
    CAMT_054 = "camt.054"  # Bank-to-Customer Debit/Credit Notification

    @property
    def namespace(self) -> str:
        return iso20022_namespace(self.value)

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
