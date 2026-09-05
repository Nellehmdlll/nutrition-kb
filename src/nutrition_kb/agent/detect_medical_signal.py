"""Detection d'un signal medical, par regles.

PLACEHOLDER DE SECURITE INCOMPLET. Detecte UNIQUEMENT un nombre associe a
l'un des mots-cles ('sucre','glycemie','glycémie','tension','taux') --
rien de plus. Ne tente PAS de deviner des symptomes, des noms de
medicaments, ou toute autre formulation d'une urgence medicale : ce serait
inventer une couverture qui n'existe pas. Cette fonction doit etre revue et
validee par un professionnel de sante AVANT tout enrichissement -- ne pas
etendre la liste de mots-cles ni la logique sans cette validation.

'glycemie' et 'glycémie' sont toutes les deux dans la liste brute (fidele au
brief), mais normalize() les rend identiques -- la forme accentuee est
redondante une fois normalisee, gardee ici pour ne rien retirer de ce qui a
ete demande.
"""

import re
from typing import Optional

from nutrition_kb.agent.normalize import normalize

MEDICAL_TRIGGER_WORDS = ["sucre", "glycemie", "glycémie", "tension", "taux"]


def find_medical_signal_detail(question: str) -> Optional[str]:
    """Rend un detail lisible ('mot-cle + valeur') si un signal est detecte, sinon None.

    Separee de detect_medical_signal (qui reste -> bool, cf. contrat) pour
    que route() puisse construire un reason= explicite sans dupliquer la
    logique de detection.
    """
    normalized_question = normalize(question)
    number_match = re.search(r"\d+", normalized_question)
    if not number_match:
        return None

    for word in MEDICAL_TRIGGER_WORDS:
        norm_word = normalize(word)
        if re.search(rf"\b{re.escape(norm_word)}\b", normalized_question):
            return f"mot-cle '{norm_word}', valeur '{number_match.group()}'"
    return None


def detect_medical_signal(question: str) -> bool:
    return find_medical_signal_detail(question) is not None
