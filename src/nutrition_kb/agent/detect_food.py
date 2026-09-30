"""Detection de mot(s)-cle d'aliment par regles, a partir de kb.food_keyword
ET de kb.food_local_match (termes vernaculaires apparies, Temps 3).

Meme structure que detect_nutrient (cf. ce module pour le detail du
raisonnement) : fonction d'EXTRACTION (tous les termes vus, pas une
selection), match sur MOTS ENTIERS (frontieres \\b), cache rafraichissable.

DEUX sources fusionnees dans UNE structure {terme: [resultats]} -- le terme
reconnu dans la question est la cle, peu importe sa source ; seul ce qu'il
faut RENVOYER differe :
  - kb.food_keyword : le mot-cle se renvoie lui-meme (pas de food_code --
    food_keyword n'a pas d'equivalent au tagname de nutrient_synonym).
  - kb.food_local_match (status='matched') : le terme renvoie son ou ses
    food_code (ex. 'dolo' -> deux lignes, deux food_code -- bière de mil ET
    de sorgho).
Un terme present dans LES DEUX sources (ex. 'soumbala', deja un mot-cle
extrait de food.name_fr ET desormais aussi vernaculaire apparie) cumule les
deux resultats : le mot-cle ET le food_code resolu, tous les deux utiles.

Compat retro : keyword_set accepte encore un set brut (API historique, cf.
tests) -- chaque mot se mappe alors sur lui-meme, comportement identique a
avant cette extension.
"""

import re
from typing import Optional, Union

import psycopg2

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

_keyword_set_cache: Optional[dict] = None
_known_without_data_cache: Optional[dict] = None


def load_keyword_set(lang: str = "fr") -> dict:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT keyword FROM kb.food_keyword WHERE lang = %s", (lang,))
            terms: dict = {row[0]: [row[0]] for row in cur.fetchall()}

            # PAS de filtre lang ici : un terme vernaculaire (moore ou fr)
            # peut apparaitre dans une question francaise quelle que soit sa
            # langue d'origine -- 'lang' documente la PROVENANCE du terme,
            # pas la langue attendue de la question qui le contient.
            cur.execute("SELECT term, food_code FROM kb.food_local_match WHERE status = 'matched'")
            for term, food_code in cur.fetchall():
                bucket = terms.setdefault(term, [])
                if food_code not in bucket:
                    bucket.append(food_code)
    finally:
        conn.close()
    return terms


def load_known_without_data_terms() -> dict:
    """{terme: note} pour les entrees food_local_match SANS food_code
    (status 'absent_wafct' ou 'unknown') -- vocabulaire SEPARE de celui de
    detect_food : ces termes ne renvoient JAMAIS de food_code (il n'y en a
    pas). Sans cette fonction, un terme connu-mais-sans-donnees (ex. 'voaga',
    le kapok, absent de la WAFCT) serait indiscernable d'un terme totalement
    inconnu -- l'agent dirait alors a tort "je ne connais pas cet aliment"
    au lieu de "je le connais, je n'ai juste pas ses donnees".
    """
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT term, note FROM kb.food_local_match WHERE status IN ('absent_wafct', 'unknown')"
            )
            return dict(cur.fetchall())
    finally:
        conn.close()


def clear_cache() -> None:
    """Vide les caches en memoire (vocabulaire d'aliments ET termes
    connus-sans-donnees).

    Comme pour detect_nutrient : les caches ne se rafraichissent JAMAIS tout
    seuls. Appeler clear_cache() (ou force_reload=True) apres tout reseed de
    kb.food_keyword / kb.food_local_match, sinon l'ancien vocabulaire reste
    actif.
    """
    global _keyword_set_cache, _known_without_data_cache
    _keyword_set_cache = None
    _known_without_data_cache = None


def _as_terms_dict(keyword_set: Union[set, dict]) -> dict:
    if isinstance(keyword_set, dict):
        return keyword_set
    return {k: [k] for k in keyword_set}


def detect_food(question: str, keyword_set: Optional[Union[set, dict]] = None, force_reload: bool = False) -> list:
    """Rend la liste des mots-cles/food_code reconnus dans la question (vide si aucun).

    keyword_set est optionnel : par defaut, charge depuis kb.food_keyword +
    kb.food_local_match et mis en cache en memoire. L'injecter explicitement
    (set OU dict) rend la fonction testable sans base de donnees (cf. tests).
    """
    if keyword_set is None:
        global _keyword_set_cache
        if force_reload or _keyword_set_cache is None:
            _keyword_set_cache = load_keyword_set()
        keyword_set = _keyword_set_cache

    terms = _as_terms_dict(keyword_set)
    normalized_question = normalize(question)
    found = []
    for term in sorted(terms):
        if re.search(rf"\b{re.escape(term)}\b", normalized_question):
            for result in terms[term]:
                if result not in found:
                    found.append(result)
    return found


def detect_known_without_data(question: str, terms: Optional[dict] = None, force_reload: bool = False) -> list:
    """Rend les termes CONNUS mais SANS donnees mentionnes dans la question
    (ex. 'voaga') -- jamais un food_code, cf. docstring de
    load_known_without_data_terms(). Vide si aucun terme de ce type n'est
    mentionne (ce qui NE VEUT PAS DIRE que la question ne parle d'aucun
    aliment -- voir detect_food() pour les aliments qui ONT des donnees).
    """
    if terms is None:
        global _known_without_data_cache
        if force_reload or _known_without_data_cache is None:
            _known_without_data_cache = load_known_without_data_terms()
        terms = _known_without_data_cache

    normalized_question = normalize(question)
    found = []
    for term in sorted(terms):
        if re.search(rf"\b{re.escape(term)}\b", normalized_question):
            if term not in found:
                found.append(term)
    return found
