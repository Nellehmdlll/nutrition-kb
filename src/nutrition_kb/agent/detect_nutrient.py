"""Detection de nutriment(s) par regles, a partir de kb.nutrient_synonym.

Fonction d'EXTRACTION, pas de selection : elle rend TOUS les tagnames vus
dans la question (dedupliques, ordre = ordre du synonym_map), jamais un
seul choisi a sa place -- c'est au routeur de decider quoi faire si
plusieurs nutriments sont mentionnes.

Correspondance sur des MOTS ENTIERS (frontieres \\b), pas une sous-chaine
brute : un synonyme court comme "sel" ne doit pas matcher a l'interieur
d'un autre mot qui le contient par hasard.
"""

import re
from typing import Mapping, Optional

import psycopg2

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

_synonym_map_cache: Optional[dict] = None


def load_synonym_map(lang: str = "fr") -> dict:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT synonym, tagname FROM kb.nutrient_synonym WHERE lang = %s ORDER BY synonym",
                (lang,),
            )
            return dict(cur.fetchall())
    finally:
        conn.close()


def clear_cache() -> None:
    """Vide le cache en memoire de la table de synonymes.

    Le cache ne se rafraichit JAMAIS tout seul : une fois charge, il ne
    reverra pas un changement fait dans kb.nutrient_synonym (ex. apres un
    reseed) tant que ce module reste en memoire. Appeler clear_cache()
    (ou passer force_reload=True a detect_nutrient) apres toute
    modification de la table, sinon les anciens synonymes restent actifs.
    """
    global _synonym_map_cache
    _synonym_map_cache = None


def detect_nutrient(
    question: str,
    synonym_map: Optional[Mapping[str, str]] = None,
    force_reload: bool = False,
) -> list:
    """Rend la liste des tagnames reconnus dans la question (vide si aucun).

    synonym_map est optionnel : par defaut, charge depuis kb.nutrient_synonym
    et mis en cache en memoire pour les appels suivants. L'injecter
    explicitement rend la fonction testable sans base de donnees (cf. tests).
    force_reload=True force un rechargement depuis la DB meme si un cache
    existe deja (equivalent a clear_cache() puis appel normal).
    """
    if synonym_map is None:
        global _synonym_map_cache
        if force_reload or _synonym_map_cache is None:
            _synonym_map_cache = load_synonym_map()
        synonym_map = _synonym_map_cache

    normalized_question = normalize(question)
    found = []
    for synonym, tagname in synonym_map.items():
        if re.search(rf"\b{re.escape(synonym)}\b", normalized_question):
            if tagname not in found:
                found.append(tagname)
    return found
