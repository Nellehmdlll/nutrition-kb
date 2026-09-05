"""Tests de render_response : un par valeur de `kind`, avec ExecutionResult
et FoodValueRow/ChunkHit construits a la main (pas de DB ici -- render_response
ne fait que reagencer du texte a partir de donnees deja recuperees, meme
niveau de test que detect_nutrient/detect_food avec une table injectee).
"""

from nutrition_kb.agent.execute import ExecutionResult
from nutrition_kb.agent.render import render_response
from nutrition_kb.agent.tools import ChunkHit, FoodValueRow


def test_render_referral_mixes_in_no_nutrition_data():
    result = ExecutionResult(
        kind="referral", data=None, reason="signal medical: mot-cle 'glycemie', valeur '18'"
    )
    text = render_response(result)

    assert "professionnel de sant" in text  # "santé"/"sante", insensible a l'e final accentue
    # RÈGLE ABSOLUE : aucune donnee nutritionnelle melee au message d'alerte --
    # ni le chiffre du signal medical, ni un mot du domaine nutrition/aliment.
    assert not any(ch.isdigit() for ch in text)
    for forbidden in ("kcal", "mg", "aliment", "gombo", "riz", "sodium"):
        assert forbidden not in text.lower()


def test_render_clarify_gives_helpful_example():
    result = ExecutionResult(kind="clarify", data=None, reason="aucun aliment ni nutriment identifie")
    text = render_response(result)

    assert "reformuler" in text
    assert "?" in text  # contient un exemple de question


def test_render_no_result_is_honest_about_missing_info():
    result = ExecutionResult(kind="no_result", data=[], reason="aucun chunk sous le seuil de confiance")
    text = render_response(result)

    assert "pas trouvé" in text or "aucune information" in text.lower()
    # n'invente rien : le texte ne doit pas ressembler a une reponse positive
    assert "reformul" in text


def test_render_sql_result_carries_uncertainty_for_estimated_and_non_african():
    rows = [
        FoodValueRow(
            food_code="01_001", name_fr="Mil, grain entier", tagname="NA", unit="mg",
            value=12.0, status="ESTIMATED", provenance="NON_AFRICAN", source_id="WAFCT_2019",
        ),
        FoodValueRow(
            food_code="02_002", name_fr="Sorgho, grain entier", tagname="NA", unit="mg",
            value=8.0, status="MEASURED", provenance="AFRICAN", source_id="WAFCT_2019",
        ),
    ]
    result = ExecutionResult(kind="sql_result", data=rows, reason="classement NA (mg), ordre=desc")
    text = render_response(result)

    # La ligne ESTIMATED/NON_AFRICAN doit porter les DEUX mentions d'incertitude.
    assert "valeur estimée" in text
    assert "d'après des données non africaines" in text
    # Chiffres et noms presents (reagencement des donnees, rien invente).
    assert "12" in text and "Mil" in text
    assert "8" in text and "Sorgho" in text
    # Source citee.
    assert "WAFCT_2019" in text


def test_render_sql_result_measured_african_has_no_spurious_qualifier():
    rows = [
        FoodValueRow(
            food_code="02_002", name_fr="Sorgho, grain entier", tagname="NA", unit="mg",
            value=8.0, status="MEASURED", provenance="AFRICAN", source_id="WAFCT_2019",
        ),
    ]
    result = ExecutionResult(kind="sql_result", data=rows, reason="classement NA (mg), ordre=desc")
    text = render_response(result)

    assert "estimée" not in text
    assert "non africaines" not in text
    assert "non précisée" not in text


def test_render_vector_result_presents_chunk_content_verbatim():
    hits = [
        ChunkHit(
            chunk_id=1, food_code="01_172", angle="hypertension",
            content="Gombo, frais, cru contient environ 7 mg de sodium (provenance non précisée). Source : FAO/INFOODS WAFCT 2019.",
            distance=0.08, source_id="WAFCT_2019",
        ),
    ]
    result = ExecutionResult(kind="vector_result", data=hits, reason="aliments=['gombo'], nutriments=[], forme=advice")
    text = render_response(result)

    # Presente TEL QUEL : le contenu du chunk doit apparaitre mot pour mot.
    assert hits[0].content in text
