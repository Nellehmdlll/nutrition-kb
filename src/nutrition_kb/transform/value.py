"""Parsing d'une cellule brute WAFCT en (valeur, statut, provenance).

Deux axes ORTHOGONAUX, volontairement séparés :

  - ValueStatus  : ce qu'on sait de la VALEUR    (mesurée / estimée / trace / non déterminée)
  - Provenance   : d'où vient l'ÉCHANTILLON      (africain / non africain / inconnu)

Une cellule peut être MEASURED + NON_AFRICAN, ou ESTIMATED + AFRICAN, etc.
Les deux dimensions ne se déduisent pas l'une de l'autre : elles cohabitent.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class ValueStatus(Enum):
    """Ce que l'on sait de la valeur elle-même. Exclusif : un seul statut à la fois."""

    MEASURED = "MEASURED"              # nombre nu     -> ex. "1.00"
    ESTIMATED = "ESTIMATED"            # entre [...]   -> ex. "[0.2]"  (empruntée / calculée)
    TRACE = "TRACE"                    # "tr" / "[tr]" -> présent, mais NON QUANTIFIÉ
    NOT_DETERMINED = "NOT_DETERMINED"  # cellule vide  -> jamais mesuré


class Provenance(Enum):
    """D'où vient l'échantillon ayant servi à la compilation FAO."""

    AFRICAN = "AFRICAN"          # l'aliment a une ligne "Non-African data", la cellule N'EST PAS marquée
    NON_AFRICAN = "NON_AFRICAN"  # la cellule est marquée "oa" (originating abroad)
    UNKNOWN = "UNKNOWN"          # l'aliment n'a AUCUNE ligne "Non-African data" -> on ne sait pas
    # CORRECTION (bug 2) : UNKNOWN est INDISPENSABLE.
    # 539 aliments sur 1028 (dont 91 des 116 aliments burkinabè) n'ont aucune
    # ligne de provenance. Les déclarer AFRICAN serait AFFIRMER SANS PREUVE.
    # L'absence de preuve n'est pas la preuve de l'absence.
    #
    # TODO : ces aliments sont massivement des plats composés (nom suffixé d'un "*").
    # Hypothèse : leurs valeurs sont CALCULÉES depuis la recette (feuille 09 Mixed dishes),
    # et non mesurées. À confirmer dans le User Guide FAO (lien en feuille 01) avant
    # d'introduire un éventuel statut CALCULATED. On ne code pas sur une hypothèse.


class ParsedValue(NamedTuple):
    value: float | None
    status: ValueStatus
    provenance: Provenance


# Grammaire de la cellule WAFCT :
#
#     cellule  := vide | '[' atome ']' | atome
#     atome    := nombre | 'tr'
#
# Les crochets sont un ENVELOPPE (-> ESTIMATED), pas un contenu.
# Il faut donc DÉBALLER d'abord, ANALYSER le contenu ensuite.
# C'était l'erreur du bug 1 : on cherchait "tr" AVANT d'ouvrir les crochets,
# donc "[tr]" tombait dans la branche numérique et float("tr") plantait.

_BRACKETED = re.compile(r"^\[(?P<inner>.*)\]$")

# STRICT : on n'accepte QUE le jeton réellement utilisé par la FAO.
# Pas de "trace", pas de "TR", pas de .lower(). Un parseur permissif est un
# parseur qui absorbe les surprises en silence au lieu de les signaler.
_TRACE_TOKEN = "tr"


class UnparsableCellError(ValueError):
    """La cellule ne correspond à aucune convention WAFCT connue."""


def parse_value(raw: str | None, provenance: Provenance) -> ParsedValue:
    """Transforme une cellule brute en valeur typée.

    `provenance` est FOURNIE par l'appelant : elle ne se lit pas dans la cellule
    mais sur la ligne "Non-African data" de l'aliment. Le parseur ne devine pas.
    (Ancienne signature `is_oa: bool` : un booléen ne peut pas porter 3 états.)
    """
    # 1. Cellule absente ou vide -> jamais mesuré.
    if raw is None or raw.strip() == "":
        return ParsedValue(None, ValueStatus.NOT_DETERMINED, provenance)

    text = raw.strip()

    # 2. Déballer les crochets. C'est l'enveloppe, pas le contenu.
    match = _BRACKETED.match(text)
    is_estimated = match is not None
    atom = match.group("inner").strip() if match else text

    # 3. Analyser l'ATOME (donc "tr" est vu, qu'il soit ou non entre crochets).
    if atom == _TRACE_TOKEN:
        # "tr" ET "[tr]" -> TRACE.
        # Décision assumée : TRACE l'emporte sur ESTIMATED, car l'information utile
        # pour l'utilisateur est "on ne connaît pas le chiffre". On perd le fait que
        # c'était aussi estimé -> 4 cellules sur 53 652. Coût accepté, faille documentée.
        #
        # value = None (et NON 0.0) : décision produit. En santé, sous-estimer le
        # sodium est l'erreur dangereuse ; inventer une valeur est malhonnête.
        # On dit "il y en a un peu, on ne sait pas combien".
        return ParsedValue(None, ValueStatus.TRACE, provenance)

    try:
        number = float(atom)
    except ValueError:
        # PLANTER BRUYAMMENT. Jamais de `return None` silencieux : une convention
        # inconnue doit interrompre le pipeline, pas se glisser dans la base.
        raise UnparsableCellError(f"Cellule WAFCT illisible : {raw!r}") from None

    status = ValueStatus.ESTIMATED if is_estimated else ValueStatus.MEASURED
    return ParsedValue(number, status, provenance)


def resolve_provenance(food_has_oa_row: bool, cell_marked_oa: bool) -> Provenance:
    """Détermine la provenance d'UNE cellule à partir du contexte de son aliment.

    À appeler depuis la boucle silver, qui seule connaît la ligne "Non-African data".
    """
    if not food_has_oa_row:
        return Provenance.UNKNOWN      # aucune info : on ne conclut pas
    return Provenance.NON_AFRICAN if cell_marked_oa else Provenance.AFRICAN
