"""Lancement local de l'AGENT LLM : le function calling d'Ollama comme
cerveau de l'agent -- second chemin, en plus du routeur par regles (voir
scripts/try_agent.py pour celui-ci, conserve tel quel comme filet de
secours).

Mode debug : affiche, pour chaque question, quel(s) outil(s) le LLM a
appele(s) et avec quels arguments -- pour VOIR son raisonnement, pas
seulement sa reponse finale.

PREREQUIS :
  - PostgreSQL doit tourner (les outils lisent kb.nutrient_synonym,
    kb.component, kb.food_value, gold.chunk). Si besoin :

        docker start nutrition-kb-pg-v3

  - Ollama doit tourner, avec le modele llama3.1:8b deja tire :

        ollama serve          (si le service n'est pas deja lance)
        ollama pull llama3.1:8b

Usage :
    python scripts/try_llm_agent.py
"""

import sys

# La console Windows n'utilise pas toujours l'UTF-8 par defaut : sans ceci,
# print() plante (UnicodeEncodeError) des qu'un texte contient un accent --
# meme correction que scripts/try_agent.py et scripts/try_router.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json

import psycopg2
import requests

from nutrition_kb.agent.llm_agent import run_llm_agent


def _print_trace(trace: list) -> None:
    if not trace:
        print("(aucun outil appele)")
        return
    for call in trace:
        print(f"  -> outil : {call['tool']}")
        print(f"     arguments : {json.dumps(call['arguments'], ensure_ascii=False)}")
        result = call["result"]
        if "error" in result:
            print(f"     resultat : ERREUR -- {result['error']}")
        elif "rows" in result:
            print(f"     resultat : {len(result['rows'])} ligne(s)")
        elif "hits" in result:
            print(f"     resultat : {len(result['hits'])} chunk(s)")


def run_interactive() -> None:
    print("Agent LLM (Ollama, llama3.1:8b) -- tape une question, 'quit' pour sortir.\n")
    history = None
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question or question.lower() in ("quit", "exit"):
            break

        try:
            response_text, trace, history = run_llm_agent(question, history=history)
        except psycopg2.OperationalError:
            print(
                "\nImpossible de se connecter a PostgreSQL.\n"
                "Demarre le conteneur puis reessaie :\n\n"
                "    docker start nutrition-kb-pg-v3\n"
            )
            sys.exit(1)
        except requests.exceptions.ConnectionError:
            print(
                "\nImpossible de se connecter a Ollama (http://localhost:11434).\n"
                "Verifie qu'il tourne, puis reessaie :\n\n"
                "    ollama serve\n"
            )
            sys.exit(1)

        print("[debug -- outils appeles]")
        _print_trace(trace)
        print("\n[reponse]")
        print(response_text)
        print()


if __name__ == "__main__":
    run_interactive()
