"""Peuple kb.food_local_lexicon avec la colonne locaux_externes du fichier
de triangulation manuelle (vocabulaire_aliments_burkina_independant.xlsx).

Ces termes ne sont PAS des mots-cles de detection (pas dans food_keyword) :
aucun food_code derriere eux pour l'instant, c'est un lexique de reference
pour un futur appariement vernaculaire (mooré et autres), pas un vocabulaire
actif du routeur. Idempotent : TRUNCATE puis INSERT dans une seule transaction.
"""

import psycopg2
import psycopg2.extras

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

XLSX_PATH = r"C:\Users\1\Downloads\vocabulaire_aliments_burkina_independant.xlsx"
NOTE = "colonne locaux_externes, fichier utilisateur (triangulation manuelle)"


def load_terms() -> list:
    import pandas as pd

    vocab = pd.read_excel(XLSX_PATH, sheet_name="vocabulaire")
    raw_terms = [str(x).strip() for x in vocab["locaux_externes"].dropna().tolist()]
    # normalize() (minuscules, sans accents) pour rester coherent avec le
    # reste du projet -- meme si cette table n'est pas encore interrogee par
    # un detecteur, elle le sera un jour, et on ne veut pas deux formes
    # d'un meme terme (accentuee/non accentuee) coexister par accident.
    return sorted({normalize(t) for t in raw_terms})


def main() -> int:
    terms = load_terms()

    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE kb.food_local_lexicon")
                psycopg2.extras.execute_batch(
                    cur,
                    "INSERT INTO kb.food_local_lexicon (term, lang, note) VALUES (%s, %s, %s)",
                    [(t, "und", NOTE) for t in terms],
                )
    finally:
        conn.close()

    print(f"[seed_food_local_lexicon] {len(terms)} terme(s) charge(s) dans kb.food_local_lexicon.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
