"""Peuple kb.food_local_match -- UNIQUEMENT les correspondances vernaculaires
VALIDEES A LA MAIN (Temps 3 de l'appariement vernaculaire).

N'insere RIEN d'automatique : chaque ligne ci-dessous vient d'une decision
humaine explicite (cf. rapports match_food_local_lexicon.py /
verify_vernacular_glosses.py, Temps 1 et 2 -- ces scripts PROPOSENT, ce
fichier-ci est la ou l'humain a DISPOSE). Idempotent (TRUNCATE + reload),
meme discipline que seed_nutrient_synonyms.py/seed_food_keywords.py.

'chenilles' est deliberement ABSENT de cette liste : candidat a 3 food_code
(bambou/mopane/mopane-conserve) jamais tranche -- cf. echange avec
l'utilisateur, "a confirmer". Ne pas l'ajouter sans validation explicite.
"""

import psycopg2
import psycopg2.extras

from nutrition_kb.db import DSN

# (term, food_code, lang, status, note)
ROWS = [
    # --- Vernaculaires moore apparies ---------------------------------------
    ("arzantiga", "04_011", "moore", "matched", None),
    ("benga", "03_004", "moore", "matched", None),
    ("bulvaka", "04_038", "moore", "matched", None),
    ("kagha", "05_007", "moore", "matched", None),
    ("weda", "05_011", "moore", "matched", None),
    ("dolo", "12_003", "moore", "matched", None),
    ("dolo", "12_004", "moore", "matched", None),
    # --- Vernaculaires moore NON apparies ------------------------------------
    ("voaga", None, "moore", "absent_wafct", "kapok (Bombax costatum) absent de la WAFCT"),
    ("bikalga", None, "moore", "absent_wafct",
     "graines fermentées oseille; seule la version crue (06_030) existe, composition différente"),
    ("scarabe", None, "moore", "unknown", "sens non identifié"),
    # --- Locutions francaises validees (Temps 1) -----------------------------
    ("feuilles de baobab", "04_001", "fr", "matched", None),
    ("feuilles de gombo", "04_004", "fr", "matched", None),
    ("feuilles de manioc", "04_008", "fr", "matched", None),
    ("feuilles de niébé", "04_010", "fr", "matched", None),
    ("feuilles de patate douce", "04_059", "fr", "matched", None),
    ("feuilles de tamarin", "04_019", "fr", "matched", None),
    ("graine de courge", "06_038", "fr", "matched", None),
    ("graine d'oseille", "06_030", "fr", "matched", None),
    ("noix de karité", "05_044", "fr", "matched", None),
    ("sauterelle", "07_074", "fr", "matched", None),
    ("soumbala", "03_042", "fr", "matched", None),
]


def seed(cur) -> int:
    cur.execute("TRUNCATE TABLE kb.food_local_match")
    psycopg2.extras.execute_batch(
        cur,
        "INSERT INTO kb.food_local_match (term, food_code, lang, status, note) VALUES (%s, %s, %s, %s, %s)",
        ROWS,
    )
    return len(ROWS)


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                n = seed(cur)
    finally:
        conn.close()
    print(f"[seed] kb.food_local_match : {n} ligne(s) chargee(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
