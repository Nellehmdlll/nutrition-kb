"""Tests de parse_value / resolve_provenance.

RÈGLE, apprise à la dure : un test qui échoue est une INFORMATION, pas un obstacle.
Le cas "[tr]" avait été retiré de la liste — et c'était précisément celui qui
faisait planter le code. Supprimer un test pour passer au vert, ce n'est plus
tester son code : c'est tester son optimisme. Il est ci-dessous, en premier.
"""

import pytest

from nutrition_kb.transform.value import (
    ParsedValue,
    Provenance,
    UnparsableCellError,
    ValueStatus,
    parse_value,
    resolve_provenance,
)

AF = Provenance.AFRICAN
NA = Provenance.NON_AFRICAN
UNK = Provenance.UNKNOWN


@pytest.mark.parametrize(
    "raw, provenance, expected",
    [
        # --- LE cas qui avait été supprimé -------------------------------------
        # "[tr]" : trace ET entre crochets. TRACE l'emporte (cf. value.py).
        # Cellule réelle : 03_003 Bambara groundnut / VITA.
        ("[tr]", AF, ParsedValue(None, ValueStatus.TRACE, AF)),

        # --- Les 6 cellules réelles observées dans la feuille 06 ---------------
        ("1.00", AF, ParsedValue(1.0, ValueStatus.MEASURED, AF)),        # 01_172 / EDIBLE2
        ("[0.2]", AF, ParsedValue(0.2, ValueStatus.ESTIMATED, AF)),      # 01_172 / FAT
        ("tr", AF, ParsedValue(None, ValueStatus.TRACE, AF)),            # 02_036 / VITA
        ("4.6", NA, ParsedValue(4.6, ValueStatus.MEASURED, NA)),         # 01_188 / WATER  (oa)
        ("[61]", NA, ParsedValue(61.0, ValueStatus.ESTIMATED, NA)),      # 01_188 / CARTBEQ (oa)
        ("", AF, ParsedValue(None, ValueStatus.NOT_DETERMINED, AF)),

        # --- Absence de cellule ------------------------------------------------
        (None, AF, ParsedValue(None, ValueStatus.NOT_DETERMINED, AF)),

        # --- Provenance UNKNOWN : elle doit traverser le parseur intacte -------
        # (91 des 116 aliments burkinabè sont dans ce cas.)
        ("0", UNK, ParsedValue(0.0, ValueStatus.MEASURED, UNK)),
        ("[2.5]", UNK, ParsedValue(2.5, ValueStatus.ESTIMATED, UNK)),
        ("tr", UNK, ParsedValue(None, ValueStatus.TRACE, UNK)),

        # --- Robustesse de forme ------------------------------------------------
        ("  2.4  ", AF, ParsedValue(2.4, ValueStatus.MEASURED, AF)),
        ("[ 0.5 ]", AF, ParsedValue(0.5, ValueStatus.ESTIMATED, AF)),
        ("0", AF, ParsedValue(0.0, ValueStatus.MEASURED, AF)),  # zéro RÉEL != absence
    ],
)
def test_parse_value_cases(raw, provenance, expected):
    assert parse_value(raw, provenance) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "abc",      # texte inconnu
        "6,25",     # virgule décimale : convention absente de la WAFCT -> refuser
        "trace",    # jeton NON utilisé par la FAO -> refuser (parseur strict)
        "TR",       # casse différente -> refuser
        "[abc]",    # crochets bien formés, contenu illisible
        "[]",       # crochets vides
    ],
)
def test_parse_value_refuses_unknown_conventions(raw):
    """Toute convention inconnue doit PLANTER, jamais retourner None en silence.

    Un parseur permissif absorbe les surprises ; un parseur strict les signale.
    """
    with pytest.raises(UnparsableCellError):
        parse_value(raw, AF)


@pytest.mark.parametrize(
    "has_oa_row, marked_oa, expected",
    [
        (True, True, Provenance.NON_AFRICAN),   # marquée "oa"
        (True, False, Provenance.AFRICAN),      # ligne présente, cellule non marquée
        (False, False, Provenance.UNKNOWN),     # aucune ligne "Non-African data"
        (False, True, Provenance.UNKNOWN),      # incohérent -> on refuse de conclure
    ],
)
def test_resolve_provenance(has_oa_row, marked_oa, expected):
    assert resolve_provenance(has_oa_row, marked_oa) == expected
