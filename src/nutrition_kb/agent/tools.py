"""Les OUTILS que le routeur peut faire executer -- jamais l'inverse.

Deux outils pour l'instant :
  - query_sql(intent, **params)  : requetes structurees, intention FERMEE.
  - search_vector(question, ...) : recherche semantique sur gold.chunk.

Ce module ne connait PAS le routeur (nutrition_kb.agent.router) : c'est
execute.py qui fait le pont entre une RoutingDecision et ces fonctions.
Objectif de la separation : pouvoir remplacer le routeur par un LLM plus
tard sans toucher a une ligne ici.
"""

from dataclasses import dataclass
from typing import Optional

import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from nutrition_kb.db import DSN
from nutrition_kb.rag.embedding import EMBEDDING_MODEL, encode_query


@dataclass
class FoodValueRow:
    food_code: str
    name_fr: str
    tagname: str
    unit: str
    value: float
    status: str        # MEASURED | ESTIMATED (jamais TRACE : value serait NULL)
    provenance: str    # AFRICAN | NON_AFRICAN | UNKNOWN
    source_id: str     # pour citer : toujours 'WAFCT_2019' aujourd'hui


@dataclass
class ChunkHit:
    chunk_id: int
    food_code: str
    angle: str
    content: str
    distance: float    # distance cosinus (<=>) -- plus petit = plus proche
    source_id: str      # pour citer : toujours 'WAFCT_2019' aujourd'hui


# ---------------------------------------------------------------------------
# query_sql -- barriere de securite : intention FERMEE, jamais de SQL compose
# a partir d'une entree libre.
# ---------------------------------------------------------------------------

KNOWN_INTENTS = {"top_by_nutrient"}


class UnknownIntentError(ValueError):
    """Intention absente de KNOWN_INTENTS -- refusee avant toute requete."""


def query_sql(intent: str, **params) -> list:
    if intent not in KNOWN_INTENTS:
        raise UnknownIntentError(intent)
    if intent == "top_by_nutrient":
        return _top_by_nutrient(**params)


# ORDER BY ne se parametre pas avec %s (ce n'est pas une valeur, c'est du
# SQL) -- liste blanche verifiee AVANT toute f-string, jamais l'inverse.
_ORDER_SQL = {"asc": "ASC", "desc": "DESC"}


def _top_by_nutrient(tagname: str, unit: str, limit: int = 5, order: str = "desc", conn=None) -> list:
    if order not in _ORDER_SQL:
        raise ValueError(f"order invalide : {order!r} (attendu 'asc' ou 'desc')")

    # value IS NOT NULL exclut deja les lignes TRACE (value toujours NULL pour
    # ce statut, cf. contrainte value_matches_status) : NULLS LAST est donc de
    # la ceinture-et-bretelles, pas un besoin reel avec les donnees actuelles.
    sql = (
        "SELECT fv.food_code, f.name_fr, fv.tagname, fv.unit, fv.value, fv.status, fv.provenance, fv.source_id "
        "FROM kb.food_value fv "
        "JOIN kb.food f ON f.food_code = fv.food_code "
        "WHERE fv.tagname = %s AND fv.unit = %s AND fv.value IS NOT NULL "
        f"ORDER BY fv.value {_ORDER_SQL[order]} NULLS LAST "
        "LIMIT %s"
    )
    # conn injectable : execute() ouvre UNE connexion pour resolve_unit() +
    # query_sql() plutot que d'en ouvrir une par appel (cf. execute.py).
    own_conn = conn is None
    if own_conn:
        conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (tagname, unit, limit))
            rows = cur.fetchall()
    finally:
        if own_conn:
            conn.close()

    return [
        FoodValueRow(
            food_code=row[0],
            name_fr=row[1],
            tagname=row[2],
            unit=row[3],
            value=float(row[4]),
            status=row[5],
            provenance=row[6],
            source_id=row[7],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# search_vector -- recherche semantique sur gold.chunk.
# ---------------------------------------------------------------------------

_model_cache: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    # Charger le modele coute plusieurs secondes : mis en cache en memoire,
    # comme les caches de detect_nutrient/detect_food (meme raison, cout
    # different -- ici c'est le modele, pas une table).
    global _model_cache
    if _model_cache is None:
        _model_cache = SentenceTransformer(EMBEDDING_MODEL)
    return _model_cache


# Seuil calibre le 2026-09-05 contre la vraie base (gold.chunk, 3084 lignes
# encodees, intfloat/multilingual-e5-small) -- PAS suppose :
#   - questions clairement dans le domaine
#       "combien de sodium dans le gombo"            -> top_dist 0.060
#       "le riz est bon pour le diabete ?"            -> top_dist 0.112
#       "le gombo est bon pour l'hypertension ?"      -> top_dist 0.119
#   - aliment absent du corpus mais toujours nutrition
#       "le kiwi est bon pour la tension ?"           -> top_dist 0.172
#   - hors-sujet
#       "comment reparer une voiture qui ne demarre pas" -> top_dist 0.193
#       "quel est le sens de la vie ?"                    -> top_dist 0.194
#       "quelle est la capitale de la France"             -> top_dist 0.231
# Le 0.35 envisage au depart n'aurait JAMAIS rejete -- meme le hors-sujet le
# plus flagrant reste sous 0.35 avec ce modele sur ce corpus (les distances
# e5 restent compressees sur un corpus etroit et homogene). 0.18 separe net
# les deux groupes observes ici. Echantillon petit (8 questions, a la main) :
# a recalibrer avec un vrai jeu d'evaluation des que possible.
DEFAULT_THRESHOLD = 0.18


def search_vector(
    question: str,
    angle: Optional[str] = None,
    top_k: int = 3,
    threshold: float = DEFAULT_THRESHOLD,
    conn=None,
) -> list:
    """Renvoie les chunks les plus proches de `question`, sous `threshold`.

    Le seuil est applique APRES le tri : trier par distance, prendre les
    top_k premiers, puis ne garder que ceux sous le seuil. Une question
    hors-sujet peut donc renvoyer une liste VIDE -- c'est le signal voulu
    ("rien de fiable"), pas un cas d'erreur a rattraper.
    """
    model = _get_model()
    vector = encode_query(model, question)

    # embedding IS NOT NULL : garde defensive -- toutes les lignes de
    # gold.chunk sont deja encodees aujourd'hui (embed_chunks.py), mais rien
    # ne garantit que ça reste vrai (nouveau chunk ajoute avant le prochain
    # passage du script d'encodage, par exemple).
    sql = (
        "SELECT chunk_id, food_code, angle, content, embedding <=> %s AS distance, source_id "
        "FROM gold.chunk "
        "WHERE embedding IS NOT NULL"
    )
    params = [vector]
    if angle is not None:
        sql += " AND angle = %s"
        params.append(angle)
    sql += " ORDER BY distance LIMIT %s"
    params.append(top_k)

    own_conn = conn is None
    if own_conn:
        conn = psycopg2.connect(DSN)
        register_vector(conn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        if own_conn:
            conn.close()

    return [
        ChunkHit(
            chunk_id=row[0], food_code=row[1], angle=row[2], content=row[3],
            distance=float(row[4]), source_id=row[5],
        )
        for row in rows
        if row[4] < threshold
    ]
