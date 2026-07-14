"""Test de fidelite Parquet <-> source .xlsx, par un chemin de lecture
independant d'openpyxl (zipfile + xml.etree) pour ne pas valider le pipeline
avec ses propres outils.

Tolerance connue et documentee : deux representations d'un meme nombre
peuvent differer en texte (ex. XML "2.40" vs Parquet "2.4") sans etre une
vraie divergence. On les compte a part via float(a) == float(b) plutot que
de les decouvrir un jour comme un "bug" mysterieux.

Autre piege documente ici : on lit le cote Parquet avec pyarrow (pas
pandas.read_parquet). Pandas 3 a introduit un dtype "str" par defaut qui
represente les valeurs manquantes par NaN au lieu de None/pd.NA -- ce n'est
pas un defaut du fichier (verifie au niveau Arrow : is_valid=False, valeur
reelle None), juste un choix de lecture de pandas. Le contourner ici evite
un faux positif ; le connaitre evite une frayeur cote consommateur de la
donnee.
"""

import json
import random
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from nutrition_kb.ingest import raw as ingest_raw

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
SAMPLES_PER_SHEET = 40  # stratifie : chaque feuille est verifiee, pas juste les plus grosses
SEED = 20260714  # fixe : reproductibilite du test d'un run a l'autre


def _col_letters_to_index(letters: str) -> int:
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch.upper()) - ord("A") + 1)
    return index


def _split_ref(ref: str) -> tuple[str, int]:
    i = 0
    while i < len(ref) and ref[i].isalpha():
        i += 1
    return ref[:i], int(ref[i:])


