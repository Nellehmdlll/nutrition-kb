"""Tests de la PLOMBERIE de llm_agent.py -- pas de TDD classique sur la
sortie du LLM (non deterministe). Ce qui est teste :
  - l'execution reelle des outils (execute_tool_call) contre la vraie base ;
  - le rejet propre d'arguments invalides (mauvais tagname, mauvais order,
    outil inconnu) -- jamais de confiance aveugle sur une sortie de LLM ;
  - le court-circuit medical AVANT tout appel au LLM (deterministe, ne
    depend pas d'Ollama) ;
  - un test de fumee de bout en bout QUI appelle reellement Ollama, pour
    verifier que la boucle entiere (function calling multi-tours) fonctionne
    -- sans jamais asserter sur le TEXTE produit par le LLM.
"""

from nutrition_kb.agent.llm_agent import execute_tool_call, run_llm_agent


def test_execute_tool_call_search_vector_returns_hits():
    result = execute_tool_call("search_vector", {}, original_question="le gombo est bon pour l'hypertension ?")
    assert "hits" in result
    assert len(result["hits"]) > 0
    assert "content" in result["hits"][0]


def test_execute_tool_call_search_vector_ignores_llm_question_uses_original(monkeypatch):
    # Le correctif : le LLM peut reformuler/tronquer ("le soumbala, c" au lieu
    # de la question complete, observe en pratique) -- meme si son argument
    # 'question' est present et fausse, search_vector doit recevoir la
    # question ORIGINALE de l'utilisateur, jamais celle du LLM.
    import nutrition_kb.agent.llm_agent as mod

    calls = []

    def fake_search_vector(question, angle=None):
        calls.append(question)
        return []

    monkeypatch.setattr(mod, "search_vector", fake_search_vector)

    original = "le soumbala, c'est bon pour l'hypertension ?"
    execute_tool_call(
        "search_vector",
        {"question": "le soumbala, c"},  # argument LLM tronque -- doit etre ignore
        original_question=original,
    )

    assert calls == [original]


def test_execute_tool_call_search_vector_rejects_bad_angle():
    result = execute_tool_call(
        "search_vector", {"angle": "n_importe_quoi"}, original_question="le riz est bon ?"
    )
    assert "error" in result
    assert "angle" in result["error"]


def test_execute_tool_call_query_sql_returns_rows():
    result = execute_tool_call(
        "query_sql", {"intent": "top_by_nutrient", "tagname": "NA", "order": "desc"}, original_question=""
    )
    assert "rows" in result
    assert len(result["rows"]) == 5
    assert result["rows"][0]["tagname"] == "NA"
    assert result["rows"][0]["unit"] == "mg"


def test_execute_tool_call_query_sql_defaults_energy_to_kcal():
    result = execute_tool_call(
        "query_sql", {"intent": "top_by_nutrient", "tagname": "ENERC", "order": "desc"}, original_question=""
    )
    assert result["rows"][0]["unit"] == "kcal"


def test_execute_tool_call_query_sql_rejects_unknown_tagname():
    # Jamais de confiance aveugle : un tagname invente par le LLM est rejete
    # AVANT d'atteindre resolve_unit()/query_sql().
    result = execute_tool_call(
        "query_sql", {"intent": "top_by_nutrient", "tagname": "PAS_UN_TAGNAME", "order": "desc"}, original_question=""
    )
    assert "error" in result
    assert "inconnu" in result["error"]


def test_execute_tool_call_query_sql_rejects_bad_order():
    result = execute_tool_call(
        "query_sql", {"intent": "top_by_nutrient", "tagname": "NA", "order": "sideways"}, original_question=""
    )
    assert "error" in result
    assert "order" in result["error"]


def test_execute_tool_call_query_sql_rejects_unknown_intent():
    # Barriere de tools.query_sql (UnknownIntentError) geree proprement --
    # pas de crash, un message clair renvoyable au LLM.
    result = execute_tool_call(
        "query_sql", {"intent": "drop_everything", "tagname": "NA", "order": "desc"}, original_question=""
    )
    assert "error" in result
    assert "inconnue" in result["error"]


def test_execute_tool_call_rejects_unknown_tool_name():
    result = execute_tool_call("outil_qui_n_existe_pas", {}, original_question="")
    assert "error" in result


def test_run_llm_agent_short_circuits_medical_signal_without_calling_llm():
    # Deterministe : ne depend PAS d'Ollama (le court-circuit intervient
    # avant le premier appel reseau).
    text, trace, messages = run_llm_agent("ma glycemie est a 18")
    assert "professionnel de sant" in text
    assert trace == []
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == text


def test_run_llm_agent_end_to_end_smoke():
    # Test de fumee : la boucle complete (Ollama + function calling reel)
    # tourne sans planter et produit une reponse. AUCUNE assertion sur le
    # texte produit -- non deterministe, cf. docstring du module.
    text, trace, messages = run_llm_agent("quel aliment contient le plus de sodium ?")
    assert isinstance(text, str)
    assert len(text) > 0
    assert isinstance(trace, list)
    assert messages[-1]["role"] == "assistant"
