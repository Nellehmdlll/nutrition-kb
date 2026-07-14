"""Couche SILVER : transforme le raw (grille de cellules) en tables typées.

Produit 4 tables :
    component      — le dictionnaire des nutriments (feuille 02)
    food_category  — les 14 groupes d'aliments
    food           — les 1028 aliments
    food_value     — LE CŒUR : une ligne par (aliment × nutriment × unité), en modèle EAV

--------------------------------------------------------------------------
LE POINT DÉLICAT : le motif « carry-forward » (report de contexte)
--------------------------------------------------------------------------
La feuille 06 est PLATE et SÉQUENTIELLE. Le lien entre un aliment et ses lignes
statistiques n'est écrit NULLE PART : il est PORTÉ PAR LA POSITION.

    ligne 240 │ 01_172 │ Baling béinré │ 66.3 │ [0.2] │ ...   ← l'ALIMENT
    ligne 241 │ SD     │               │  2.1 │       │ ...   ┐
    ligne 245 │ n      │               │    3 │       │ ...   ├─ ses STATS
    ligne 246 │ Non-African data │      │      │  oa   │ ...  ┘  ← appartient à 01_172
    ligne 247 │ 01_173 │ ...                                   ← l'aliment SUIVANT

On ne peut donc pas « chercher » la ligne Non-African data : il faut LIRE DANS
L'ORDRE et se souvenir du dernier aliment croisé (`current_food`).

COROLLAIRE : l'ordre des lignes est SACRÉ. Trier la feuille détruirait la seule
information qui relie un aliment à ses stats. C'est pourquoi la couche raw
conserve `_source_row` — c'est la garantie de pouvoir restaurer cet ordre.

--------------------------------------------------------------------------
LA CLÉ EST (tagname, unit), PAS tagname SEUL
--------------------------------------------------------------------------
La FAO documente "ENERC" (Energy) DEUX FOIS en feuille 02 : une ligne avec
unit=kJ et sa formule, une ligne avec unit=kcal et SA formule (différente).
Ce sont deux entrées légitimes du dictionnaire, pas un doublon à jeter.
Un dedup/set sur tagname seul les fusionne en silence et perd la formule kcal.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pandas as pd

from nutrition_kb.transform.value import (
    ParsedValue,
    Provenance,
    parse_value,
    resolve_provenance,
)

ROOT_DIR = Path(__file__).resolve().parents[3]
EXTRACTED_DIR = ROOT_DIR / "data" / "raw" / "extracted" / "wafct_2019"
SILVER_DIR = ROOT_DIR / "data" / "silver"

# --- Géométrie de la feuille 06 (constantes, pas des nombres magiques) --------

COL_CODE = 0
COL_NAME_EN = 1
COL_NAME_FR = 2
COL_NAME_SCI = 3
COL_BIBLIO = 4
FIRST_COMPONENT_COL = 5  # les tagnames commencent à EDIBLE1

ROW_HEADER_EN = 1  # porte aussi l'unité : 'Energy\n(kJ)'
ROW_HEADER_FR = 2
ROW_TAGNAMES = 3  # la ligne qui porte les tagnames INFOODS : notre clé de jointure

OA_LABEL = "Non-African data"
OA_MARK = "oa"
STAT_LABELS = {"SD", "min", "max", "median", "n"}
ALL_STAT_LABELS = STAT_LABELS | {OA_LABEL}

# Unité absente de l'en-tête (facteurs de conversion sans dimension, ex. EDIBLE1,
# XFA) : même jeton que la feuille 02 utilise pour ces lignes, pour rester
# comparable lors de la validation croisée.
_NO_UNIT = "-"
_UNIT_SUFFIX = re.compile(r"\n\(([^()]+)\)\s*$")

# Même convention que value._TRACE_TOKEN, côté cellules de stats.
_STAT_TRACE_TOKEN = "tr"


class RowKind(Enum):
    HEADER = "HEADER"      # les 3 premières lignes
    CATEGORY = "CATEGORY"  # code présent, nom absent  -> un groupe d'aliments
    FOOD = "FOOD"          # code présent, nom présent -> un aliment
    STAT = "STAT"          # col_0 ∈ {SD, min, max, median, n, Non-African data}
    EMPTY = "EMPTY"        # ligne entièrement vide


class MalformedSheetError(RuntimeError):
    """La feuille ne respecte pas la structure attendue. On PLANTE, on ne devine pas."""


def classify_row(row: pd.Series, source_row: int) -> RowKind:
    """Détermine la nature d'une ligne. Fonction PURE : testable isolément."""
    if source_row <= ROW_TAGNAMES:
        return RowKind.HEADER

    code = _clean(row.get(f"col_{COL_CODE}"))
    name = _clean(row.get(f"col_{COL_NAME_EN}"))

    if code in ALL_STAT_LABELS:
        return RowKind.STAT
    if code and name:
        return RowKind.FOOD
    if code and not name:
        return RowKind.CATEGORY
    if not code and not name:
        return RowKind.EMPTY

    # Aucun cas ne colle -> on refuse de deviner.
    raise MalformedSheetError(f"Ligne {source_row} inclassable : code={code!r} name={name!r}")


