"""Routeur de l'agent : arbre de decision, routage par regles.

Cascade en ORDRE STRICT (l'ordre encode la priorite, ne pas reordonner) :
  1. signal medical (securite)         -> medical_referral, STOP
  2. aucun aliment/nutriment identifie -> clarify, STOP
  3. forme de la question              -> sql (ranking) ou vector (advice)

Chaque etape est un STOP : les etapes suivantes ne sont MEME PAS calculees
si une precedente a deja tranche (ex. foods/nutrients ne sont jamais
calcules si un signal medical est detecte -- pas juste ignores).

LIMITE CONNUE de l'ordre strict : une question de forme 'ranking' qui ne
nomme AUCUN aliment/nutriment reconnu (ex. "quel aliment est le plus
salé" -- 'salé' n'est ni un food_keyword ni un nutrient_synonym, retire
plus tot pour collision avec "sale"=dirty) est bloquee en 'clarify' a
l'etape 2, sans jamais atteindre detect_form. Assume, pas un bug : sans
nutriment nomme, le futur outil SQL n'aurait de toute facon aucune colonne
sur laquelle trier.

N'implemente PAS les outils (requete SQL, recherche vectorielle) ni la
generation de reponse : uniquement la DECISION de vers quoi router.
"""

from dataclasses import dataclass

from nutrition_kb.agent.detect_food import detect_food
from nutrition_kb.agent.detect_form import detect_form
from nutrition_kb.agent.detect_medical_signal import detect_medical_signal, find_medical_signal_detail
from nutrition_kb.agent.detect_nutrient import detect_nutrient


@dataclass
class RoutingDecision:
    question: str  # la question d'origine -- execute() en a besoin (ex. search_vector)
    action: str  # 'medical_referral' | 'sql' | 'vector' | 'clarify'
    foods: list
    nutrients: list
    form: str
    reason: str  # tracabilite : POURQUOI cette decision


def route(question: str) -> RoutingDecision:
    # 1. Signal medical -- priorite absolue, avant tout le reste. STOP.
    if detect_medical_signal(question):
        detail = find_medical_signal_detail(question)
        return RoutingDecision(
            question=question,
            action="medical_referral",
            foods=[],
            nutrients=[],
            form="",
            reason=f"signal medical: {detail}",
        )

    # 2. Rien identifie -- ni aliment ni nutriment. STOP.
    foods = detect_food(question)
    nutrients = detect_nutrient(question)
    if not foods and not nutrients:
        return RoutingDecision(
            question=question,
            action="clarify",
            foods=[],
            nutrients=[],
            form="",
            reason="aucun aliment ni nutriment identifie",
        )

    # 3. Forme de la question -> sql (classement) ou vector (conseil general).
    form = detect_form(question)
    action = "sql" if form == "ranking" else "vector"
    return RoutingDecision(
        question=question,
        action=action,
        foods=foods,
        nutrients=nutrients,
        form=form,
        reason=f"aliments={foods}, nutriments={nutrients}, forme={form}",
    )
