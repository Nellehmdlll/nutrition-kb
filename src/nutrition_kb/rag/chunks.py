"""Rendu de chunks RAG (angle par angle) a partir des vues gold.

Un chunk est de la prose autoportante, jamais un dump cle:valeur -- c'est ce
que le modele d'embedding lit. Regles dures (heritees de tout le projet) :
un chiffre n'est jamais nu sans son incertitude, un NULL n'est jamais un vide
silencieux, la provenance est par nutriment, et la source termine toujours
le texte pour rester citable. Le sujet ("le gombo", jamais "il") est repete
dans chaque phrase : le chunk doit rester comprehensible isole, et repeter le
nom renforce son poids dans l'embedding.

La prose vit ici, en Python, pas en SQL (cf. ADR 0007) : c'est de la
presentation, elle changera souvent (formulations, alias mooré...) et ne doit
jamais devenir une migration de base de donnees.

Alias (mooré, dioula...) : `food_row["aliases"]` est deja lu partout ci-dessous.
La colonne existe dans les vues gold mais `kb.food_alias` est vide tant que la
table BF2005 n'est pas appariee -- ces clauses ne produisent donc rien
aujourd'hui. Le jour ou l'appariement est fait, tous les chunks deviennent
cherchables dans la langue locale sans toucher une ligne de ce fichier.
"""

from typing import Mapping, Optional, Sequence

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


_VOWELS = "aeiouyàâéèêëïîôùûüAEIOUYÀÂÉÈÊËÏÎÔÙÛÜ"


def _de(label: str) -> str:
    # elision : "de énergie" est incorrect, il faut "d'énergie".
    return f"d'{label}" if label and label[0] in _VOWELS else f"de {label}"


def _nutrient_clause(label: str, value, unit: str, status: Optional[str], provenance: Optional[str]) -> str:
    if value is None:
        return f"une teneur en {label} non mesurée"
    clause = f"environ {_format_number(value)} {unit} {_de(label)}"
    qualifier = _qualifier_clause(status, provenance)
    if qualifier:
        clause += f" ({qualifier})"
    return clause


def _short_name(name_fr: str) -> str:
    """Nom complet -> forme courte pour les mentions repetees dans le meme
    paragraphe. Certains noms FAO sont tres longs et descriptifs (ex. 'Baling
    béinré (nord du Burkina Faso)*: bouillie de sorgho avec pain de singe,
    tamarin, eau, lait et sucre') : les repeter mot pour mot rend la prose
    illisible. On coupe avant la premiere parenthese/deux-points. Le nom
    complet reste utilise une fois, en ouverture, pour l'identification precise."""
    cut = len(name_fr)
    for sep in ("(", ":"):
        idx = name_fr.find(sep)
        if idx != -1:
            cut = min(cut, idx)
    short = name_fr[:cut].strip().rstrip(",")
    return short or name_fr


def _identity_sentences(name: str, category: str, aliases: Optional[Sequence[str]]) -> list:
    sentences = [f"{name} ({_french_category(category)})."]
    if aliases:
        sentences.append(f"Aussi appelé {', '.join(aliases)}.")
    return sentences


def _recipe_clause(name: str, is_recipe_based: bool) -> Optional[str]:
    if not is_recipe_based:
        return None
    return (
        f"{name} est un plat dont les valeurs nutritionnelles sont calculées "
        "à partir de sa recette, ce qui explique une provenance souvent non précisée."
    )


# --- Angle HYPERTENSION --------------------------------------------------------


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
    short = _short_name(name)
    sentences = _identity_sentences(name, food_row["category"], food_row.get("aliases"))

    recipe = _recipe_clause(short, food_row["is_recipe_based"])
    if recipe:
        sentences.append(recipe)

    sodium_clause = _nutrient_clause(
        "sodium", food_row["sodium_mg"], "mg", food_row["sodium_status"], food_row["sodium_provenance"]
    )
    potassium_clause = _nutrient_clause(
        "potassium", food_row["potassium_mg"], "mg", food_row["potassium_status"], food_row["potassium_provenance"]
    )
    sentences.append(f"{short} contient {sodium_clause} et {potassium_clause}.")

    sentences.append(_ratio_sentence(food_row["na_k_ratio"], food_row["ratio_unavailable_reason"]))
    sentences.append(SOURCE_LINE)

    return " ".join(sentences)


# --- Angle DIABÈTE --------------------------------------------------------------


