"""Genere les chunks RAG (3 angles) pour tous les aliments et les charge dans gold.chunk.

Idempotent : TRUNCATE puis COPY dans une seule transaction (echec => rollback,
jamais une table a moitie vide, meme discipline que le loader silver->kb).
L'embedding n'est pas rempli ici -- etape separee, une fois le modele choisi.
"""

import io
import os

import pandas as pd
import psycopg2
import psycopg2.extras

from nutrition_kb.rag.chunks import (
    render_diabetes_chunk,
    render_hypertension_chunk,
    render_macros_chunk,
)

DSN = os.environ.get(
    "NUTRITION_KB_DSN",
    "postgresql://nutrition:nutrition@localhost:5432/nutrition_kb",
)
SOURCE_ID = "WAFCT_2019"

ANGLES = [
    ("hypertension", "gold.v_food_hypertension", render_hypertension_chunk),
    ("diabetes", "gold.v_food_diabetes", render_diabetes_chunk),
    ("macros", "gold.v_food_base", render_macros_chunk),
]


def _copy_df(cur, df: pd.DataFrame, table: str, columns: list) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, columns=columns, na_rep="")
    buf.seek(0)
    cols_sql = ", ".join(columns)
    cur.copy_expert(f"COPY {table} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)


def generate_all_chunks(cur) -> dict:
    counts = {}
    records = []

    for angle, view, render in ANGLES:
        angle_cur = cur.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        angle_cur.execute(f"SELECT * FROM {view}")
        rows = angle_cur.fetchall()
        angle_cur.close()

        for row in rows:
            records.append(
                {
                    "food_code": row["food_code"],
                    "angle": angle,
                    "content": render(row),
                    "source_id": SOURCE_ID,
                }
            )
        counts[angle] = len(rows)

    df = pd.DataFrame.from_records(records, columns=["food_code", "angle", "content", "source_id"])
    cur.execute("TRUNCATE TABLE gold.chunk")
    _copy_df(cur, df, "gold.chunk", ["food_code", "angle", "content", "source_id"])
    return counts


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                counts = generate_all_chunks(cur)
    finally:
        conn.close()

    total = sum(counts.values())
    print(f"[chunks] {total} chunks generes et charges dans gold.chunk :")
    for angle, n in counts.items():
        print(f"    {angle:15} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
