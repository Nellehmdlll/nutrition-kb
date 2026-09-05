"""Peuple kb.nutrient_synonym.

Les tagnames sont verifies contre kb.component AVANT toute ecriture (le
peuplement echoue bruyamment si un tagname n'existe pas -- jamais une
reference silencieusement fausse). Idempotent : TRUNCATE puis INSERT dans
une seule transaction (echec => rollback, jamais une table a moitie vide).
"""

import psycopg2
import psycopg2.extras

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

# (synonyme brut, tagname). La normalisation se fait dans build_seed_rows,
# pas ici : ecrire les accents tels qu'on les pense evite de se tromper en
# pre-normalisant a la main (et documente, en clair, le mot francais reel).
#
# PAS de 'salé' ici : sa forme normalisee 'sale' collide avec le mot
# francais courant "sale" (dirty) -> faux positifs sur NA pour toute
# question contenant ce mot sans rapport avec le sodium. 'salé' releve
# d'un jugement de magnitude ("cet aliment est-il salé ?"), pas d'une
# simple detection lexicale de nutriment -- il ira dans detect_form plus
# tard, pas ici.
RAW_SYNONYMS = [
    ("sel", "NA"),
    ("sodium", "NA"),
    ("sucre", "CHOAVLDF"),
    ("glucides", "CHOAVLDF"),
    ("sucré", "CHOAVLDF"),
    ("fibres", "FIBTG"),
    ("potassium", "K"),
    ("énergie", "ENERC"),
    ("calories", "ENERC"),
]


class SeedConflictError(RuntimeError):
    """Un synonyme normalise pointe vers plusieurs tagnames, ou un tagname est inconnu."""


def build_seed_rows(raw_synonyms, lang: str = "fr") -> list:
    """Normalise, deduplique, et refuse toute ambiguite reelle.

    Deux synonymes bruts qui normalisent vers la meme forme (ex. 'sucre' et
    'sucré') et pointent vers le MEME tagname -> une seule ligne (doublon
    inoffensif). Vers des tagnames DIFFERENTS -> erreur : c'est une vraie
    ambiguite, jamais tranchee en silence.
    """
    grouped: dict = {}
    for raw_synonym, tagname in raw_synonyms:
        norm = normalize(raw_synonym)
        grouped.setdefault(norm, set()).add(tagname)

    rows = []
    for norm, tagnames in sorted(grouped.items()):
        if len(tagnames) > 1:
            raise SeedConflictError(
                f"Synonyme normalise {norm!r} : tagnames en conflit {sorted(tagnames)}"
            )
        rows.append((norm, next(iter(tagnames)), lang))
    return rows


def verify_tagnames_exist(cur, tagnames) -> None:
    cur.execute("SELECT DISTINCT tagname FROM kb.component")
    known = {row[0] for row in cur.fetchall()}
    missing = sorted(set(tagnames) - known)
    if missing:
        raise SeedConflictError(f"Tagname(s) absent(s) de kb.component : {missing}")


def main() -> int:
    rows = build_seed_rows(RAW_SYNONYMS)
    tagnames = {tagname for _, tagname, _ in rows}

    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                verify_tagnames_exist(cur, tagnames)
                cur.execute("TRUNCATE TABLE kb.nutrient_synonym")
                psycopg2.extras.execute_batch(
                    cur,
                    "INSERT INTO kb.nutrient_synonym (synonym, tagname, lang) VALUES (%s, %s, %s)",
                    rows,
                )
    finally:
        conn.close()

    print(f"[seed] {len(rows)} synonyme(s) chargé(s) dans kb.nutrient_synonym :")
    for synonym, tagname, lang in rows:
        print(f"    {synonym!r:15} -> {tagname} ({lang})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