class RawWorkbookReader:
    """Lecture minimale d'un .xlsx directement depuis son XML, sans openpyxl."""

    def __init__(self, xlsx_path: Path):
        self._zip = zipfile.ZipFile(xlsx_path)
        self._shared_strings = self._load_shared_strings()
        self._sheet_files = self._load_sheet_files()
        self._cell_cache: dict[str, dict[tuple[int, int], object]] = {}

    def _load_shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        root = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        strings = []
        for si in root.findall("m:si", NS):
            texts = [t.text or "" for t in si.iter(f"{{{NS['m']}}}t")]
            strings.append("".join(texts))
        return strings

    def _load_sheet_files(self) -> dict[str, str]:
        wb_root = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels_root = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.get("Id"): rel.get("Target") for rel in rels_root}
        mapping = {}
        for sheet in wb_root.find("m:sheets", NS):
            rid = sheet.get(f"{{{NS['r']}}}id")
            target = rid_to_target[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            mapping[sheet.get("name")] = target
        return mapping

    def _load_sheet(self, sheet_name: str) -> dict[tuple[int, int], object]:
        if sheet_name in self._cell_cache:
            return self._cell_cache[sheet_name]
        root = ET.fromstring(self._zip.read(self._sheet_files[sheet_name]))
        cells: dict[tuple[int, int], object] = {}
        for c_el in root.iter(f"{{{NS['m']}}}c"):
            col_letters, row_num = _split_ref(c_el.get("r"))
            col_idx = _col_letters_to_index(col_letters)
            cell_type = c_el.get("t")
            v_el = c_el.find("m:v", NS)
            is_el = c_el.find("m:is", NS)

            if cell_type == "s" and v_el is not None:
                value = self._shared_strings[int(v_el.text)]
            elif cell_type == "inlineStr" and is_el is not None:
                value = "".join(t.text or "" for t in is_el.iter(f"{{{NS['m']}}}t"))
            elif cell_type == "b" and v_el is not None:
                value = "True" if v_el.text == "1" else "False"
            elif v_el is not None:
                value = v_el.text
            else:
                value = None
            cells[(row_num, col_idx)] = value
        self._cell_cache[sheet_name] = cells
        return cells

    def read_cell(self, sheet_name: str, row: int, col: int) -> str | None:
        return self._load_sheet(sheet_name).get((row, col))

    def non_null_cell_count(self, sheet_name: str) -> int:
        return sum(1 for v in self._load_sheet(sheet_name).values() if v is not None)


def _numeric_equal(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def test_random_cell_fidelity():
    extracted_dir = ingest_raw.EXTRACTED_DIR / "wafct_2019"
    index_file = extracted_dir / "sheet_index.json"
    if not index_file.exists():
        pytest.skip(
            "Aucune extraction trouvee. Lancez d'abord : "
            "python -m nutrition_kb.ingest.raw"
        )

    index = json.loads(index_file.read_text(encoding="utf-8"))
    xlsx_path = ingest_raw.SOURCES_DIR / index["source_file"]
    reader = RawWorkbookReader(xlsx_path)

    sheets_meta = index["sheets"]
    rng = random.Random(SEED)

    table_cache: dict[str, pa.Table] = {}

    def load_table(sheet_meta: dict) -> pa.Table:
        fname = sheet_meta["parquet_file"]
        if fname not in table_cache:
            table_cache[fname] = pq.read_table(extracted_dir / fname)
        return table_cache[fname]

    known_tolerance = []
    true_divergences = []
    per_sheet_counts: dict[str, int] = {}

    # Echantillonnage stratifie par feuille (pas pondere par taille) : un
    # tirage global pondere par nombre de cellules a deja produit un vrai bug
    # ici -- "01 Introduction" (104 cellules) n'a jamais ete tiree sur 500
    # echantillons face aux feuilles stats de 3812 lignes. Sans stratification,
    # le test "verifie tout" mais ne verifie en pratique que les 2 grosses
    # feuilles -- silencieusement, comme le raw qu'on essaie justement
    # de ne jamais laisser trier sans le dire.
    for sheet_meta in sheets_meta:
        total = sheet_meta["rows"] * sheet_meta["cols"]
        k = min(SAMPLES_PER_SHEET, total)
        flat_indices = rng.sample(range(total), k=k)
        per_sheet_counts[sheet_meta["sheet_name"]] = k

        table = load_table(sheet_meta)
        for flat_idx in flat_indices:
            row_pos, col_pos = divmod(flat_idx, sheet_meta["cols"])
            source_row = table.column("_source_row")[row_pos].as_py()
            parquet_value = table.column(f"col_{col_pos}")[row_pos].as_py()
            col_idx_xml = col_pos + 1

            raw_cell = reader.read_cell(sheet_meta["sheet_name"], source_row, col_idx_xml)
            expected = None if raw_cell is None else str(raw_cell)

            if expected == parquet_value:
                continue
            if _numeric_equal(expected, parquet_value):
                known_tolerance.append(
                    (sheet_meta["sheet_name"], source_row, col_idx_xml, expected, parquet_value)
                )
                continue
            true_divergences.append(
                (sheet_meta["sheet_name"], source_row, col_idx_xml, expected, parquet_value)
            )

    total_samples = sum(per_sheet_counts.values())
    unsampled = [name for name, n in per_sheet_counts.items() if n == 0]
    print(f"\n[fidelite] {total_samples} cellules echantillonnees (seed={SEED}), reparties sur {len(sheets_meta)} feuille(s) :")
    for name, n in per_sheet_counts.items():
        print(f"    {n:3d}  {name}")
    print(
        f"[fidelite] {len(known_tolerance)} tolerance connue (formatage numerique), "
        f"{len(true_divergences)} divergence(s) reelle(s)."
    )

    assert not unsampled, f"Feuille(s) jamais echantillonnee(s) : {unsampled}"
    assert not true_divergences, (
        f"{len(true_divergences)} divergence(s) non tolerees XML vs Parquet : "
        f"{true_divergences[:10]}"
    )


def test_completeness():
    """L'echantillonnage ci-dessus tire dans l'espace du Parquet : une cellule
    tronquee a l'extraction (ex. max_col sous-evalue si une ligne XML est plus
    courte que les autres) est structurellement invisible pour lui, puisqu'elle
    n'existe plus dans l'espace tire. Ce test ne sonde pas : il compte, en O(n),
    sur l'espace XML complet (independant de raw.py), et verifie qu'aucune
    cellule non vide n'a disparu en route. Corruption (valeurs justes ?) et
    omission (toutes presentes ?) sont deux proprietes distinctes ; celle-ci
    couvre la seconde."""
    extracted_dir = ingest_raw.EXTRACTED_DIR / "wafct_2019"
    index_file = extracted_dir / "sheet_index.json"
    if not index_file.exists():
        pytest.skip(
            "Aucune extraction trouvee. Lancez d'abord : "
            "python -m nutrition_kb.ingest.raw"
        )

    index = json.loads(index_file.read_text(encoding="utf-8"))
    xlsx_path = ingest_raw.SOURCES_DIR / index["source_file"]
    reader = RawWorkbookReader(xlsx_path)

    mismatches = []
    for sheet_meta in index["sheets"]:
        sheet_name = sheet_meta["sheet_name"]
        xml_count = reader.non_null_cell_count(sheet_name)

        table = pq.read_table(extracted_dir / sheet_meta["parquet_file"])
        data_cols = [c for c in table.column_names if not c.startswith("_")]
        parquet_count = sum(len(table) - table.column(c).null_count for c in data_cols)

        print(f"[completude] {sheet_name:45} xml={xml_count:6d}  parquet={parquet_count:6d}")
        if xml_count != parquet_count:
            mismatches.append((sheet_name, xml_count, parquet_count))

    assert not mismatches, (
        "Nombre de cellules non vides different entre XML et Parquet "
        f"(feuille, xml, parquet) : {mismatches}"
    )
