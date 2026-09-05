"""Detection de la FORME de la question (ranking vs advice), par regles.

Version MINIMALE et volontairement grossiere : deux valeurs seulement. Les
formes plus fines (fact, comparaison...) viendront APRES avoir observe
l'agent tourner en pratique -- pas devinees a l'avance sur un jeu de
questions imaginaires.

Pas de cache ici (contrairement a detect_nutrient/detect_food) : les
marqueurs sont une liste Python figee, pas une table chargee depuis la DB --
rien de couteux a mettre en cache.

LIMITE CONNUE, assumee pour cette version minimale : 'salé' et 'sucré' se
normalisent (accents retires) en 'sale' et 'sucre'. 'sale' collide avec le
mot francais "sale" (dirty) ; 'sucre' collide avec le nom du nutriment
"sucre". Consequence : "cette assiette est sale" ou "combien de sucre dans
le riz" sont classes 'ranking' aujourd'hui, ce qui n'est pas exactement le
sens voulu. Assume pour l'instant (cf. brief), verrouille par un test dedie
pour qu'un futur changement soit une decision, pas une surprise.
"""

import re

from nutrition_kb.agent.normalize import normalize

RANKING_MARKERS = [
    "le plus",
    "le moins",
    "plus de",
    "moins de",
    "riche en",
    "pauvre en",
    "trop de",
    "beaucoup de",
    "sale",  # 'salé' normalise -- cf. limite connue ci-dessus
    "sucre",  # 'sucré' normalise -- cf. limite connue ci-dessus
    "quel aliment",
]


def detect_form(question: str) -> str:
    normalized_question = normalize(question)
    for marker in RANKING_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", normalized_question):
            return "ranking"
    return "advice"
