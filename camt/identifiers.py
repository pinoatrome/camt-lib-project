"""Telling the account identifiers apart: an IBAN, or a digital euro account number (DEAN).

A DEAN (digital euro scheme rulebook v0.9, FUR.07) is `EU`, two check digits and the 14-digit
BEAN: shaped like an IBAN, so it's recognised first and never written as one."""
import re

DEAN = re.compile(r"^EU\d{16}$")


def is_dean(account_id: str) -> bool:
    return bool(DEAN.match(account_id))


def is_iban(account_id: str) -> bool:
    """Two letters and two digits first, at most 34 characters, and not a DEAN."""
    return (len(account_id) <= 34 and account_id[:2].isalpha() and account_id[2:4].isdigit()
            and not is_dean(account_id))
