"""Check a camt document against ISO 20022's schemas (the XSDs in `camt/xsd/`).

The schemas are the Cash Management message set of the catalogue, 2025/2026
edition: the newest version of each family the library handles (camt.003.001.08,
camt.004.001.10, camt.005.001.11, camt.006.001.11, camt.018.001.05, camt.019.001.07,
camt.025.001.09, camt.029.001.14, camt.046.001.08, camt.047.001.08, camt.048.001.07,
camt.049.001.07, camt.050.001.07, camt.052/.053/.054.001.14, camt.056.001.12).
The library builds every message in that version, so a document is checked against
the schema of its own version; the parsers read older versions too, but those aren't
checked (`schema_errors` says there's no schema for them).
"""
from __future__ import annotations

from functools import cache
from pathlib import Path

from lxml import etree

from .exceptions import CamtError

SCHEMAS = Path(__file__).parent / "xsd"

# The version each family is checked in: "camt.053" -> "camt.053.001.14".
NEWEST = {path.stem[:8]: path.stem for path in SCHEMAS.glob("camt.*.xsd")}


class CamtValidationError(CamtError):
    """A document isn't valid against its schema; `errors` are the schema's findings."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Not valid ISO 20022: " + "; ".join(errors[:3]) + (" ..." if len(errors) > 3 else ""))


@cache
def _schema(version: str) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMAS / f"{version}.xsd")))


def schema_errors(xml: bytes) -> list[str]:
    """What the schema of `xml`'s own version finds wrong in it; empty when it's valid.

    A document that isn't XML, isn't a camt message, or is in a version other than
    the one the library checks, is one error.
    """
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        return [f"not XML: {exc}"]
    namespace = etree.QName(root).namespace or ""
    if not namespace.startswith("urn:iso:std:iso:20022:tech:xsd:camt."):
        return [f"not a camt message: namespace {namespace!r}"]
    version = namespace.rsplit(":", 1)[1]
    if NEWEST.get(version[:8]) != version:
        known = NEWEST.get(version[:8])
        return [f"no schema for {version}" + (f": the library checks {known}" if known else "")]
    checker = _schema(version)
    if checker.validate(root):
        return []
    return [error.message for error in checker.error_log]


def validate(xml: bytes) -> bytes:
    """`xml`, if it's valid against its schema; raises `CamtValidationError` if not."""
    errors = schema_errors(xml)
    if errors:
        raise CamtValidationError(errors)
    return xml
