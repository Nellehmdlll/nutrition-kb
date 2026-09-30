"""Tri automatique des termes de kb.food_local_lexicon contre kb.food --
Temps 1 de l'appariement vernaculaire (cf. echange avec l'utilisateur).

NE PEUPLE RIEN : produit un rapport (candidats food_code par terme, classes
en 3 categories) pour validation humaine. Meme philosophie que
build_food_keywords.py -- la machine PROPOSE, l'humain DISPOSE. Un mauvais
appariement automatique et silencieux serait grave (un aliment prendrait le
nom d'un autre) : aucune ecriture en base ici, meme provisoire.

Correspondance sur MOT ENTIER (frontieres de mot), jamais sous-chaine brute
(evite que "ble" matche "faible"). Pour un terme de plusieurs mots (ex.
"feuilles de baobab"), TOUS les mots pleins doivent apparaitre (ET, pas OU)
dans le meme champ -- chercher "feuilles" seul remonterait des dizaines de
faux positifs (le mot est present dans une grande partie de kb.food), alors
qu'exiger "feuilles" ET "baobab" ensemble cible la bonne famille d'aliments
quel que soit l'ordre des mots dans name_fr.

Tolerance singulier/pluriel simple (mot final +/- 's') : le lexique et
kb.food n'accordent pas toujours en nombre le meme terme (ex. lexique
"chenilles", kb.food "Chenille de bambou..." au singulier) -- une regle
d'accord irreguliere resterait un angle mort assume, pas traite ici (echelle
trop faible -- 37 termes -- pour justifier plus qu'un accord regulier).
"""

import re
from pathlib import Path

import psycopg2

from nutrition_kb.agent.build_food_keywords import STOPWORDS_GRAMMAR
from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

OUT_PATH = "food_local_lexicon_match_review.txt"

# Au-dela de ce nombre de food_code candidats, le terme est trop generique
# pour qu'une liste soit exploitable (ex. un mot present dans des dizaines
# de noms) -- categorise AMBIGU plutot que de noyer la validation humaine
# sous des dizaines de candidats. Seuil arbitraire mais documente, a
# ajuster apres avoir vu le rapport reel si besoin.
AMBIGUOUS_THRESHOLD = 10


def _significant_words(term: str) -> list:
    """Tokenise un terme du lexique en mots pleins (mots vides retires,
    doublons retires en gardant l'ordre -- ex. "koura-koura" -> ["koura"],
    pas ["koura", "koura"])."""
    normalized = normalize(term)
    tokens = re.split(r"[^a-z0-9]+", normalized)
    seen = set()
    words = []
    for t in tokens:
        if t and t not in STOPWORDS_GRAMMAR and t not in seen:
            seen.add(t)
            words.append(t)
    return words


def _word_pattern(word: str) -> str:
    # Tolerance singulier/pluriel reguliere uniquement (cf. docstring module).
    stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
    return rf"\b{re.escape(stem)}s?\b"


def _load_foods(cur) -> list:
    cur.execute("SELECT food_code, name_fr, name_scientific FROM kb.food ORDER BY food_code")
    return cur.fetchall()


def _find_candidates(words: list, foods: list) -> list:
    """food_code dont name_fr OU name_scientific contient TOUS les mots
    significatifs du terme (mot entier, meme champ)."""
    patterns = [_word_pattern(w) for w in words]
    candidates = []
    for food_code, name_fr, name_scientific in foods:
        for field in (name_fr, name_scientific):
            if not field:
                continue
            norm_field = normalize(field)
            if all(re.search(p, norm_field) for p in patterns):
                candidates.append((food_code, name_fr))
                break
    return candidates


def classify_terms(cur) -> dict:
    cur.execute("SELECT term, lang, note FROM kb.food_local_lexicon ORDER BY term")
    terms = cur.fetchall()
    foods = _load_foods(cur)

    results = {"APPARIE_AUTO": [], "NON_APPARIE": [], "AMBIGU": []}
    for term, lang, note in terms:
        words = _significant_words(term)
        if not words:
            results["NON_APPARIE"].append((term, [], "aucun mot plein apres filtrage"))
            continue

        candidates = _find_candidates(words, foods)
        seen = set()
        deduped = []
        for fc, name in candidates:
            if fc not in seen:
                seen.add(fc)
                deduped.append((fc, name))

        if not deduped:
            results["NON_APPARIE"].append((term, words, None))
        elif len(deduped) > AMBIGUOUS_THRESHOLD:
            results["AMBIGU"].append((term, words, deduped))
        else:
            results["APPARIE_AUTO"].append((term, words, deduped))

    return results


def render_report(results: dict) -> str:
    total = sum(len(v) for v in results.values())
    lines = [
        f"Tri automatique de kb.food_local_lexicon contre kb.food -- {total} terme(s)",
        "PROPOSITION UNIQUEMENT -- rien n'est ecrit en base. A valider a la main.",
        "=" * 78,
        "",
        f"APPARIE_AUTO : {len(results['APPARIE_AUTO'])}",
        f"AMBIGU       : {len(results['AMBIGU'])}",
        f"NON_APPARIE  : {len(results['NON_APPARIE'])}",
        "",
        "=" * 78,
        f"APPARIE_AUTO ({len(results['APPARIE_AUTO'])}) -- candidats trouves, A VALIDER",
        "=" * 78,
    ]
    for term, words, candidates in results["APPARIE_AUTO"]:
        lines.append(f"\n'{term}'  (mots cherches : {', '.join(words)})")
        for fc, name in candidates:
            lines.append(f"    {fc}  {name}")

    lines += [
        "",
        "=" * 78,
        f"AMBIGU ({len(results['AMBIGU'])}) -- trop de candidats (> {AMBIGUOUS_THRESHOLD}), a examiner",
        "=" * 78,
    ]
    for term, words, candidates in results["AMBIGU"]:
        lines.append(f"\n'{term}'  (mots cherches : {', '.join(words)}) -- {len(candidates)} candidats")
        for fc, name in candidates[:5]:
            lines.append(f"    {fc}  {name}")
        if len(candidates) > 5:
            lines.append(f"    ... et {len(candidates) - 5} autre(s)")

    lines += [
        "",
        "=" * 78,
        f"NON_APPARIE ({len(results['NON_APPARIE'])}) -- glose manuelle, ou aliment absent de la WAFCT",
        "=" * 78,
    ]
    for term, words, reason in results["NON_APPARIE"]:
        extra = f"  ({reason})" if reason else ""
        lines.append(f"'{term}'  (mots cherches : {', '.join(words)}){extra}")

    return "\n".join(lines)


def main() -> int:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            results = classify_terms(cur)
    finally:
        conn.close()

    report = render_report(results)
    Path(OUT_PATH).write_text(report, encoding="utf-8")

    print(f"[match] rapport ecrit dans {OUT_PATH}")
    print(
        f"[match] APPARIE_AUTO={len(results['APPARIE_AUTO'])}  "
        f"AMBIGU={len(results['AMBIGU'])}  NON_APPARIE={len(results['NON_APPARIE'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
