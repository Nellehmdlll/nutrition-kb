"""Tests de execute() : un par valeur de `kind`, plus les trous documentes
dans le brief (nutrients vide -> clarify, ENERC -> unit kcal par defaut).

Comme test_agent_router.py et test_agent_tools.py : appelle route() et
execute() tels quels contre la VRAIE base -- c'est l'ORCHESTRATION entre
routeur et outils qui est verifiee ici, pas des mocks. Seule exception :
le chemin 'no_result' (search_vector vide), monkeypatche pour ne pas
dependre d'une question "naturellement" hors-sujet qui pourrait cesser de
l'etre si le corpus ou le modele changent -- cf. meme raisonnement que le
monkeypatch de cache dans test_agent_detect_nutrient.py.
"""

from nutrition_kb.agent.execute import ExecutionResult, execute, resolve_unit
from nutrition_kb.agent.router import route
from nutrition_kb.agent.tools import ChunkHit, FoodValueRow


def test_execute_medical_referral_touches_no_tool():
    decision = route("ma glycemie est a 18")
    result = execute(decision)
    assert isinstance(result, ExecutionResult)
    assert result.kind == "referral"
    assert result.data is None
    assert "glycemie" in result.reason


def test_execute_clarify_when_nothing_detected():
    decision = route("raconte-moi ta journee")
    result = execute(decision)
    assert result.kind == "clarify"
    assert result.data is None


def test_execute_clarify_when_ranking_names_no_nutrient():
    # Trou n1 (cf. brief + docs/limitations.md limite n1) : forme 'ranking'
    # mais aucun nutriment nomme -- ici un ALIMENT est bien reconnu ('gombo'),
    # donc le routeur ne bloque pas en clarify a l'etape 2 comme pour "le plus
    # sale" ; c'est execute() qui doit rattraper l'absence de nutriment.
    decision = route("le gombo est le plus cher")
    assert decision.action == "sql"
    assert decision.nutrients == []

    result = execute(decision)
    assert result.kind == "clarify"
    assert "limite n1" in result.reason or "nutriment" in result.reason


def test_execute_sql_result_single_nutrient():
    decision = route("quel aliment contient le plus de sodium")
    assert decision.nutrients == ["NA"]

    result = execute(decision)
    assert result.kind == "sql_result"
    assert len(result.data) == 5
    assert all(isinstance(r, FoodValueRow) for r in result.data)
    assert all(r.tagname == "NA" and r.unit == "mg" for r in result.data)
    assert "NA" in result.reason and "mg" in result.reason and "desc" in result.reason


def test_execute_sql_result_multiple_nutrients_uses_first_and_signals_it():
    # Trou n2 : plusieurs nutriments nommes -> le premier est traite, et le
    # fait est SIGNALE dans reason plutot que choisi en silence.
    decision = route("quel aliment a le plus de sel et de sucre")
    assert decision.nutrients == ["NA", "CHOAVLDF"]

    result = execute(decision)
    assert result.kind == "sql_result"
    assert all(r.tagname == "NA" for r in result.data)
    assert "NA" in result.reason and "CHOAVLDF" in result.reason


def test_execute_sql_result_energy_defaults_to_kcal():
    # ENERC a deux unites en base (kJ et kcal) -- kcal est le defaut assume.
    decision = route("quel aliment est le plus riche en calories")
    assert decision.nutrients == ["ENERC"]

    result = execute(decision)
    assert result.kind == "sql_result"
    assert all(r.unit == "kcal" for r in result.data)
    assert "kcal" in result.reason


def test_resolve_unit_single_component_uses_its_own_unit():
    assert resolve_unit("NA") == "mg"


def test_resolve_unit_multiple_components_defaults_to_kcal():
    assert resolve_unit("ENERC") == "kcal"


def test_execute_vector_result_when_hits_found():
    decision = route("le gombo est bon pour moi ?")
    assert decision.action == "vector"

    result = execute(decision)
    assert result.kind == "vector_result"
    assert len(result.data) > 0
    assert all(isinstance(h, ChunkHit) for h in result.data)


def test_execute_vector_no_result_when_search_vector_finds_nothing(monkeypatch):
    import nutrition_kb.agent.execute as mod

    decision = route("le gombo est bon pour moi ?")
    assert decision.action == "vector"

    monkeypatch.setattr(mod, "search_vector", lambda question: [])
    result = execute(decision)
    assert result.kind == "no_result"
    assert result.data == []
