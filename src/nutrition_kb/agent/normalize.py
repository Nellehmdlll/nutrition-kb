"""Normalisation de texte pour le routeur (comparaison synonyme <-> question).

Appliquee des DEUX cotes (synonymes stockes, question utilisateur) pour
qu'une simple egalite de chaines suffise ensuite -- pas de LIKE/regex
approximatif dans detect_nutrient.

LIMITE CONNUE, non traitee ici volontairement : ni la ponctuation ni les
espaces multiples/irreguliers ne sont normalises (ex. "sel  -  sodium"
garde ses espaces doubles et son tiret). Sans consequence tant que tous les
synonymes sont des mots uniques (cf. detect_nutrient, matching par mot
entier). Le jour ou un synonyme MULTI-MOTS apparait (ex. "riche en fibres"),
cette fonction devra probablement collapser les espaces/la ponctuation pour
que la comparaison reste fiable -- a traiter a ce moment-la, pas maintenant.
"""

import unicodedata


def normalize(text: str) -> str:
    text = text.strip().lower()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
