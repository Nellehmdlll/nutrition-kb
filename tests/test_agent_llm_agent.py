"""Tests de la PLOMBERIE de llm_agent.py -- pas de TDD classique sur la
sortie du LLM (non deterministe). Ce qui est teste :
  - l'execution reelle des outils (execute_tool_call) contre la vraie base ;
  - le rejet propre d'arguments invalides (mauvais tagname, mauvais order,
    outil inconnu) -- jamais de confiance aveugle sur une sortie de LLM ;
  - 'angle' TOLERANT (jamais bloquant) pour search_vector ;
  - le garde-fou anti-invention (_looks_fabricated) sur des reponses MOCKEES,
    jamais sur une vraie sortie de LLM ;
  - le court-circuit medical AVANT tout appel au LLM (deterministe, ne
    depend pas d'Ollama) ;
  - un test de fumee de bout en bout QUI appelle reellement Ollama, pour
    verifier que la boucle entiere (function calling multi-tours) fonctionne
    -- sans jamais asserter sur le TEXTE produit par le LLM.
"""

import nutrition_kb.agent.llm_agent as llm_agent_mod
from nutrition_kb.agent.llm_agent import (
    FABRICATION_FALLBACK,
    _looks_fabricated,
    execute_tool_call,
    run_llm_agent,
)


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


def test_execute_tool_call_search_vector_tolerates_invalid_angle(monkeypatch):
    # Correctif probleme 1 : un angle mal rempli ne bloque PLUS la recherche
    # -- observe en pratique, le LLM remplit parfois 'angle' avec n'importe
    # quoi ("null", "", "diabetes,hypertension"...), et rejeter faisait
    # echouer search_vector a chaque fois -> zero donnee -> invention.
    calls = []

    def fake_search_vector(question, angle=None):
        calls.append(angle)
        return []

    monkeypatch.setattr(llm_agent_mod, "search_vector", fake_search_vector)

    for bad_angle in ["null", "", "diabetes,hypertension", "n_importe_quoi", None]:
        result = execute_tool_call(
            "search_vector", {"angle": bad_angle}, original_question="le riz est bon ?"
        )
        assert "error" not in result

    # Toute valeur hors des 3 connues degrade vers None -- recherche sur
    # tous les angles, jamais un blocage.
    assert calls == [None, None, None, None, None]


def test_execute_tool_call_search_vector_accepts_valid_angle(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_agent_mod, "search_vector", lambda question, angle=None: calls.append(angle) or [])

    execute_tool_call("search_vector", {"angle": "hypertension"}, original_question="le riz est bon ?")

    assert calls == ["hypertension"]


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


def test_execute_tool_call_search_disease_info_returns_hits():
    result = execute_tool_call(
        "search_disease_info", {}, original_question="qu'est-ce que le diabète ?"
    )
    assert "hits" in result
    assert len(result["hits"]) > 0
    assert "content" in result["hits"][0]
    assert "section" in result["hits"][0]


def test_execute_tool_call_search_disease_info_ignores_llm_question_uses_original(monkeypatch):
    # Meme correctif que search_vector : le LLM ne doit jamais reformuler la
    # question envoyee a l'outil, meme s'il essaie.
    calls = []

    def fake_search_disease_info(question, disease=None):
        calls.append(question)
        return []

    monkeypatch.setattr(llm_agent_mod, "search_disease_info", fake_search_disease_info)

    original = "qu'est-ce que l'hypertension ?"
    execute_tool_call(
        "search_disease_info",
        {"question": "qu'est-ce que l'hyper"},  # argument LLM tronque -- doit etre ignore
        original_question=original,
    )

    assert calls == [original]


def test_execute_tool_call_search_disease_info_tolerates_invalid_disease(monkeypatch):
    # Meme tolerance que 'angle' sur search_vector : une valeur bizarre pour
    # 'disease' ne doit jamais bloquer la recherche.
    calls = []

    def fake_search_disease_info(question, disease=None):
        calls.append(disease)
        return []

    monkeypatch.setattr(llm_agent_mod, "search_disease_info", fake_search_disease_info)

    for bad_disease in ["null", "", "diabete,hypertension", "cancer", None]:
        result = execute_tool_call(
            "search_disease_info", {"disease": bad_disease}, original_question="qu'est-ce que le diabète ?"
        )
        assert "error" not in result

    assert calls == [None, None, None, None, None]


def test_execute_tool_call_search_disease_info_accepts_valid_disease(monkeypatch):
    calls = []
    monkeypatch.setattr(
        llm_agent_mod, "search_disease_info", lambda question, disease=None: calls.append(disease) or []
    )

    execute_tool_call(
        "search_disease_info", {"disease": "diabete"}, original_question="qu'est-ce que le diabète ?"
    )

    assert calls == ["diabete"]


def test_looks_fabricated_blocks_number_with_unit_and_no_tool_data():
    assert _looks_fabricated("Le quinoa apporte environ 150 kcal et 4g de protéines.", []) is True


def test_looks_fabricated_passes_when_tool_data_present():
    trace = [{"tool": "search_vector", "arguments": {}, "result": {"hits": [{"content": "..."}]}}]
    assert _looks_fabricated("Le quinoa apporte environ 150 kcal.", trace) is False


