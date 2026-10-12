"""What the reservation messages share: the account and the reservation type.

camt.046 (`camt.camt046`) queries reservations, camt.047 (`camt.camt047`)
answers; camt.048 (`camt.camt048`) changes one and camt.049 (`camt.camt049`)
deletes one, both answered by a camt.025 Receipt. A reservation is named by its
type (`Tp`, a ReservationType2Choice) and the account it's held on (`AcctId`).
"""
from __future__ import annotations

import re

from lxml import etree

from .builder import sub

_CODE = re.compile(r"^[A-Z0-9]{1,4}$")


def build_account_id(parent: etree._Element, account_id: str, id_type: str) -> None:
    """`<AcctId>` (AccountIdentification4Choice): `IBAN` for `id_type` "IBAN", else
    `Othr/Id` with `id_type` as its proprietary scheme name (e.g. "DEAN")."""
    acct_id = sub(parent, "AcctId")
    if id_type == "IBAN":
        sub(acct_id, "IBAN", account_id)
    else:
        othr = sub(acct_id, "Othr")
        sub(othr, "Id", account_id)
        sub(sub(othr, "SchmeNm"), "Prtry", id_type)


def build_reservation_type(parent: etree._Element, tag: str, reservation_type: str) -> None:
    """`<tag>` (ReservationType2Choice): `Cd` for an external code (at most 4
    letters or digits, e.g. "UPAR", "MMR"), else `Prtry`."""
    choice = sub(parent, tag)
    sub(choice, "Cd" if _CODE.match(reservation_type) else "Prtry", reservation_type)


def build_reservation_id(
    parent: etree._Element, tag: str, account_id: str, reservation_type: str, id_type: str
) -> None:
    """`<tag>` (ReservationIdentification4): the reservation's type and its account."""
    reservation = sub(parent, tag)
    build_reservation_type(reservation, "Tp", reservation_type)
    build_account_id(reservation, account_id, id_type)
