"""Peuple kb.food_keyword avec le vocabulaire final (cf. build_food_keywords.py).

Reutilise build_vocabulary() -- la MEME fonction qui produit le rapport de
revue -- pour que ce qui est ecrit en base soit garanti identique a ce qui a
ete montre et valide, jamais une version divergente recalculee a part.
Idempotent : TRUNCATE puis INSERT dans une seule transaction.
"""

import psycopg2
import psycopg2.extras

from nutrition_kb.agent.build_food_keywords import build_vocabulary
from nutrition_kb.db import DSN

LANG = "fr"


def main() -> int:
    vocabulary = build_vocabulary()
    keywords = sorted(vocabulary["kept"])

    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE kb.food_keyword")
                psycopg2.extras.execute_batch(
                    cur,
                    "INSERT INTO kb.food_keyword (keyword, lang) VALUES (%s, %s)",
                    [(kw, LANG) for kw in keywords],
                )
    finally:
        conn.close()

    print(f"[seed_food_keywords] {len(keywords)} mot(s)-cle(s) charge(s) dans kb.food_keyword.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
