"""Lancement local du routeur : voir l'arbre de decision tourner sur de
vraies questions, avant de brancher les outils (SQL, recherche vectorielle).

Ce script ne fait qu'APPELER route() et AFFICHER le resultat -- aucune
logique metier ici, tout vit dans nutrition_kb.agent.router et les
detecteurs qu'il appelle.

PREREQUIS : le conteneur PostgreSQL doit tourner (route() lit
kb.nutrient_synonym et kb.food_keyword en base via detect_nutrient/
detect_food). Si besoin :

    docker start nutrition-kb-pg-v3

(voir src/nutrition_kb/db.py pour le DSN et le port utilises -- le nom du
conteneur peut differer selon la machine, verifie avec "docker ps -a").

Usage :
    python scripts/try_router.py batch         # questions pre-remplies
    python scripts/try_router.py interactive   # boucle de saisie au clavier
    python scripts/try_router.py               # equivalent a "batch"
"""

import sys

# La console Windows n'utilise pas toujours l'UTF-8 par defaut : sans ceci,
# print() plante (UnicodeEncodeError) des qu'un texte contient un accent --
# decouvert en construisant scripts/try_agent.py (memes plantages possibles ici).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg2

from nutrition_kb.agent.router import route

# Une question par action possible, plus le cas-limite documente dans
# docs/limitations.md (adjectif de classement qui ne nomme aucun nutriment).
BATCH_QUESTIONS = [
    "ma glycemie est a 18",                    # medical_referral
    "glycemie 18, je mange du riz ?",          # medical_referral (priorite sur food)
    "raconte-moi ta journee",                  # clarify (rien reconnu)
    "quel aliment est le plus sale",           # clarify (limite connue, cf. docs/limitations.md)
    "quel aliment contient le plus de sodium", # sql (ranking)
    "le gombo est bon pour moi ?",             # vector (advice)
]


def print_decision(question: str, decision) -> None:
    print(f"Question : {question}")
    print(f"  action     : {decision.action}")
    print(f"  reason     : {decision.reason}")
    print(f"  foods      : {decision.foods}")
    print(f"  nutrients  : {decision.nutrients}")
    print(f"  form       : {decision.form!r}")
    print()


def route_or_explain(question: str):
    try:
        return route(question)
    except psycopg2.OperationalError:
        print(
            "\nImpossible de se connecter a PostgreSQL.\n"
            "Le routeur a besoin de kb.nutrient_synonym et kb.food_keyword en base.\n"
            "Demarre le conteneur puis reessaie :\n\n"
            "    docker start nutrition-kb-pg-v3\n"
        )
        sys.exit(1)


def run_batch() -> None:
    for question in BATCH_QUESTIONS:
        decision = route_or_explain(question)
        print_decision(question, decision)


def run_interactive() -> None:
    print("Mode interactif -- tape une question, 'quit' (ou Ctrl+D) pour sortir.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in ("quit", "exit"):
            break
        decision = route_or_explain(question)
        print_decision(question, decision)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "batch"
    if mode == "batch":
        run_batch()
    elif mode == "interactive":
        run_interactive()
    else:
        print(f"Mode inconnu : {mode!r}. Usage : batch | interactive")
        sys.exit(1)


if __name__ == "__main__":
    main()
