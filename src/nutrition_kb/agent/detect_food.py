"""Detection de mot(s)-cle d'aliment par regles, a partir de kb.food_keyword.

Meme structure que detect_nutrient (cf. ce module pour le detail du
raisonnement) : fonction d'EXTRACTION (tous les mots-cles vus, pas une
selection), match sur MOTS ENTIERS (frontieres \\b), cache rafraichissable.

food_keyword n'a pas d'equivalent au tagname de nutrient_synonym : le
mot-cle EST le resultat, pas de traduction vers un identifiant separe.
"""

import re
from typing import Optional

import psycopg2

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

_keyword_set_cache: Optional[set] = None


def load_keyword_set(lang: str = "fr") -> set:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT keyword FROM kb.food_keyword WHERE lang = %s", (lang,))
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def clear_cache() -> None:
    """Vide le cache en memoire du vocabulaire d'aliments.

    Comme pour detect_nutrient : le cache ne se rafraichit JAMAIS tout seul.
    Appeler clear_cache() (ou force_reload=True) apres tout reseed de
    kb.food_keyword, sinon l'ancien vocabulaire reste actif.
    """
    global _keyword_set_cache
    _keyword_set_cache = None


def detect_food(question: str, keyword_set: Optional[set] = None, force_reload: bool = False) -> list:
    """Rend la liste des mots-cles d'aliment reconnus dans la question (vide si aucun).

    keyword_set est optionnel : par defaut, charge depuis kb.food_keyword et
    mis en cache en memoire. L'injecter explicitement rend la fonction
    testable sans base de donnees (cf. tests).
    """
    if keyword_set is None:
        global _keyword_set_cache
        if force_reload or _keyword_set_cache is None:
            _keyword_set_cache = load_keyword_set()
        keyword_set = _keyword_set_cache

    normalized_question = normalize(question)
    found = []
    for keyword in sorted(keyword_set):
        if re.search(rf"\b{re.escape(keyword)}\b", normalized_question):
            if keyword not in found:
                found.append(keyword)
    return found
