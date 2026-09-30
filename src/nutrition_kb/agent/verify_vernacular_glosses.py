"""Verifie en base la presence d'aliments correspondant a des gloses
vernaculaires (moore -> francais/botanique) -- Temps 2 de l'appariement
vernaculaire (cf. Temps 1 : match_food_local_lexicon.py).

Different de Temps 1 : Temps 1 decouvre des candidats par recoupement
mecanique (mots du terme lui-meme). Ici, les mots-cles a chercher viennent
d'une GLOSE fournie par l'utilisateur (connaissance linguistique externe,
ex. "bikalga" = graines fermentees d'oseille de Guinee) -- le script ne fait
que verifier methodiquement si kb.food contient quelque chose sous ces
mots-cles, il n'invente ni la glose ni la correspondance.

PROPOSITION uniquement : ne peuple rien, n'ecrit rien en base. Meme
discipline que Temps 1 -- la machine cherche, l'humain valide.
"""

import re
from pathlib import Path

import psycopg2

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

OUT_PATH = "vernacular_gloss_verification_review.txt"

# Chaque terme : (glose donnee par l'utilisateur, mots-cles a chercher OU
# None si volontairement pas cherche -- cf. voaga/scarabe).
TERMS = [
    ("arzantiga", "moringa", ["moringa", "oleifera"]),
    ("benga", "haricot / niebe", ["niebe", "haricot"]),
    ("bulvaka", "corete potagere", ["corete", "corchorus"]),
    ("bikalga", "graines fermentees d'oseille (Hibiscus sabdariffa)",
     ["oseille", "hibiscus", "datou", "fermente"]),
    ("kagha", "detar (Detarium senegalense/microcarpum)", ["detar", "detarium"]),
    ("voaga", "kapok (Bombax costatum)", None),  # deja verifie absent (cf. echange precedent)
    ("weda", "fruit de liane (Saba senegalensis)", ["liane", "saba", "landolphia"]),
    ("dolo", "biere de mil/sorgho", ["dolo", "biere", "sorgho"]),
    ("scarabe", "sens inconnu", None),
]


def _word_pattern(word: str) -> str:
    stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
    return rf"\b{re.escape(stem)}s?\b"


def _load_foods(cur) -> list:
    cur.execute("SELECT food_code, name_fr, name_scientific FROM kb.food ORDER BY food_code")
    return cur.fetchall()


def _search_keyword(keyword: str, foods: list) -> list:
    """food_code dont name_fr OU name_scientific contient ce mot-cle (mot
    entier). Renvoie (food_code, name_fr, champ_touche)."""
    pattern = _word_pattern(normalize(keyword))
    hits = []
    for food_code, name_fr, name_scientific in foods:
        if name_fr and re.search(pattern, normalize(name_fr)):
            hits.append((food_code, name_fr, "name_fr"))
        elif name_scientific and re.search(pattern, normalize(name_scientific)):
            hits.append((food_code, name_fr, "name_scientific"))
    return hits


def verify_all(cur) -> list:
    foods = _load_foods(cur)
    results = []
    for term, gloss, keywords in TERMS:
        if keywords is None:
            results.append((term, gloss, None, {}))
            continue
        per_keyword = {}
        for kw in keywords:
            per_keyword[kw] = _search_keyword(kw, foods)
        results.append((term, gloss, keywords, per_keyword))
    return results


def render_report(results: list) -> str:
    lines = [
        "Verification des gloses vernaculaires contre kb.food -- Temps 2",
        "PROPOSITION UNIQUEMENT -- rien n'est ecrit en base. A valider a la main.",
        "=" * 78,
    ]
    for term, gloss, keywords, per_keyword in results:
        lines.append("")
        lines.append(f"'{term}' = {gloss}")
        if keywords is None:
            lines.append("    NON CHERCHE (cf. brief) -- marque 'absent WAFCT' ou 'sens inconnu, non apparie'.")
            continue

        any_hit = False
        for kw in keywords:
            hits = per_keyword[kw]
            if not hits:
                lines.append(f"    mot-cle '{kw}' : 0 resultat")
                continue
            any_hit = True
            lines.append(f"    mot-cle '{kw}' : {len(hits)} resultat(s)")
            for food_code, name_fr, field in hits:
                lines.append(f"        {food_code}  {name_fr}  (trouve via {field})")

        if not any_hit:
            lines.append("    => ABSENT de la WAFCT sous ces mots-cles (aucun, tous testes).")

    return "\n".join(lines)


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            results = verify_all(cur)
    finally:
        conn.close()

    report = render_report(results)
    Path(OUT_PATH).write_text(report, encoding="utf-8")
    print(f"[verify] rapport ecrit dans {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
