"""Interface de chat Streamlit pour l'agent -- appelle run_llm_agent()
DIRECTEMENT (import Python), jamais Ollama en direct.

Toute la securite de l'agent (court-circuit medical, barriere SQL,
garde-fou anti-invention -- cf. docstring de nutrition_kb.agent.llm_agent)
passe par run_llm_agent(). Cette interface ne fait qu'AFFICHER : elle ne
contourne jamais l'agent pour parler au LLM ou a la base directement.

PREREQUIS avant de lancer :
  - PostgreSQL doit tourner (les outils lisent kb.*/gold.chunk).
  - Ollama doit tourner, avec le modele llama3.1:8b deja tire.

Lancement :
    streamlit run app/streamlit_app.py
"""

import psycopg2
import requests
import streamlit as st

from nutrition_kb.agent.llm_agent import run_llm_agent

st.set_page_config(page_title="Assistant nutritionnel", page_icon="🥗")

st.title("Assistant nutritionnel")
st.caption(
    "Informations sur la composition des aliments, à partir de la table "
    "FAO/INFOODS WAFCT 2019. Ne remplace pas un professionnel de santé."
)

# history : passe tel quel a run_llm_agent(question, history=...) pour le
# multi-tours ("et le soumbala ?") -- format brut (roles user/assistant/tool),
# PAS ce qui est affiche a l'ecran (cf. display, distinct expres).
if "history" not in st.session_state:
    st.session_state.history = None

# display : une entree par tour VISIBLE (question posee, reponse rendue +
# sa trace d'outils) -- separe de `history` pour ne jamais montrer a
# l'utilisateur les messages internes 'tool' (JSON brut) qui alimentent le
# LLM d'un tour a l'autre.
if "display" not in st.session_state:
    st.session_state.display = []


def _render_trace(trace: list) -> None:
    if not trace:
        st.write("Aucun outil appelé pour cette réponse.")
        return
    for call in trace:
        st.markdown(f"**Outil : `{call['tool']}`**")
        st.json(call["arguments"])
        result = call["result"]
        if "error" in result:
            st.write(f"Résultat : erreur — {result['error']}")
        elif "rows" in result:
            st.write(f"Résultat : {len(result['rows'])} ligne(s)")
        elif "hits" in result:
            st.write(f"Résultat : {len(result['hits'])} chunk(s)")


for turn in st.session_state.display:
    with st.chat_message(turn["role"]):
        st.write(turn["content"])
        if turn["role"] == "assistant" and "trace" in turn:
            with st.expander("Détails techniques (outils appelés)"):
                _render_trace(turn["trace"])

question = st.chat_input("Posez votre question sur un aliment...")

if question:
    st.session_state.display.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("L'assistant réfléchit..."):
            try:
                response_text, trace, new_history = run_llm_agent(
                    question, history=st.session_state.history
                )
                st.session_state.history = new_history
            except psycopg2.OperationalError:
                response_text = (
                    "Impossible de me connecter à la base de données PostgreSQL. "
                    "Vérifie qu'elle tourne, puis réessaie."
                )
                trace = []
            except requests.exceptions.ConnectionError:
                response_text = (
                    "Impossible de me connecter à Ollama (http://localhost:11434). "
                    "Vérifie qu'il tourne (`ollama serve`), puis réessaie."
                )
                trace = []

        st.write(response_text)
        with st.expander("Détails techniques (outils appelés)"):
            _render_trace(trace)

    st.session_state.display.append(
        {"role": "assistant", "content": response_text, "trace": trace}
    )
