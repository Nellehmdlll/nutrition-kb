import pytest

from nutrition_kb.agent.seed_nutrient_synonyms import (
    RAW_SYNONYMS,
    SeedConflictError,
    build_seed_rows,
)


def test_build_seed_rows_normalizes_and_dedupes():
    rows = build_seed_rows(RAW_SYNONYMS)
    by_synonym = {synonym: (tagname, lang) for synonym, tagname, lang in rows}

    # 'sucre' et 'sucré' normalisent tous les deux vers 'sucre' -> une seule ligne.
    assert by_synonym["sucre"] == ("CHOAVLDF", "fr")
    assert len(rows) == len({syn for syn, _, _ in rows})  # aucune cle (synonym, lang) dupliquee

    assert by_synonym["sel"] == ("NA", "fr")
    assert by_synonym["sodium"] == ("NA", "fr")
    # 'salé' retire (ajustement) : sa forme normalisee 'sale' entre en
    # collision avec le mot francais courant "sale" (dirty) -> plus dans
    # la table du tout desormais, pas seulement absent de detect_nutrient.
    assert "sale" not in by_synonym
    assert by_synonym["glucides"] == ("CHOAVLDF", "fr")
    assert by_synonym["fibres"] == ("FIBTG", "fr")
    assert by_synonym["potassium"] == ("K", "fr")
    assert by_synonym["energie"] == ("ENERC", "fr")  # 'énergie' normalise
    assert by_synonym["calories"] == ("ENERC", "fr")


def test_build_seed_rows_raises_on_real_conflict():
    # Meme synonyme (donc meme forme normalisee), deux tagnames differents :
    # une vraie ambiguite, jamais a resoudre en silence.
    conflicting = [("sel", "NA"), ("sel", "K")]
    with pytest.raises(SeedConflictError):
        build_seed_rows(conflicting)
