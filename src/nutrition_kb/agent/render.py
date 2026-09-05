"""Generation de reponse MINIMALE (templates Python, PAS de LLM) -- PROVISOIRE.

Phrases a trous, pour voir l'agent tourner de bout en bout. On decidera
gabarit-vs-LLM APRES avoir observe l'agent complet en pratique -- pas devine
a l'avance.

RÈGLE ABSOLUE (sante) : render_response ne fait que REAGENCER ce que
`result` contient. Aucun chiffre, aucun conseil, aucune affirmation qui ne
soit pas deja dans les donnees. Si une info n'est pas dans `result`, elle
n'apparait PAS dans le texte produit. En particulier, le referral medical ne
touche JAMAIS a result.data : on ne melange pas alerte et conseil.

Reutilise format_number/qualifier_clause/SOURCE_LINE de rag.chunks : c'est
deja LA ou vit la regle "un chiffre n'est jamais nu sans son incertitude"
pour les chunks RAG -- la dupliquer ici serait le genre de divergence
silencieuse que le projet a deja rencontree ailleurs.
"""

from nutrition_kb.agent.execute import ExecutionResult
from nutrition_kb.rag.chunks import format_number, qualifier_clause


def render_response(result: ExecutionResult) -> str:
    if result.kind == "referral":
        return _render_referral(result)
    if result.kind == "clarify":
        return _render_clarify(result)
    if result.kind == "no_result":
        return _render_no_result(result)
    if result.kind == "sql_result":
        return _render_sql_result(result)
    if result.kind == "vector_result":
        return _render_vector_result(result)
    raise ValueError(f"kind inconnu : {result.kind!r}")


def _render_referral(result: ExecutionResult) -> str:
    # Message FIXE, sans aucune interpolation de result.reason ou result.data :
    # c'est le message le plus important de l'app, il ne doit jamais se
    # retrouver melange a un chiffre ou un conseil nutritionnel. Ne dramatise
    # pas, ne minimise pas -- reconnait, oriente, s'arrete la.
    return (
        "Ta question mentionne une donnée de santé (par exemple une valeur de "
        "glycémie ou de tension). Je suis un assistant de nutrition : je ne fais "
        "pas de diagnostic médical et je ne suis pas en mesure d'interpréter "
        "cette valeur.\n\n"
        "Merci d'en parler à un professionnel de santé (médecin, infirmier, "
        "centre de santé). Je ne peux pas proposer de conseil nutritionnel sur "
        "cette base tant qu'un professionnel n'a pas évalué la situation."
    )


def _render_clarify(result: ExecutionResult) -> str:
    return (
        "Je n'ai pas identifié d'aliment ou de nutriment assez précis dans ta "
        "question pour te répondre. Peux-tu reformuler ? Par exemple : "
        "« quel aliment contient le plus de sodium ? » ou "
        "« le gombo est-il bon pour la tension ? »"
    )


def _render_no_result(result: ExecutionResult) -> str:
    return (
        "Je n'ai pas trouvé d'information fiable sur ce sujet dans mes sources "
        "actuelles. Essaie de reformuler ta question en citant un aliment précis."
    )


def _render_sql_result(result: ExecutionResult) -> str:
    rows = result.data
    if not rows:
        return "Aucun aliment avec une valeur mesurée n'a été trouvé pour ce nutriment."

    lines = []
    for i, row in enumerate(rows, start=1):
        clause = f"{i}. {row.name_fr} : environ {format_number(row.value)} {row.unit}"
        qualifier = qualifier_clause(row.status, row.provenance)
        if qualifier:
            clause += f" ({qualifier})"
        lines.append(clause)

    # Peut y avoir plusieurs sources en theorie (une seule aujourd'hui,
    # WAFCT_2019 partout) -- on cite ce qui est reellement dans les donnees,
    # pas un nom suppose.
    sources = sorted({row.source_id for row in rows})
    source_line = "Source : " + ", ".join(sources) + "."

    return "\n".join(lines) + "\n\n" + source_line


def _render_vector_result(result: ExecutionResult) -> str:
    # Les chunks contiennent deja une prose autoportante qui se termine par sa
    # propre citation de source (cf. rag/chunks.py, SOURCE_LINE) : on les
    # presente TELS QUELS, sans reformuler -- reformuler risquerait
    # d'introduire une erreur dans un contenu deja verifie.
    return "\n\n".join(hit.content for hit in result.data)
