"""Rendu de chunks RAG (angle par angle) a partir des vues gold.

Un chunk est de la prose autoportante, jamais un dump cle:valeur -- c'est ce
que le modele d'embedding lit. Regles dures (heritees de tout le projet) :
un chiffre n'est jamais nu sans son incertitude, un NULL n'est jamais un vide
silencieux, la provenance est par nutriment, et la source termine toujours
le texte pour rester citable.
"""

from typing import Mapping, Optional

SOURCE_LINE = "Source : FAO/INFOODS WAFCT 2019."


def _format_number(value) -> str:
    value = float(value)
    if value == int(value):
        return str(int(value))
    # 1 decimale d'abord (lisible : "0.2", "3.3") ; si ca arrondit a 0 pour
    # une valeur reellement non nulle (ex. ratio 2/162 = 0.012), on affine
    # jusqu'a obtenir un chiffre non nul plutot que d'ecrire "0" a la place
    # d'un vrai petit nombre -- indiscernable d'un zero mesure.
    for decimals in (1, 2, 3, 4):
        text = f"{value:.{decimals}f}"
        if float(text) != 0:
            return text.rstrip("0").rstrip(".")
    return f"{value:.4f}"


def _french_category(category: str) -> str:
    # 'Cereals and their products/Céréales et produits dérivés' -> partie FR.
    return category.split("/")[-1].strip() if "/" in category else category


def _qualifier_clause(status: Optional[str], provenance: Optional[str]) -> str:
    bits = []
    if status == "ESTIMATED":
        bits.append("valeur estimée")
    if provenance == "NON_AFRICAN":
        bits.append("d'après des données non africaines")
    elif provenance == "UNKNOWN":
        bits.append("provenance non précisée")
    return ", ".join(bits)


def _nutrient_clause(label: str, value, unit: str, status: Optional[str], provenance: Optional[str]) -> str:
    if value is None:
        return f"une teneur en {label} non mesurée"
    clause = f"environ {_format_number(value)} {unit} de {label}"
    qualifier = _qualifier_clause(status, provenance)
    if qualifier:
        clause += f" ({qualifier})"
    return clause


def _ratio_sentence(ratio, reason: Optional[str]) -> str:
    if reason is not None:
        return f"Le ratio sodium/potassium n'est pas calculable ({reason})."
    ratio = float(ratio)
    if ratio < 1:
        lecture = "le potassium y est proportionnellement plus abondant que le sodium"
    else:
        lecture = "le sodium y est proportionnellement plus abondant que le potassium"
    return f"Le ratio sodium/potassium est d'environ {_format_number(ratio)} : {lecture}."


def render_hypertension_chunk(food_row: Mapping) -> str:
    """Prend une ligne de gold.v_food_hypertension, rend un paragraphe autoportant."""
    name = food_row["name_fr"]
    category = _french_category(food_row["category"])

    sentences = [f"{name} ({category})."]

    if food_row["is_recipe_based"]:
        sentences.append(
            "Il s'agit d'un plat dont les valeurs nutritionnelles sont calculées "
            "à partir de sa recette, ce qui explique une provenance souvent non précisée."
        )

    sodium_clause = _nutrient_clause(
        "sodium", food_row["sodium_mg"], "mg", food_row["sodium_status"], food_row["sodium_provenance"]
    )
    potassium_clause = _nutrient_clause(
        "potassium", food_row["potassium_mg"], "mg", food_row["potassium_status"], food_row["potassium_provenance"]
    )
    sentences.append(f"Il contient {sodium_clause} et {potassium_clause}.")

    sentences.append(_ratio_sentence(food_row["na_k_ratio"], food_row["ratio_unavailable_reason"]))

    sentences.append(SOURCE_LINE)

    return " ".join(sentences)
