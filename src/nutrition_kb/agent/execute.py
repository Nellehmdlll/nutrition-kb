"""La glue entre le routeur (DECIDE) et les outils (EXECUTENT).

route() ne touche AUCUN outil : il rend une RoutingDecision pure a partir de
regles sur le texte. execute() prend cette decision et appelle le bon outil
(query_sql ou search_vector). Separation volontaire : remplacer route() par
un LLM plus tard ne doit toucher a rien ici, et inversement changer un outil
ne doit jamais toucher au routeur.

N'ECRIT PAS la reponse en langage naturel : ExecutionResult porte des
donnees structurees (FoodValueRow, ChunkHit), la mise en mots vient apres,
dans une couche separee.
"""

from dataclasses import dataclass
from typing import Any

import psycopg2

from nutrition_kb.agent.router import RoutingDecision
from nutrition_kb.agent.tools import query_sql, search_vector
from nutrition_kb.db import DSN

# ENERC est le seul tagname avec plusieurs unites en base (kJ ET kcal, cf.
# sql/schema.sql / kb.component -- la FAO le declare deux fois). kcal est le
# defaut choisi : c'est l'unite qu'on emploie a l'oral ("kcal"), pas le kJ
# scientifique. Decision assumee, pas deduite -- documentee ici, pas ailleurs.
DEFAULT_ENERGY_UNIT = "kcal"

# Toujours 'desc' pour l'instant : les questions de classement captees par
# detect_form ("le plus", "riche en"...) demandent presque toujours un
# maximum. "le moins" / "pauvre en" -> 'asc' viendra quand detect_form saura
# distinguer les deux sens (cf. docs/limitations.md, limite n2).
DEFAULT_ORDER = "desc"


@dataclass
class ExecutionResult:
    kind: str  # 'referral' | 'clarify' | 'no_result' | 'sql_result' | 'vector_result'
    data: Any
    reason: str


def resolve_unit(tagname: str, conn=None) -> str:
    """Renvoie l'unite a utiliser pour `tagname`, depuis kb.component --
    source de verite UNIQUE (pas de table nouvelle, pas de valeur en dur
    dispersee ailleurs).

    Un seul enregistrement pour ce tagname -> son unite. Plusieurs (cas
    ENERC) -> DEFAULT_ENERGY_UNIT.

    conn injectable : execute() ouvre UNE connexion et la fait suivre a
    resolve_unit() ET query_sql() plutot que d'en ouvrir une par appel.
    """
    own_conn = conn is None
    if own_conn:
        conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT unit FROM kb.component WHERE tagname = %s", (tagname,))
            units = [row[0] for row in cur.fetchall()]
    finally:
        if own_conn:
            conn.close()
    if len(units) == 1:
        return units[0]
    return DEFAULT_ENERGY_UNIT


def execute(decision: RoutingDecision) -> ExecutionResult:
    if decision.action == "medical_referral":
        # Aucun outil touche : securite avant tout, cf. router.py etape 1.
        return ExecutionResult(
            kind="referral",
            data=None,
            reason=decision.reason,
        )

    if decision.action == "clarify":
        # Aucun outil touche : rien d'identifie par le routeur, cf. router.py etape 2.
        return ExecutionResult(kind="clarify", data=None, reason=decision.reason)

    if decision.action == "vector":
        hits = search_vector(decision.question)
        if not hits:
            return ExecutionResult(
                kind="no_result",
                data=[],
                reason="aucun chunk sous le seuil de confiance -- rien de fiable a renvoyer",
            )
        return ExecutionResult(kind="vector_result", data=hits, reason=decision.reason)

    # decision.action == "sql"

    # Trou n1 : forme 'ranking' mais aucun nutriment nomme (ex. "le plus
    # sale", cf. docs/limitations.md limite n1). Pas de colonne sur laquelle
    # classer -> clarify, pas un crash.
    if not decision.nutrients:
        return ExecutionResult(
            kind="clarify",
            data=None,
            reason=(
                "forme 'ranking' mais aucun nutriment identifie -- "
                "cf. docs/limitations.md, limite n1"
            ),
        )

    tagname = decision.nutrients[0]
    note = ""
    # Trou n2 : plusieurs nutriments nommes -> on traite le premier pour
    # cette v1, et on le SIGNALE plutot que de choisir en silence.
    if len(decision.nutrients) > 1:
        note = f" (plusieurs nutriments detectes {decision.nutrients} -- seul '{tagname}' traite pour cette v1)"

    # Une seule connexion pour les deux appels (resolve_unit + query_sql) --
    # pas une par appel.
    conn = psycopg2.connect(DSN)
    try:
        unit = resolve_unit(tagname, conn=conn)
        rows = query_sql("top_by_nutrient", tagname=tagname, unit=unit, limit=5, order=DEFAULT_ORDER, conn=conn)
    finally:
        conn.close()
    return ExecutionResult(
        kind="sql_result",
        data=rows,
        reason=f"classement {tagname} ({unit}), ordre={DEFAULT_ORDER}{note}",
    )
