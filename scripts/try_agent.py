"""Lancement local de l'AGENT COMPLET : route() -> execute() -> render_response().

Contrairement a scripts/try_router.py (qui montre uniquement la DECISION),
ce script montre le texte final tel qu'il serait affiche a l'utilisateur --
avec render_response(), qui est un gabarit Python PROVISOIRE (pas de LLM).

PREREQUIS : le conteneur PostgreSQL doit tourner (route()/execute() lisent
kb.nutrient_synonym, kb.food_keyword, kb.component, kb.food_value et
gold.chunk en base). Si besoin :

    docker start nutrition-kb-pg-v3

Usage :
    python scripts/try_agent.py
"""

import sys

# La console Windows n'utilise pas toujours l'UTF-8 par defaut : sans ceci,
# print() plante (UnicodeEncodeError) des qu'un texte contient un accent ou
# des guillemets francais -- soit presque chaque reponse de cet agent.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg2

from nutrition_kb.agent.execute import execute
from nutrition_kb.agent.render import render_response
from nutrition_kb.agent.router import route


def run_interactive() -> None:
    print("Agent complet -- tape une question, 'quit' (ou Ctrl+D) pour sortir.\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in ("quit", "exit"):
            break

        try:
            decision = route(question)
            result = execute(decision)
        except psycopg2.OperationalError:
            print(
                "\nImpossible de se connecter a PostgreSQL.\n"
                "Demarre le conteneur puis reessaie :\n\n"
                "    docker start nutrition-kb-pg-v3\n"
            )
            sys.exit(1)

        print(f"[{result.kind}]")
        print(render_response(result))
        print()


if __name__ == "__main__":
    run_interactive()
