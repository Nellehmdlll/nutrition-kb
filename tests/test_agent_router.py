"""Tests du routeur : un par CHEMIN de l'arbre de decision.

Contrairement a detect_nutrient/detect_food (testes avec une table injectee,
sans DB), ces tests appellent route() tel quel : c'est l'ORCHESTRATION des
briques deja testees individuellement qui est verifiee ici, contre le
vocabulaire REEL (kb.food_keyword, kb.nutrient_synonym). Tester ca avec des
tables fictives reviendrait a tester des mocks, pas le routeur.
"""

from nutrition_kb.agent.router import RoutingDecision, route


def test_route_medical_signal_wins_priority():
    decision = route("ma glycemie est a 18")
    assert decision.action == "medical_referral"


def test_route_clarify_when_nothing_detected():
    decision = route("raconte-moi ta journee")
    assert decision.action == "clarify"
    assert decision.foods == []
    assert decision.nutrients == []


def test_route_sql_when_ranking_form():
    decision = route("quel aliment contient le plus de sodium")
    assert decision.action == "sql"
    assert decision.form == "ranking"
    assert decision.nutrients == ["NA"]


def test_route_clarify_when_ranking_marker_names_nothing():
    # LIMITE CONNUE, assumee : 'quel aliment est le plus salé' ne nomme ni
    # aliment ni nutriment reconnu ('salé' a ete retire de nutrient_synonym
    # et food_keyword, collision avec 'sale'=dirty). L'etape 2 de l'arbre
    # bloque donc AVANT meme de regarder detect_form -- clarify, pas sql.
    # Documente ici pour que ce ne soit jamais "corrige" par accident sans
    # decision explicite (cf. echange avec l'utilisateur, 2026-09).
    decision = route("quel aliment est le plus sale")
    assert decision.action == "clarify"


def test_route_vector_when_advice_form():
    decision = route("le gombo est bon pour moi ?")
    assert decision.action == "vector"
    assert decision.form == "advice"
    assert "gombo" in decision.foods


def test_route_medical_signal_beats_food_detection():
    # L'ORDRE de priorite doit tenir : un signal medical present ET un
    # aliment mentionne -> medical_referral gagne quand meme, foods/nutrients
    # ne sont meme pas calcules (STOP au step 1).
    decision = route("glycemie 18, je mange du riz ?")
    assert decision.action == "medical_referral"
    assert decision.foods == []


def test_route_decision_fields_always_filled():
    # "Remplir foods, nutrients, form, reason dans tous les cas" (branche 3)
    decision = route("le gombo est bon pour moi ?")
    assert isinstance(decision, RoutingDecision)
    assert decision.reason  # non vide
    assert decision.form in ("ranking", "advice")
