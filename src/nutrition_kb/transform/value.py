"""Parsing d'une cellule brute food_value en (valeur, statut, provenance)."""

from enum import Enum
from typing import NamedTuple


class ValueStatus(Enum):
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    TRACE = "TRACE"
    NOT_DETERMINED = "NOT_DETERMINED"


class Provenance(Enum):
    AFRICAN = "AFRICAN"
    NON_AFRICAN = "NON_AFRICAN"


class ParsedValue(NamedTuple):
    value: float | None
    status: ValueStatus
    provenance: Provenance


_TRACE_TOKENS = {"tr", "trace"}


def parse_value(raw: str | None, is_oa: bool) -> ParsedValue:
    provenance = Provenance.NON_AFRICAN if is_oa else Provenance.AFRICAN

    if raw is None or raw.strip() == "":
        return ParsedValue(None, ValueStatus.NOT_DETERMINED, provenance)

    text = raw.strip()

    if text.lower() in _TRACE_TOKENS:
        return ParsedValue(None, ValueStatus.TRACE, provenance)

    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        try:
            return ParsedValue(float(inner), ValueStatus.ESTIMATED, provenance)
        except ValueError:
            raise ValueError(f"Valeur estimee illisible : {raw!r}") from None

    try:
        return ParsedValue(float(text), ValueStatus.MEASURED, provenance)
    except ValueError:
        raise ValueError(f"Valeur illisible : {raw!r}") from None
