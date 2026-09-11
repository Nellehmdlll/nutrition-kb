"""Decoupe une fiche d'information OMS (.txt) en sections, TELLES QUELLES.

Pas d'heuristique de detection de titre : les titres de section sont fournis
EXPLICITEMENT par l'appelant (verifies a la main contre le fichier source,
cf. DIABETE_SECTIONS dans seed_disease_chunks.py) -- pour un contenu de
sante, un heuristique qui se trompe de decoupage est un risque qu'on ne
prend pas.

Le contenu de chaque section est copie tel quel (paragraphes et sauts de
ligne internes preserves, rien de reformule) -- cf. kb_disease_chunk.sql.
"""

from pathlib import Path
from typing import Sequence


def parse_sections(
    text: str,
    all_section_titles: Sequence[str],
    exclude: Sequence[str] = (),
) -> dict:
    """Renvoie {titre_section: contenu}, sections de `exclude` retirees.

    IMPORTANT : `all_section_titles` doit lister TOUS les titres reellement
    presents dans le texte, dans l'ordre -- y compris ceux qu'on va exclure
    ensuite (ex. "Action de l'OMS"). Sans son titre pour marquer sa propre
    frontiere, une section exclue serait silencieusement AVALEE par la
    section precedente au lieu d'etre retiree (ex. "Diagnostic et
    traitement" engloutirait tout "Action de l'OMS" si ce dernier n'etait
    pas dans `all_section_titles`).

    Le texte avant le premier titre connu (titre de la fiche, ex. « Diabète »
    tout seul en haut du fichier) est ignore : ce n'est pas une section.
    """
    lines = text.splitlines()
    boundaries = [i for i, line in enumerate(lines) if line.strip() in all_section_titles]

    sections = {}
    for idx, start in enumerate(boundaries):
        title = lines[start].strip()
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        body_lines = lines[start + 1 : end]
        # Ne retire que le vide en debut/fin -- les sauts de ligne internes
        # (entre paragraphes OMS) restent tels quels : c'est la mise en
        # forme d'origine, pas une reformulation.
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        sections[title] = "\n".join(body_lines)

    for title in exclude:
        sections.pop(title, None)
    return sections


def parse_file(path, all_section_titles: Sequence[str], exclude: Sequence[str] = ()) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    return parse_sections(text, all_section_titles, exclude=exclude)