def test_looks_fabricated_passes_greeting_without_unit():
    assert _looks_fabricated("Bonjour, comment allez-vous ?", []) is False


def test_looks_fabricated_passes_bare_number_without_unit():
    # Un nombre NU (pas colle a une unite nutritionnelle) n'est pas une
    # invention de valeur -- "voici 3 aliments" est une enumeration, pas un
    # chiffre nutritionnel invente.
    assert _looks_fabricated("Voici 3 aliments qui pourraient vous intéresser.", []) is False


def test_looks_fabricated_ignores_tool_calls_that_only_errored_or_returned_nothing():
    # Un outil APPELE mais qui n'a rien renvoye (erreur, ou liste vide) ne
    # compte pas comme "donnees disponibles" -> bloque, ici via un chiffre
    # invente (mais cf. test suivant : le blocage ne depend meme plus de ça).
    trace = [
        {"tool": "search_vector", "arguments": {}, "result": {"hits": []}},
        {"tool": "query_sql", "arguments": {}, "result": {"error": "nutriment inconnu"}},
    ]
    assert _looks_fabricated("Cet aliment contient environ 12 mg de sodium.", trace) is True


def test_looks_fabricated_blocks_narrative_with_no_number_when_tool_called_empty():
    # Extension du garde-fou : observe en pratique sur "raconte-moi ta
    # journee" -- un outil appele qui renvoie zero donnee, puis un recit
    # ENTIER sans aucun chiffre ("j'ai recu trois demandes aujourd'hui...").
    # L'ancienne regle (chiffre+unite uniquement) laissait passer ce cas ;
    # desormais, un outil appele sans donnees bloque QUEL QUE SOIT le texte.
    trace = [{"tool": "search_vector", "arguments": {"angle": "diabetes"}, "result": {"hits": []}}]
    narrative = (
        "Aujourd'hui a été une journée très occupée ! J'ai reçu de nombreuses "
        "questions de personnes qui souhaitaient connaître la composition "
        "nutritionnelle des aliments locaux au Burkina Faso."
    )
    assert _looks_fabricated(narrative, trace) is True


def test_looks_fabricated_passes_when_no_tool_called_and_no_number():
    # Regression : si le LLM ne tente AUCUN outil et ne produit aucun chiffre,
    # rien ne doit bloquer -- ex. une simple salutation. Le garde-fou etendu
    # ne doit pas devenir surprotecteur pour les echanges qui n'ont jamais eu
    # besoin d'un outil.
    assert _looks_fabricated("Bonjour, comment puis-je vous aider ?", []) is False


def test_run_llm_agent_blocks_narrative_when_tool_called_returns_nothing(monkeypatch):
    # Reproduit le cas reel observe ("raconte-moi ta journee") : le LLM
    # appelle bien un outil, l'outil renvoie zero resultat, puis le LLM
    # improvise un recit sans aucun chiffre. Doit etre bloque comme le cas
    # chiffre -- c'est exactement ce que l'extension du garde-fou corrige.
    call_count = {"n": 0}

    def fake_call_ollama(messages, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "search_vector", "arguments": {}}}],
            }
        return {
            "role": "assistant",
            "content": "Aujourd'hui a été une journée très occupée ! J'ai aidé plusieurs personnes.",
        }

    monkeypatch.setattr(llm_agent_mod, "_call_ollama", fake_call_ollama)
    monkeypatch.setattr(llm_agent_mod, "search_vector", lambda question, angle=None: [])

    text, trace, messages = run_llm_agent("raconte-moi ta journée")

    assert text == FABRICATION_FALLBACK
    assert len(trace) == 1
    assert messages[-1]["content"] == FABRICATION_FALLBACK


def test_run_llm_agent_blocks_fabricated_response_from_mocked_ollama(monkeypatch):
    # Reponse LLM MOCKEE (pas d'appel reseau reel) : pas d'appel d'outil, un
    # chiffre nutritionnel invente -> doit etre bloquee et remplacee.
    def fake_call_ollama(messages, tools):
        return {"role": "assistant", "content": "Le quinoa apporte environ 150 kcal pour 100 g."}

    monkeypatch.setattr(llm_agent_mod, "_call_ollama", fake_call_ollama)

    text, trace, messages = run_llm_agent("le quinoa, c'est bon ?")

    assert text == FABRICATION_FALLBACK
    assert trace == []
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == FABRICATION_FALLBACK


def test_run_llm_agent_passes_through_mocked_response_without_number(monkeypatch):
    def fake_call_ollama(messages, tools):
        return {"role": "assistant", "content": "Bonjour, comment puis-je vous aider ?"}

    monkeypatch.setattr(llm_agent_mod, "_call_ollama", fake_call_ollama)

    text, trace, messages = run_llm_agent("bonjour")

    assert text == "Bonjour, comment puis-je vous aider ?"


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


def test_run_llm_agent_end_to_end_smoke_disease_info():
    # Test de fumee sur le nouvel outil : question sur LA MALADIE (pas un
    # aliment) -> doit passer par search_disease_info. AUCUNE assertion sur
    # le texte produit -- non deterministe.
    text, trace, messages = run_llm_agent("qu'est-ce que le diabète ?")
    assert isinstance(text, str)
    assert len(text) > 0
    assert any(call["tool"] == "search_disease_info" for call in trace)
