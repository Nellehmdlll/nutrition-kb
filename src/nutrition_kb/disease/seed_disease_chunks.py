"""Peuple kb.disease_chunk a partir des fiches OMS (.txt), decoupees en
sections par parse_who_fact_sheet.parse_file.

Idempotent comme rag/generate_chunks.py (TRUNCATE + reload) : le TEXTE est
regenere a chaque lancement, l'EMBEDDING est un chantier separe et
incremental (embed_disease_chunks.py) -- meme partage des responsabilites
que gold.chunk/embed_chunks.py, pour la meme raison (l'embedding coute cher
a recalculer, le texte ne coute rien).
"""

from pathlib import Path

import psycopg2
import psycopg2.extras

from nutrition_kb.db import DSN
from nutrition_kb.disease.parse_who_fact_sheet import parse_file

ROOT_DIR = Path(__file__).resolve().parents[3]
SOURCES_DIR = ROOT_DIR / "data" / "raw" / "sources"

SOURCE_ID = "OMS_2024"

# Titres de section VERIFIES A LA MAIN contre le fichier source -- cf.
# docstring de parse_who_fact_sheet.parse_sections sur pourquoi ce n'est
# jamais devine par heuristique sur un contenu de sante.
#
# "Action de l'OMS" et "Références bibliographiques" n'apparaissent PLUS
# dans OMS_diabete_2024.txt (fichier deja nettoye de ces deux sections --
# perimetre institutionnel et bibliographie brute, pas du contenu educatif).
# EXCLUDE reste present (vide) pour que le contrat de parse_file() -- lister
# ICI ce qui doit etre ecarte si jamais une future fiche les reintroduit --
# soit explicite plutot qu'implicite.
DIABETE_ALL_TITLES = [
    "Principaux faits",
    "Vue d’ensemble",
    "Symptômes",
    "Diabète de type 1",
    "Diabète de type 2",
    "Diabète gestationnel",
    "Intolérance au glucose et altération de la glycémie à jeun",
    "Prévention",
    "Diagnostic et traitement",
]
DIABETE_EXCLUDE: list = []

HYPERTENSION_ALL_TITLES = [
    "L’essentiel",
    "Généralités",
    "Facteurs de risque",
    "Symptômes",
    "Traitement",
    "Prévention",
    "Complications d’une hypertension non maîtrisée",
    "Prévalence de l’hypertension",
]
HYPERTENSION_EXCLUDE: list = []

DISEASES = {
    "diabete": (SOURCES_DIR / "OMS_diabete_2024.txt", DIABETE_ALL_TITLES, DIABETE_EXCLUDE),
    "hypertension": (SOURCES_DIR / "OMS_hypertension_2024.txt", HYPERTENSION_ALL_TITLES, HYPERTENSION_EXCLUDE),
}


def seed_disease(cur, disease: str, path: Path, all_titles: list, exclude: list) -> int:
    if not all_titles or not path.exists() or not path.read_text(encoding="utf-8").strip():
        print(f"[disease] {disease:13} ignore -- {path.name} absent, vide, ou titres de section pas encore verifies")
        return 0

    sections = parse_file(path, all_titles, exclude=exclude)
    rows = [(disease, title, content, SOURCE_ID) for title, content in sections.items()]
    psycopg2.extras.execute_batch(
        cur,
        "INSERT INTO kb.disease_chunk (disease, section, content, source_id) VALUES (%s, %s, %s, %s)",
        rows,
    )
    return len(rows)


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE kb.disease_chunk")
                for disease, (path, all_titles, exclude) in DISEASES.items():
                    n = seed_disease(cur, disease, path, all_titles, exclude)
                    print(f"[disease] {disease:13} {n} section(s) chargee(s)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
