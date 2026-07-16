"""Encode gold.chunk.content en vecteurs pgvector, via sentence-transformers.

Reprenable par construction : ne traite QUE les lignes non encodees par le
modele courant, encode par lots, commit par lot. Si le processus est tue au
lot 30/48, les 29 precedents restent acquis -- relancer le script reprend
exactement la ou il s'est arrete, sans rien recalculer en double.
"""

import os

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from nutrition_kb.rag.embedding import EMBEDDING_MODEL, encode_passages

# ~64 : assez gros pour amortir le cout fixe de chaque appel au modele
# (3084 encodages un par un seraient tres lents), assez petit pour ne pas
# saturer la memoire sur un simple CPU.
BATCH_SIZE = 64

DSN = os.environ.get(
    "NUTRITION_KB_DSN",
    "postgresql://nutrition:nutrition@localhost:5432/nutrition_kb",
)


def fetch_pending(cur) -> list:
    # IS DISTINCT FROM, pas <> : NULL-safe (cf. commentaire dans
    # gold_chunk_table.sql). Sans ca, les chunks jamais encodes
    # (embedding_model IS NULL) echapperaient a la condition <> et resteraient
    # ignores pour toujours.
    cur.execute(
        """
        SELECT chunk_id, content
        FROM gold.chunk
        WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM %s
        ORDER BY chunk_id
        """,
        (EMBEDDING_MODEL,),
    )
    return cur.fetchall()


def main() -> int:
    conn = psycopg2.connect(DSN)
    # Enregistre l'adaptateur pgvector sur CETTE connexion : sans lui, il
    # faudrait serialiser chaque vecteur numpy en chaine '[0.1,0.2,...]' a la
    # main pour l'ecrire dans une colonne vector(384) -- source classique de
    # bugs de format. Avec l'adaptateur, un numpy.ndarray passe tel quel en
    # parametre de requete.
    register_vector(conn)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as read_cur:
        pending = fetch_pending(read_cur)

    total = len(pending)
    if total == 0:
        print(f"[embed] rien à encoder (déjà à jour avec {EMBEDDING_MODEL}).")
        conn.close()
        return 0

    print(f"[embed] {total} chunk(s) à encoder avec {EMBEDDING_MODEL}.")
    # Charge le modele APRES avoir verifie qu'il y a du travail : un rerun
    # idempotent (rien a faire) ne paie pas le cout de chargement du modele.
    model = SentenceTransformer(EMBEDDING_MODEL)

    done = 0
    for start in range(0, total, BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        contents = [row["content"] for row in batch]

        # encode_passages applique le prefixe "passage: " (exige par e5) et
        # normalize_embeddings=True (norme 1, coherent avec l'operateur de
        # distance cosinus <=>/vector_cosine_ops decide dans l'ADR 0008) --
        # cette logique vit dans embedding.py, jamais dupliquee ici.
        vectors = encode_passages(model, contents, batch_size=BATCH_SIZE)

        with conn.cursor() as write_cur:
            psycopg2.extras.execute_batch(
                write_cur,
                "UPDATE gold.chunk SET embedding = %s, embedding_model = %s WHERE chunk_id = %s",
                [
                    (vector, EMBEDDING_MODEL, row["chunk_id"])
                    for row, vector in zip(batch, vectors)
                ],
            )
        conn.commit()  # commit PAR LOT, pas a la toute fin : c'est ca qui rend le script reprenable.

        done += len(batch)
        print(f"[embed] {done}/{total}")

    conn.close()
    print(f"[embed] terminé : {total} chunk(s) encodé(s) avec {EMBEDDING_MODEL}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
