"""Le LLM local (Ollama, llama3.1:8b) comme cerveau de l'agent -- function calling.

C'est un SECOND chemin, pas un remplacement : router.py/execute.py (le
routeur par regles) restent en place comme filet de secours. Ce module ne
supprime rien, il ajoute une orchestration ou c'est le LLM qui decide quel
outil appeler et qui redige la reponse finale.

BOUCLE :
  1. Instruction systeme chargee depuis docs/system_prompt.md -- SOURCE
     UNIQUE, jamais dupliquee en dur ici (un prompt modifie sur disque est
     pris en compte au prochain appel, sans toucher au code).
  2. Envoi a Ollama : system + historique + question + description des 3
     outils (query_sql, search_vector, search_disease_info) au format
     function calling.
  3. Si le LLM demande un outil -> on VALIDE ses arguments, puis on execute
     l'outil REEL (nos fonctions securisees), et on renvoie le resultat au
     LLM (role 'tool').
  4. Boucle jusqu'a une reponse en texte (pas d'appel d'outil), ou jusqu'a
     MAX_TOOL_ROUNDS (un LLM n'est pas garanti de converger).

SECURITE -- barrieres INDEPENDANTES du bon vouloir du LLM :
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
  - Anti-invention : si au moins un outil a ete appele dans le tour et
    qu'AUCUN n'a renvoye de donnees exploitables, la reponse est BLOQUEE cote
    code -- quel que soit son contenu (chiffre invente ou recit sans rapport
    avec les donnees, observes tous les deux en pratique). Si aucun outil
    n'a ete appele du tout, seul un chiffre colle a une unite nutritionnelle
    est detecte et bloque. Limite connue restante : une affirmation
    qualitative inventee SANS chiffre ET sans appel d'outil n'est pas
    attrapee (cf. docs/limitations.md).
  - Conseil medical/dietetique prescriptif ("vous pouvez manger", "evitez") :
    UNIQUEMENT attenue par le system prompt pour l'instant, pas de barriere
    code. Faille CONNUE, non entierement reglee -- cf. docs/limitations.md.
"""

import json
import logging
import re
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
from nutrition_kb.disease.search import search_disease_info

