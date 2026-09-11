"""Encode kb.disease_chunk.content en vecteurs pgvector -- MEME pipeline que
rag/embed_chunks.py (meme modele, meme prefixe 'passage: ', meme colonne
embedding_model), applique a la table maladie au lieu de gold.chunk.

Reprenable par construction : ne traite que les lignes non encodees par le
modele courant (meme requete IS DISTINCT FROM que embed_chunks.py, meme
raison -- NULL-safe, sinon les lignes jamais encodees y echapperaient).
"""

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from nutrition_kb.db import DSN
from nutrition_kb.rag.embedding import EMBEDDING_MODEL, encode_passages

BATCH_SIZE = 64


def fetch_pending(cur) -> list:
    cur.execute(
        """
        SELECT chunk_id, content
        FROM kb.disease_chunk
        WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM %s
        ORDER BY chunk_id
        """,
        (EMBEDDING_MODEL,),
    )
    return cur.fetchall()


def main() -> int:
    conn = psycopg2.connect(DSN)
    register_vector(conn)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as read_cur:
        pending = fetch_pending(read_cur)

    total = len(pending)
    if total == 0:
        print(f"[embed-disease] rien à encoder (déjà à jour avec {EMBEDDING_MODEL}).")
        conn.close()
        return 0

    print(f"[embed-disease] {total} chunk(s) à encoder avec {EMBEDDING_MODEL}.")
    model = SentenceTransformer(EMBEDDING_MODEL)

    done = 0
    for start in range(0, total, BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        contents = [row["content"] for row in batch]
        vectors = encode_passages(model, contents, batch_size=BATCH_SIZE)

        with conn.cursor() as write_cur:
            psycopg2.extras.execute_batch(
                write_cur,
                "UPDATE kb.disease_chunk SET embedding = %s, embedding_model = %s WHERE chunk_id = %s",
                [
                    (vector, EMBEDDING_MODEL, row["chunk_id"])
                    for row, vector in zip(batch, vectors)
                ],
            )
        conn.commit()

        done += len(batch)
        print(f"[embed-disease] {done}/{total}")

    conn.close()
    print(f"[embed-disease] terminé : {total} chunk(s) encodé(s) avec {EMBEDDING_MODEL}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