def _clean(v) -> str:
    """Normalise une cellule raw (str | None | NaN) en chaîne propre."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


# --- Le dictionnaire des composants (feuille 02) ------------------------------


def canonical_tagname(raw_tagname: str) -> tuple[str, list[str]]:
    """Le dictionnaire encode des ALTERNATIVES : 'FAT or [FATCE]'.

    Sens : « ce composant est de préférence FAT ; si la valeur provient d'une
    autre méthode analytique, c'est FATCE ». Le tagname canonique est le premier.

        'FAT or [FATCE]'  ->  ('FAT', ['FATCE'])
        'NA'              ->  ('NA',  [])
    """
    parts = [p.strip() for p in re.split(r"\s+or\s+", raw_tagname.strip())]
    canonical = parts[0]
    alternatives = [p.strip("[]") for p in parts[1:]]
    return canonical, alternatives


def build_components(df02: pd.DataFrame) -> pd.DataFrame:
    """Table `component` : le référentiel des nutriments. PK = (tagname, unit)."""
    rows = []
    for _, r in df02.iterrows():
        if int(r["_source_row"]) == 1:  # ligne d'en-tête du dictionnaire
            continue
        raw_tag = _clean(r.get("col_2"))
        if not raw_tag or raw_tag == "INFOODS tagname":  # en-tête répété dans le corps
            continue
        canonical, alternatives = canonical_tagname(raw_tag)
        rows.append(
            {
                "tagname": canonical,
                "unit": _clean(r.get("col_3")),
                "alternatives": ";".join(alternatives),
                "name_en": _clean(r.get("col_0")),
                "name_fr": _clean(r.get("col_1")),
                "denominator": _clean(r.get("col_4")),
                "max_decimals": _clean(r.get("col_6")),
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["tagname", "unit"])


def validate_tagnames(components: pd.DataFrame, tagnames: dict[int, tuple[str, str]]) -> None:
    """Deux gardes indépendantes entre les colonnes NV et le dictionnaire.

    a) Appartenance -- chaque (tagname, unit) utilisé existe-t-il au dictionnaire ?
       Fait aussi office de validation croisée ligne-1/feuille-02 : si l'unité
       lue dans l'en-tête NV ne correspond pas à celle déclarée en feuille 02,
       la paire n'existe pas dans le dictionnaire et cette garde le voit.
    b) Unicité -- chaque paire n'apparaît-elle qu'une seule fois parmi les
       colonnes NV ? Un set() ne peut PAS voir un doublon : il faut un Counter.
    """
    known_pairs = set(zip(components["tagname"], components["unit"]))
    used_pairs = list(tagnames.values())

    orphans = sorted(set(used_pairs) - known_pairs)
    if orphans:
        raise MalformedSheetError(
            "Paire(s) (tagname, unit) presente(s) dans les NV mais absente(s) du "
            f"dictionnaire (ou unite incoherente entre ligne 1 et feuille 02) : {orphans}"
        )

    duplicated = {pair: n for pair, n in Counter(used_pairs).items() if n > 1}
    if duplicated:
        raise MalformedSheetError(
            f"Paire(s) (tagname, unit) portee(s) par plusieurs colonnes des NV : {duplicated}"
        )


# --- Le cœur : parcours de la feuille NV --------------------------------------


@dataclass
class _FoodBuffer:
    """Accumulateur pour l'aliment en cours de lecture (le `current_food`)."""

    code: str
    name_en: str
    name_fr: str
    name_sci: str
    biblio: str
    category: str
    source_row: int
    values: pd.Series
    oa_row: pd.Series | None = None
    stats: dict[str, pd.Series] = field(default_factory=dict)

    @property
    def has_oa_row(self) -> bool:
        return self.oa_row is not None


