"""Charge data/silver/*.parquet dans PostgreSQL, via COPY (jamais d'INSERT ligne a ligne).

Deux ecarts assumes entre silver et le schema kb, tous deux voulus par le DDL :

  - food_value : les lignes value_status='NOT_DETERMINED' sont exclues au
    chargement. Le schema n'a meme pas ce label dans l'ENUM value_status --
    l'absence est reconstruite par v_food_nutrient_grid (CROSS JOIN), pas
    stockee. C'est la couche silver qui garde tout ; la couche kb normalise.
  - food.category_id : resolu via une jointure sur une table TEMP (le TEXT
    'category' de silver n'a pas de sens comme cle etrangere stable).

Apres chaque chargement, on verifie que le nombre de lignes inserees
correspond au nombre attendu -- un INNER JOIN qui ne matche pas silencieusement
une partie des lignes ne doit pas passer inapercu.
"""

import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2

ROOT_DIR = Path(__file__).resolve().parents[3]
SILVER_DIR = ROOT_DIR / "data" / "silver"

DSN = os.environ.get(
    "NUTRITION_KB_DSN",
    "postgresql://nutrition:nutrition@localhost:5432/nutrition_kb",
)

SOURCE_ID = "WAFCT_2019"


class LoadCountMismatchError(RuntimeError):
    """Le nombre de lignes chargees ne correspond pas au nombre attendu."""


def _copy_df(cur, df: pd.DataFrame, table: str, columns: list[str]) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, columns=columns, na_rep="")
    buf.seek(0)
    cols_sql = ", ".join(columns)
    cur.copy_expert(f"COPY {table} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)


def _assert_row_count(cur, table: str, expected: int) -> None:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    (actual,) = cur.fetchone()
    if actual != expected:
        raise LoadCountMismatchError(
            f"{table} : {actual} ligne(s) chargee(s), {expected} attendue(s)."
        )


def load_component(cur) -> None:
    df = pd.read_parquet(SILVER_DIR / "component.parquet")
    df["max_decimals"] = df["max_decimals"].replace("", None)
    columns = ["tagname", "unit", "name_en", "name_fr", "alternatives", "denominator", "max_decimals"]
    _copy_df(cur, df, "kb.component", columns)
    _assert_row_count(cur, "kb.component", len(df))


def load_food_category(cur) -> None:
    df = pd.read_parquet(SILVER_DIR / "food_category.parquet")
    names = df[["category"]].drop_duplicates().rename(columns={"category": "name_en"})
    _copy_df(cur, names, "kb.food_category", ["name_en"])
    _assert_row_count(cur, "kb.food_category", len(names))


def load_food(cur) -> None:
    df = pd.read_parquet(SILVER_DIR / "food.parquet")
    stg = df.rename(columns={"_source_row": "source_row"})[
        ["food_code", "name_en", "name_fr", "name_scientific", "biblio_source", "category", "source_row"]
    ]

    cur.execute(
        """
        CREATE TEMP TABLE stg_food (
            food_code TEXT, name_en TEXT, name_fr TEXT, name_scientific TEXT,
            biblio_source TEXT, category TEXT, source_row INTEGER
        ) ON COMMIT DROP
        """
    )
    _copy_df(cur, stg, "stg_food", list(stg.columns))

    cur.execute(
        """
        INSERT INTO kb.food
            (food_code, name_en, name_fr, name_scientific, category_id, biblio_source, source_id, source_row)
        SELECT s.food_code, s.name_en, s.name_fr, NULLIF(s.name_scientific, ''), fc.category_id,
               NULLIF(s.biblio_source, ''), %s, s.source_row
        FROM stg_food s
        JOIN kb.food_category fc ON fc.name_en = s.category
        """,
        (SOURCE_ID,),
    )
    _assert_row_count(cur, "kb.food", len(df))


def load_food_value(cur) -> None:
    df = pd.read_parquet(SILVER_DIR / "food_value.parquet")
    # NOT_DETERMINED = absence de ligne dans ce schema (cf. docstring du module).
    df = df[df["value_status"] != "NOT_DETERMINED"].copy()
    # dtype nullable (pas .apply(int)+None : pandas reinfere alors la colonne
    # en float64 et "1" redevient "1.0" au moment du CSV).
    df["stat_n"] = df["stat_n"].astype("Int64")
    df["source_id"] = SOURCE_ID
    df = df.rename(columns={"value_status": "status", "_source_row": "source_row"})

    columns = [
        "food_code", "tagname", "unit", "value", "status", "provenance",
        "stat_n", "stat_sd", "stat_min", "stat_max", "stat_median",
        "source_id", "source_row",
    ]
    _copy_df(cur, df, "kb.food_value", columns)
    _assert_row_count(cur, "kb.food_value", len(df))


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                load_component(cur)
                load_food_category(cur)
                load_food(cur)
                load_food_value(cur)
    except LoadCountMismatchError as e:
        conn.rollback()
        print(f"[load] ECHEC : {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("[load] component, food_category, food, food_value charges avec succes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
