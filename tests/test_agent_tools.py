"""Tests des outils (query_sql, search_vector) contre la VRAIE base
(kb.food_value, kb.component, gold.chunk) et le vrai modele d'embedding --
meme logique que test_agent_router.py : tester ca avec des tables ou un
modele fictifs reviendrait a tester des mocks, pas les outils reels.
"""

import pytest

from nutrition_kb.agent.tools import (
    ChunkHit,
    FoodValueRow,
    UnknownIntentError,
    query_sql,
    search_vector,
)


def test_query_sql_rejects_unknown_intent():
    with pytest.raises(UnknownIntentError):
        query_sql("drop_everything")


def test_top_by_nutrient_rejects_invalid_order():
    with pytest.raises(ValueError):
        query_sql("top_by_nutrient", tagname="NA", unit="mg", limit=5, order="sideways")


def test_top_by_nutrient_desc_returns_highest_first():
    rows = query_sql("top_by_nutrient", tagname="NA", unit="mg", limit=5, order="desc")
    assert len(rows) == 5
    assert all(isinstance(r, FoodValueRow) for r in rows)
    values = [r.value for r in rows]
    assert values == sorted(values, reverse=True)
    # l'incertitude voyage avec le classement : jamais vide sur ces colonnes
    assert all(r.status for r in rows)
    assert all(r.provenance for r in rows)


def test_top_by_nutrient_asc_returns_lowest_first():
    rows = query_sql("top_by_nutrient", tagname="NA", unit="mg", limit=5, order="asc")
    values = [r.value for r in rows]
    assert values == sorted(values)


def test_top_by_nutrient_respects_limit():
    rows = query_sql("top_by_nutrient", tagname="NA", unit="mg", limit=2, order="desc")
    assert len(rows) == 2


def test_search_vector_returns_hits_for_on_topic_question():
    hits = search_vector("le gombo est bon pour l'hypertension ?")
    assert len(hits) > 0
    assert all(isinstance(h, ChunkHit) for h in hits)
    assert all(h.distance <= 0.18 for h in hits)


def test_search_vector_returns_empty_for_off_topic_question():
    # Cf. calibration reelle documentee dans tools.py : une question
    # hors-sujet ne descend jamais sous le seuil -- liste vide, pas une
    # reponse forcee.
    hits = search_vector("quelle est la capitale de la France")
    assert hits == []


def test_search_vector_respects_top_k():
    hits = search_vector("le gombo est bon pour l'hypertension ?", top_k=2)
    assert len(hits) <= 2


def test_search_vector_filters_by_angle():
    hits = search_vector("le gombo est bon pour l'hypertension ?", angle="hypertension")
    assert all(h.angle == "hypertension" for h in hits)