def _carb_density_sentence(name: str, energy_kcal, density) -> str:
    if density is None:
        return f"La densité glucidique {_de(name)} n'est pas calculable (énergie ou glucides non mesurés)."
    return (
        f"Avec {_format_number(energy_kcal)} kcal pour 100 g, cela représente environ "
        f"{_format_number(density)} g de glucides disponibles pour 100 kcal."
    )


def render_diabetes_chunk(food_row: Mapping) -> str:
    """Prend une ligne de gold.v_food_diabetes, rend un paragraphe autoportant."""
    name = food_row["name_fr"]
    short = _short_name(name)
    sentences = _identity_sentences(name, food_row["category"], food_row.get("aliases"))

    recipe = _recipe_clause(short, food_row["is_recipe_based"])
    if recipe:
        sentences.append(recipe)

    carbs = food_row["glycemic_carbs_g"]

    # Grandeur centrale de l'angle absente ou nulle : la prose change de FORME,
    # pas seulement de chiffre. "0 g de glucides ... ralentissent l'absorption
    # des glucides" est grammaticalement correct et semantiquement absurde --
    # et un faux positif de recherche (le chunk contient "glucides"/"fibres"/
    # "glycémie" sans rien dire d'utile). 212/1028 aliments sont a glucides
    # mesures a zero (surtout viandes/poissons) : on NE supprime PAS le chunk
    # -- "puis-je manger du poisson grille ?" est une vraie question diabete,
    # et "aucun impact glycemique" est une reponse utile -- on raccourcit
    # juste la prose au lieu de forcer le gabarit complet sur un zero.
    if carbs is None:
        sentences.append(
            f"La teneur en glucides disponibles {_de(short)} n'est pas mesurée : "
            "son impact sur la glycémie ne peut pas être évalué."
        )
    elif float(carbs) == 0:
        qualifier = _qualifier_clause(food_row["glycemic_carbs_status"], food_row["glycemic_carbs_provenance"])
        suffix = f" ({qualifier})" if qualifier else ""
        sentences.append(
            f"{short} ne contient pas de glucides disponibles{suffix} : aucun impact direct sur la glycémie."
        )
    else:
        carbs_clause = _nutrient_clause(
            "glucides disponibles",
            carbs,
            "g",
            food_row["glycemic_carbs_status"],
            food_row["glycemic_carbs_provenance"],
        )
        sentences.append(
            f"{short} contient {carbs_clause}, la grandeur qui influence directement la glycémie "
            "(les fibres en sont déjà déduites par la FAO)."
        )

        fiber_clause = _nutrient_clause(
            "fibres", food_row["fiber_g"], "g", food_row["fiber_status"], food_row["fiber_provenance"]
        )
        sentences.append(f"{short} apporte aussi {fiber_clause}, qui ralentissent l'absorption des glucides.")

        sentences.append(_carb_density_sentence(short, food_row["energy_kcal"], food_row["carbs_per_100kcal"]))

    sentences.append(SOURCE_LINE)

    return " ".join(sentences)


# --- Angle MACROS -----------------------------------------------------------------


def render_macros_chunk(food_row: Mapping) -> str:
    """Prend une ligne de gold.v_food_base, rend un paragraphe autoportant."""
    name = food_row["name_fr"]
    short = _short_name(name)
    sentences = _identity_sentences(name, food_row["category"], food_row.get("aliases"))

    recipe = _recipe_clause(short, food_row["is_recipe_based"])
    if recipe:
        sentences.append(recipe)

    energy_clause = _nutrient_clause(
        "énergie", food_row["energy_kcal"], "kcal", food_row["energy_status"], food_row["energy_provenance"]
    )
    sentences.append(f"{short} apporte {energy_clause} pour 100 g.")

    protein_clause = _nutrient_clause(
        "protéines", food_row["protein_g"], "g", food_row["protein_status"], food_row["protein_provenance"]
    )
    fat_clause = _nutrient_clause(
        "lipides", food_row["fat_g"], "g", food_row["fat_status"], food_row["fat_provenance"]
    )
    carb_clause = _nutrient_clause(
        "glucides disponibles",
        food_row["carb_available_g"],
        "g",
        food_row["carb_available_status"],
        food_row["carb_available_provenance"],
    )
    sentences.append(
        f"Sa composition pour 100 g comprend {protein_clause}, {fat_clause} et {carb_clause}."
    )

    sentences.append(SOURCE_LINE)

    return " ".join(sentences)
