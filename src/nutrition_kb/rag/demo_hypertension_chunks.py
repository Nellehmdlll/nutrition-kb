"""Genere et affiche les chunks 'hypertension' pour une liste d'aliments.

Usage:
    python -m nutrition_kb.rag.demo_hypertension_chunks
    python -m nutrition_kb.rag.demo_hypertension_chunks 01_172 01_188

Sans argument, utilise les 4 aliments-temoins (plat calcule, provenances
mixtes, ratio non defini, cas simple).
"""

import os
import sys

import psycopg2
import psycopg2.extras

from nutrition_kb.rag.chunks import render_hypertension_chunk

DEFAULT_FOOD_CODES = ["01_172", "01_188", "11_013", "05_016"]

DSN = os.environ.get(
    "NUTRITION_KB_DSN",
    "postgresql://nutrition:nutrition@localhost:5432/nutrition_kb",
)


def main() -> int:
    # Certaines consoles Windows (cp1252/cp936) plantent sur les accents.
    # On force l'UTF-8 en sortie, quel que soit le terminal.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    food_codes = sys.argv[1:] or DEFAULT_FOOD_CODES

    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM gold.v_food_hypertension WHERE food_code = ANY(%s)",
        (food_codes,),
    )
    rows = {r["food_code"]: r for r in cur.fetchall()}
    conn.close()

    missing = [c for c in food_codes if c not in rows]
    if missing:
        print(f"Code(s) introuvable(s) dans gold.v_food_hypertension : {missing}", file=sys.stderr)

    for code in food_codes:
        if code not in rows:
            continue
        print(f"=== {code} ===")
        print(render_hypertension_chunk(rows[code]))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