def _extract_unit(header_text: str) -> str:
    """Unité = parenthèse finale précédée d'un saut de ligne : 'Energy\\n(kJ)' -> 'kJ'.

    Certaines colonnes (facteurs de conversion : EDIBLE1/2, XFA, XN) n'ont pas
    ce motif dans l'en-tête -> _NO_UNIT, le même jeton que la feuille 02 utilise
    pour elles (vérifié : les 4 y sont déclarées unit='-').
    """
    match = _UNIT_SUFFIX.search(header_text)
    return match.group(1).strip() if match else _NO_UNIT


def read_tagnames(df: pd.DataFrame) -> dict[int, tuple[str, str]]:
    """{index de colonne -> (tagname INFOODS, unité)}.

    Le tagname vient de la ligne 3 ; l'unité de la ligne 1 (en-tête anglais).
    """
    tag_row = df[df["_source_row"] == ROW_TAGNAMES].iloc[0]
    header_row = df[df["_source_row"] == ROW_HEADER_EN].iloc[0]
    tags: dict[int, tuple[str, str]] = {}
    for col in df.columns:
        if not col.startswith("col_"):
            continue
        idx = int(col.split("_")[1])
        if idx < FIRST_COMPONENT_COL:
            continue
        tag = _clean(tag_row[col])
        if not tag:
            continue
        unit = _extract_unit(_clean(header_row[col]))
        tags[idx] = (tag, unit)
    return tags


def validate_food_value_uniqueness(values_df: pd.DataFrame) -> None:
    """Dernière ligne de défense : (food_code, tagname, unit) doit être une clé.

    Si la FAO ajoute un jour une 3e colonne ENERC (ex. kcal recalculé
    autrement), on le sait à l'ingestion -- pas quand un pivot en aval se met
    silencieusement à sommer deux valeurs incompatibles.
    """
    if values_df.empty:
        return
    dup_mask = values_df.duplicated(subset=["food_code", "tagname", "unit"], keep=False)
    if dup_mask.any():
        dupes = (
            values_df.loc[dup_mask, ["food_code", "tagname", "unit"]]
            .drop_duplicates()
            .to_dict("records")
        )
        raise MalformedSheetError(
            f"{len(dupes)} cle(s) (food_code, tagname, unit) dupliquee(s) dans "
            f"food_value : {dupes[:20]}"
        )


