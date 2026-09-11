"""L'OUTIL search_disease_info -- recherche semantique sur kb.disease_chunk.

Meme machinerie que nutrition_kb.agent.tools.search_vector (modele e5,
prefixe 'query: ', distance cosinus, seuil applique apres le tri), appliquee
a une table differente. Duplique volontairement la petite fonction plutot
que de faire dependre le module maladie du module agent/tools (nutrition) --
cf. brief : "separee logiquement de la nutrition". Le modele d'embedding
(_get_model) EST partage via nutrition_kb.rag.embedding, seul point de
verite pour le modele/prefixe -- ce qui est duplique ici, c'est juste la
requete SQL et son seuil, pas la logique d'encodage.
"""

from dataclasses import dataclass
from typing import Optional

import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from nutrition_kb.db import DSN
from nutrition_kb.rag.embedding import EMBEDDING_MODEL, encode_query


@dataclass
class DiseaseChunkHit:
    chunk_id: int
    disease: str
    section: str
    content: str
    distance: float
    source_id: str


_model_cache: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model_cache
    if _model_cache is None:
        _model_cache = SentenceTransformer(EMBEDDING_MODEL)
    return _model_cache


# Calibre le 2026-09-11 contre le vrai corpus (kb.disease_chunk, 17 lignes,
# intfloat/multilingual-e5-small) -- PAS suppose, meme discipline que
# search_vector :
#   - questions clairement dans le domaine maladie
#       "qu'est-ce que le diabète"          -> top_dist 0.106
#       "symptômes de l'hypertension"        -> top_dist 0.094
#   - nutrition (hors du domaine MALADIE, mais pas hors-sujet en general)
#       "le gombo est bon pour la tension ?" -> top_dist 0.197
#       "recette de cuisine burkinabe"       -> top_dist 0.190
#   - hors-sujet
#       "comment reparer une voiture"        -> top_dist 0.202
#       "quelle est la capitale de la France" -> top_dist 0.249
# Meme seuil que search_vector (0.18) : separe net les deux groupes sur CE
# corpus aussi (verifie, pas suppose par coincidence avec l'autre corpus).
DEFAULT_THRESHOLD = 0.18


def search_disease_info(
    question: str,
    disease: Optional[str] = None,
    top_k: int = 3,
    threshold: float = DEFAULT_THRESHOLD,
    conn=None,
) -> list:
    """Renvoie les sections de kb.disease_chunk les plus proches de `question`.

    Meme contrat que search_vector : seuil applique APRES le tri, une
    question hors du domaine maladie peut renvoyer une liste VIDE (signal
    voulu, pas une erreur).
    """
    model = _get_model()
    vector = encode_query(model, question)

    sql = (
        "SELECT chunk_id, disease, section, content, embedding <=> %s AS distance, source_id "
        "FROM kb.disease_chunk "
        "WHERE embedding IS NOT NULL"
    )
    params = [vector]
    if disease is not None:
        sql += " AND disease = %s"
        params.append(disease)
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
        DiseaseChunkHit(
            chunk_id=row[0], disease=row[1], section=row[2], content=row[3],
            distance=float(row[4]), source_id=row[5],
        )
        for row in rows
        if row[4] < threshold
    ]