logger = logging.getLogger(__name__)

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
        {
            "type": "function",
            "function": {
                "name": "search_disease_info",
                "description": (
                    "Pour COMPRENDRE une maladie (diabète, hypertension) — sa définition, ses "
                    "symptômes, ses facteurs de risque, sa prévention, comment elle se traite en "
                    "général. À utiliser pour les questions sur la MALADIE elle-même. NE PAS "
                    "utiliser pour la composition nutritionnelle d'un aliment (utiliser "
                    "search_vector ou query_sql pour ça)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "disease": {
                            "type": "string",
                            "enum": ["diabete", "hypertension"],
                            "description": "optionnel : restreint la recherche a une maladie precise",
                        },
                    },
                    "required": [],
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
# outil, tagname, order, angle, disease). Un argument deja disponible en
# clair --la question de l'utilisateur-- lui est fourni tout fait, jamais
# regenere : un modele de 8B peut reformuler ou tronquer un texte qu'il
# recopie (observe en pratique : "le soumbala, c'" au lieu de la question
# complete), et la recherche e5 est calibree pour matcher la question
# ORIGINALE contre les chunks -- une paraphrase n'apporte rien et ajoute un
# maillon non deterministe pour rien. D'ou original_question, utilise pour
# search_vector ET search_disease_info (meme correctif) : query_sql n'a pas
# ce probleme, tagname/order sont des choix que SEUL le LLM peut faire.
# ---------------------------------------------------------------------------

def execute_tool_call(name: str, arguments: dict, original_question: str) -> dict:
    if name == "search_vector":
        # Le schema de l'outil ne demande meme plus 'question' au LLM (cf.
        # _build_tools) ; on ignore quand meme tout ce qu'il aurait pu y
        # mettre par ailleurs -- defense en profondeur, pas de confiance
        # aveugle sur la forme exacte de ce qu'un modele renvoie.
        #
        # 'angle' est TOLERANT, jamais bloquant : observe en pratique, un LLM
        # de 8B remplit parfois ce champ avec n'importe quoi ("null", "",
        # "diabetes,hypertension"...). Le rejeter comme une erreur empechait
        # la recherche de tourner DU TOUT -- zero donnee, le LLM invente pour
        # combler (cf. _looks_fabricated plus bas). Toute valeur hors des 3
        # connues degrade silencieusement vers "pas d'angle" (recherche sur
        # tous les angles) plutot que de bloquer l'outil.
        angle = arguments.get("angle")
        if angle not in ("diabetes", "hypertension", "macros"):
            angle = None
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

    if name == "search_disease_info":
        # Meme tolerance que 'angle' sur search_vector : toute valeur hors
        # des maladies connues degrade vers "pas de filtre" (recherche sur
        # diabete ET hypertension), jamais un blocage.
        disease = arguments.get("disease")
        if disease not in ("diabete", "hypertension"):
            disease = None
        hits = search_disease_info(original_question, disease=disease)
        return {"hits": [asdict(h) for h in hits]}

    return {"error": f"outil inconnu : {name!r}"}


# ---------------------------------------------------------------------------
# Garde-fou anti-invention -- CODE, pas juste prompt : observe en pratique,
# quand un outil echoue (zero resultat), le LLM peut soit inventer des
# chiffres et les attribuer a "la base FAO/INFOODS WAFCT 2019" (invention
# signee de notre source, critique), SOIT -- observe ensuite, sur une
# question hors-sujet ("raconte-moi ta journee") -- improviser un recit
# entier sans aucun chiffre ("j'ai recu trois demandes aujourd'hui...").
# Le prompt seul ne suffit pas a empecher ni l'un ni l'autre de facon
# fiable -- verifie en test reel dans les deux cas (le second, sur 7
# essais, 6 fois sur 7).
#
# Deux regles, dans cet ordre :
#   1. Au moins UN outil a ete appele dans ce tour ET AUCUN n'a renvoye de
#      donnees exploitables (tous vides ou en erreur) -> la reponse est
#      bloquee, QUEL QUE SOIT SON CONTENU (chiffre invente ou pur recit).
#      Rien ne justifie de faire confiance a un texte construit sur zero
#      donnee, qu'il "ait l'air" invente ou non.
#   2. AUCUN outil n'a ete appele du tout, MAIS la reponse contient quand
#      meme un chiffre colle a une unite nutritionnelle (le LLM a invente
#      sans meme essayer un outil) -> bloquee aussi.
#
# LIMITE CONNUE restante (cf. docs/limitations.md) : si le LLM n'appelle
# AUCUN outil et invente une affirmation QUALITATIVE sans chiffre ("le
# quinoa est traditionnel au Burkina Faso", faux, sans nombre), rien ne
# l'attrape -- probleme d'ancrage general, non resoluble simplement par une
# regex. Rétréci par cette extension (le cas "outil appele, zero donnee"
# est maintenant couvert quel que soit le contenu), pas élimine.
# ---------------------------------------------------------------------------

_NUTRITION_UNITS = r"(?:kcal|kj|kg|mcg|mg|µg|g|%)"
_NUTRITION_VALUE_RE = re.compile(
    rf"\d[\d\s.,]*{_NUTRITION_UNITS}\b|\b{_NUTRITION_UNITS}\s*\d",
    re.IGNORECASE,
)

FABRICATION_FALLBACK = (
    "Je n'ai pas d'information fiable sur ce sujet dans ma base de données. "
    "Peux-tu reformuler ta question, par exemple en citant un aliment ou une "
    "maladie précis ? Je préfère ne rien affirmer plutôt que de vous donner "
    "une information incertaine."
)


def _trace_has_data(trace: list) -> bool:
    """Un outil a-t-il reellement renvoye des donnees dans ce tour ? (pas
    juste ete appele -- une erreur ou un resultat vide ne comptent pas)."""
    return any(call["result"].get("rows") or call["result"].get("hits") for call in trace)


def _looks_fabricated(response_text: str, trace: list) -> bool:
    if _trace_has_data(trace):
        return False
    if trace:
        # Au moins un outil a ete appele, aucun n'a renvoye de donnees --
        # on ne fait JAMAIS confiance au texte dans ce cas, qu'il contienne
        # un chiffre invente ou un recit sans rapport avec les donnees.
        return True
    # Aucun outil appele du tout : on ne bloque que le cas restant detectable
    # simplement -- un chiffre nutritionnel invente sans meme avoir essaye.
    return bool(_NUTRITION_VALUE_RE.search(response_text))


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
            response_text = message.get("content", "")
            if _looks_fabricated(response_text, trace):
                logger.warning(
                    "Reponse LLM bloquee (invention suspectee, aucune donnee d'outil) -- question=%r reponse_bloquee=%r",
                    question, response_text,
                )
                response_text = FABRICATION_FALLBACK
                # Remplace aussi dans l'historique : une valeur inventee ne
                # doit jamais rester disponible pour un tour suivant (le LLM
                # pourrait la "reciter" comme acquise dans une reponse a venir).
                messages[-1] = {"role": "assistant", "content": response_text}
            return response_text, trace, messages

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