def build_silver(df_nv: pd.DataFrame, df02: pd.DataFrame, emit_not_determined: bool = True):
    """Parcourt la feuille NV et produit (components, categories, foods, food_values).

    `emit_not_determined` : faut-il écrire une ligne pour les cellules VIDES ?
      True  -> la grille est explicite : « on sait qu'on ne sait pas » est une info.
      False -> table plus légère, mais l'absence devient ambiguë (vide ? oublié ?).
    DÉCISION : True. En santé, « non déterminé » doit être dit, pas déduit du silence.
    """
    tagnames = read_tagnames(df_nv)
    components = build_components(df02)
    validate_tagnames(components, tagnames)

    df_nv = df_nv.sort_values("_source_row")  # l'ordre est SACRÉ (cf. docstring)

    current_food: _FoodBuffer | None = None
    current_category: str = ""
    foods: list[_FoodBuffer] = []
    categories: list[dict] = []

    # ---- PASSE UNIQUE, de haut en bas : le motif « carry-forward » ----
    for _, row in df_nv.iterrows():
        source_row = int(row["_source_row"])
        kind = classify_row(row, source_row)

        if kind in (RowKind.HEADER, RowKind.EMPTY):
            continue

        if kind == RowKind.CATEGORY:
            current_category = _clean(row[f"col_{COL_CODE}"])
            categories.append({"category": current_category, "_source_row": source_row})
            current_food = None  # une catégorie clôt l'aliment précédent
            continue

        if kind == RowKind.FOOD:
            current_food = _FoodBuffer(
                code=_clean(row[f"col_{COL_CODE}"]),
                name_en=_clean(row[f"col_{COL_NAME_EN}"]),
                name_fr=_clean(row[f"col_{COL_NAME_FR}"]),
                name_sci=_clean(row[f"col_{COL_NAME_SCI}"]),
                biblio=_clean(row[f"col_{COL_BIBLIO}"]),  # ex. « calc. from recipe »
                category=current_category,
                source_row=source_row,
                values=row,
            )
            foods.append(current_food)
            continue

        if kind == RowKind.STAT:
            label = _clean(row[f"col_{COL_CODE}"])
            if current_food is None:
                # Une stat sans aliment = fichier mal formé. On PLANTE.
                raise MalformedSheetError(f"Ligne stat {label!r} (ligne {source_row}) sans aliment.")
            if label == OA_LABEL:
                current_food.oa_row = row
            else:
                current_food.stats[label] = row
            continue

    # ---- Émission de food_value : une ligne par (aliment × tagname × unit) ----
    values: list[dict] = []
    for food in foods:
        for col_idx, (tagname, unit) in tagnames.items():
            col = f"col_{col_idx}"
            raw = food.values.get(col)
            raw = None if (raw is None or (isinstance(raw, float) and pd.isna(raw))) else str(raw)

            marked_oa = bool(food.has_oa_row and _clean(food.oa_row.get(col)) == OA_MARK)
            provenance = resolve_provenance(food.has_oa_row, marked_oa)

            parsed: ParsedValue = parse_value(raw, provenance)

            if parsed.status.name == "NOT_DETERMINED" and not emit_not_determined:
                continue

            values.append(
                {
                    "food_code": food.code,
                    "tagname": tagname,
                    "unit": unit,
                    "value": parsed.value,
                    "value_status": parsed.status.value,
                    "provenance": parsed.provenance.value,
                    "stat_n": _num(food.stats.get("n"), col),
                    "stat_sd": _num(food.stats.get("SD"), col),
                    "stat_min": _num(food.stats.get("min"), col),
                    "stat_max": _num(food.stats.get("max"), col),
                    "stat_median": _num(food.stats.get("median"), col),
                    "_source_row": food.source_row,
                }
            )

    foods_df = pd.DataFrame(
        [
            {
                "food_code": f.code,
                "name_en": f.name_en,
                "name_fr": f.name_fr,
                "name_scientific": f.name_sci,
                "biblio_source": f.biblio,
                "category": f.category,
                "_source_row": f.source_row,
            }
            for f in foods
        ]
    )
    values_df = pd.DataFrame(values)
    validate_food_value_uniqueness(values_df)

    return components, pd.DataFrame(categories), foods_df, values_df


def _num(stat_row: pd.Series | None, col: str) -> float | None:
    """Lit une cellule de stat : numérique, vide, ou 'tr' (même convention que
    value.py). Tout le reste est une corruption inattendue -> on plante, on ne
    l'avale pas silencieusement (vérifié sur la vraie feuille 06 : les seuls
    échecs de parsing sur 66 542 cellules de stats étaient des 'tr')."""
    if stat_row is None:
        return None
    v = stat_row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    text = str(v).strip()
    if text == _STAT_TRACE_TOKEN:
        return None
    try:
        return float(text)
    except ValueError:
        raise MalformedSheetError(
            f"Cellule de stat illisible (colonne {col!r}, ni nombre ni 'tr') : {v!r}"
        ) from None


# --- Point d'entrée : data/raw/extracted/ -> data/silver/ ---------------------


def load_silver_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    df_nv = pd.read_parquet(EXTRACTED_DIR / "06_nv_stat_57_per_100g_ep.parquet")
    df02 = pd.read_parquet(EXTRACTED_DIR / "02_components.parquet")
    return df_nv, df02


def main() -> int:
    df_nv, df02 = load_silver_inputs()

    try:
        components, categories, foods, values = build_silver(df_nv, df02)
    except MalformedSheetError as e:
        print(f"[silver] ECHEC : {e}", file=sys.stderr)
        return 1

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    components.to_parquet(SILVER_DIR / "component.parquet", index=False)
    categories.to_parquet(SILVER_DIR / "food_category.parquet", index=False)
    foods.to_parquet(SILVER_DIR / "food.parquet", index=False)
    values.to_parquet(SILVER_DIR / "food_value.parquet", index=False)

    print(f"[silver] component     : {components.shape}")
    print(f"[silver] food_category : {categories.shape}")
    print(f"[silver] food          : {foods.shape}")
    print(f"[silver] food_value    : {values.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
