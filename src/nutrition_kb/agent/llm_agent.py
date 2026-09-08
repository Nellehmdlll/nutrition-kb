"""Le LLM local (Ollama, llama3.1:8b) comme cerveau de l'agent -- function calling.

C'est un SECOND chemin, pas un remplacement : router.py/execute.py (le
routeur par regles) restent en place comme filet de secours. Ce module ne
supprime rien, il ajoute une orchestration ou c'est le LLM qui decide quel
outil appeler et qui redige la reponse finale.

BOUCLE :
  1. Instruction systeme chargee depuis docs/system_prompt.md -- SOURCE
     UNIQUE, jamais dupliquee en dur ici (un prompt modifie sur disque est
     pris en compte au prochain appel, sans toucher au code).
  2. Envoi a Ollama : system + historique + question + description des 2
     outils (query_sql, search_vector) au format function calling.
  3. Si le LLM demande un outil -> on VALIDE ses arguments, puis on execute
     l'outil REEL (nos fonctions securisees), et on renvoie le resultat au
     LLM (role 'tool').
  4. Boucle jusqu'a une reponse en texte (pas d'appel d'outil), ou jusqu'a
     MAX_TOOL_ROUNDS (un LLM n'est pas garanti de converger).

SECURITE -- deux barrieres INDEPENDANTES du bon vouloir du LLM :
  - Medicale : detect_medical_signal() tourne AVANT tout appel a Ollama. Un
    signal detecte court-circuite completement le LLM -- meme texte de
    referral que le routeur par regles (render_response), point commun aux
    deux chemins. La securite medicale ne doit JAMAIS dependre uniquement
    d'un prompt (non deterministe) : double filet, code + prompt.
  - SQL : le LLM ne compose JAMAIS de requete. Il choisit une intention
    FERMEE ('top_by_nutrient') et des parametres ; c'est query_sql() qui
    ecrit le SQL (barriere deja en place dans tools.py). Tout argument venu
    du LLM (tagname, order, intent) est VALIDE avant d'atteindre les outils
    -- jamais de confiance aveugle sur une sortie de LLM.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import psycopg2
import requests

from nutrition_kb.agent.detect_medical_signal import detect_medical_signal, find_medical_signal_detail
from nutrition_kb.agent.execute import ExecutionResult, resolve_unit
from nutrition_kb.agent.render import render_response
from nutrition_kb.agent.tools import KNOWN_INTENTS, UnknownIntentError, query_sql, search_vector
from nutrition_kb.db import DSN

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[3] / "docs" / "system_prompt.md"

# Garde-fou : un LLM peut s'entêter a appeler des outils sans jamais conclure.
# Sans cette borne, la boucle 3 (tourner jusqu'a une reponse texte) n'a
# aucune garantie de terminer.
MAX_TOOL_ROUNDS = 5


def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Description des outils pour Ollama -- la correspondance nutriment->tagname
# vient de kb.nutrient_synonym, PAS d'une liste recopiee en dur : sinon elle
# pourrait diverger silencieusement de ce que detect_nutrient() connait deja.
# ---------------------------------------------------------------------------

_nutrient_reference_cache: Optional[str] = None
_known_tagnames_cache: Optional[set] = None


def _load_nutrient_reference_and_tagnames() -> tuple:
    global _nutrient_reference_cache, _known_tagnames_cache
    if _nutrient_reference_cache is not None:
        return _nutrient_reference_cache, _known_tagnames_cache

    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT synonym, tagname FROM kb.nutrient_synonym WHERE lang = 'fr' ORDER BY tagname, synonym")
            synonym_rows = cur.fetchall()
            cur.execute("SELECT DISTINCT tagname FROM kb.component")
            all_tagnames = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    by_tagname = {}
    for synonym, tagname in synonym_rows:
        by_tagname.setdefault(tagname, []).append(synonym)
    reference = ", ".join(f"{tagname} ({'/'.join(syns)})" for tagname, syns in by_tagname.items())

    _nutrient_reference_cache = reference
    _known_tagnames_cache = all_tagnames
    return reference, all_tagnames


def clear_cache() -> None:
    global _nutrient_reference_cache, _known_tagnames_cache
    _nutrient_reference_cache = None
    _known_tagnames_cache = None


def _build_tools() -> list:
    nutrient_reference, _ = _load_nutrient_reference_and_tagnames()
    return [
        {
            "type": "function",
            "function": {
                "name": "search_vector",
                "description": (
                    "Recherche des informations nutritionnelles sur l'aliment de la question de "
                    "l'utilisateur EN COURS (la question complete est deja connue, pas besoin de la "
                    "reformuler ni de la repeter). À utiliser pour les questions ouvertes ou de "
                    "conseil sur un aliment précis (ex: 'le gombo est-il intéressant ?', 'parle-moi "
                    "du soumbala')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "string",
                            "enum": ["diabetes", "hypertension", "macros"],
                            "description": "optionnel : restreint la recherche a un angle precis",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_sql",
                "description": (
                    "Classe les aliments selon leur teneur en un nutriment. À utiliser pour les "
                    "questions de classement ou de comparaison (ex: 'quels aliments sont les plus "
                    f"riches en sodium ?'). Correspondance nutriment -> tagname connue : {nutrient_reference}."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "enum": sorted(KNOWN_INTENTS),
                            "description": "toujours 'top_by_nutrient' pour l'instant",
                        },
                        "tagname": {
                            "type": "string",
                            "description": f"le nutriment sur lequel classer, un des codes suivants : {nutrient_reference}",
                        },
                        "order": {
                            "type": "string",
                            "enum": ["asc", "desc"],
                            "description": "'desc' = les plus riches en tete, 'asc' = les plus pauvres en tete",
                        },
                    },
                    "required": ["intent", "tagname", "order"],
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Execution reelle des outils -- jamais de confiance aveugle sur les
# arguments du LLM : tout est valide ICI, avant d'atteindre query_sql /
# search_vector.
#
# PRINCIPE : le LLM ne genere que ce qu'il est SEUL a pouvoir decider (quel
# outil, tagname, order, angle). Un argument deja disponible en clair --la
# question de l'utilisateur-- lui est fourni tout fait, jamais regenere : un
# modele de 8B peut reformuler ou tronquer un texte qu'il recopie (observe en
# pratique : "le soumbala, c'" au lieu de la question complete), et la
# recherche e5 est calibree pour matcher la question ORIGINALE contre les
# chunks -- une paraphrase n'apporte rien et ajoute un maillon non
# deterministe pour rien. D'ou original_question, ignoré nulle part ailleurs
# que pour search_vector : query_sql n'a pas ce probleme, tagname/order sont
# des choix que SEUL le LLM peut faire.
# ---------------------------------------------------------------------------

def execute_tool_call(name: str, arguments: dict, original_question: str) -> dict:
    if name == "search_vector":
        # Le schema de l'outil ne demande meme plus 'question' au LLM (cf.
        # _build_tools) ; on ignore quand meme tout ce qu'il aurait pu y
        # mettre par ailleurs -- defense en profondeur, pas de confiance
        # aveugle sur la forme exacte de ce qu'un modele renvoie.
        angle = arguments.get("angle")
        if angle is not None and angle not in ("diabetes", "hypertension", "macros"):
            return {"error": f"angle invalide : {angle!r} (attendu diabetes/hypertension/macros, ou rien)"}
        hits = search_vector(original_question, angle=angle)
        return {"hits": [asdict(h) for h in hits]}

    if name == "query_sql":
        intent = arguments.get("intent", "top_by_nutrient")
        tagname = arguments.get("tagname")
        order = arguments.get("order", "desc")

        _, known_tagnames = _load_nutrient_reference_and_tagnames()
        if tagname not in known_tagnames:
            return {"error": f"nutriment inconnu : {tagname!r}. Nutriments connus : {sorted(known_tagnames)}"}
        if order not in ("asc", "desc"):
            return {"error": f"order invalide : {order!r} (attendu 'asc' ou 'desc')"}

        unit = resolve_unit(tagname)
        try:
            rows = query_sql(intent, tagname=tagname, unit=unit, limit=5, order=order)
        except UnknownIntentError:
            return {"error": f"intention inconnue : {intent!r} -- outil indisponible pour cette intention"}
        return {"rows": [asdict(r) for r in rows]}

    return {"error": f"outil inconnu : {name!r}"}


def _call_ollama(messages: list, tools: list) -> dict:
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": messages, "tools": tools, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]


def run_llm_agent(question: str, history: Optional[list] = None) -> tuple:
    """Renvoie (reponse_texte, trace, messages).

    - trace : liste des appels d'outils reellement executes (pour le mode
      debug de scripts/try_llm_agent.py) -- [{tool, arguments, result}, ...].
    - messages : historique (SANS le system prompt, rechargé a chaque appel)
      a repasser en `history` au prochain tour pour garder le contexte.
    """
    if detect_medical_signal(question):
        # Court-circuit AVANT tout appel au LLM -- cf. docstring du module.
        detail = find_medical_signal_detail(question)
        result = ExecutionResult(kind="referral", data=None, reason=f"signal medical: {detail}")
        response_text = render_response(result)
        messages = list(history) if history else []
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": response_text})
        return response_text, [], messages

    messages = list(history) if history else []
    messages.append({"role": "user", "content": question})

    tools = _build_tools()
    trace = []

    for _ in range(MAX_TOOL_ROUNDS):
        llm_messages = [{"role": "system", "content": _load_system_prompt()}] + messages
        message = _call_ollama(llm_messages, tools)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return message.get("content", ""), trace, messages

        for call in tool_calls:
            fn = call["function"]
            name = fn["name"]
            arguments = fn["arguments"]
            result = execute_tool_call(name, arguments, original_question=question)
            trace.append({"tool": name, "arguments": arguments, "result": result})
            messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})

    fallback = "Désolé, je n'arrive pas à formuler une réponse claire pour cette question. Peux-tu reformuler ?"
    messages.append({"role": "assistant", "content": fallback})
    return fallback, trace, messages
