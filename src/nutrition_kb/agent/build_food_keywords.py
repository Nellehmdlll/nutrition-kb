"""Propose un vocabulaire de mots-cles pour detect_food, a partir de food.name_fr.

NE PEUPLE RIEN dans kb.food_keyword. Produit deux listes (mots gardes / mots
retires, avec la raison du retrait) dans un fichier, pour validation humaine
avant tout INSERT -- trier un mot-frontiere (ex. "farine" vs un mot d'etat
comme "sechee") est un jugement, pas un calcul ; ce script mecanise
l'extraction et propose un premier tri, il ne tranche pas a la place de
l'utilisateur.

Deux ecarts par rapport aux 3 categories du brief, trouves en inspectant les
vraies donnees (pas supposes a priori) :
  - "vitamine", "grasse"/"graisse"/"maigre"/"matiere"/"teneur" : pas dans
    kb.nutrient_synonym au sens strict, mais decrivent une composition
    nutritionnelle generique (lipides, teneur en...), pas un aliment. Meme
    logique que le retrait des nutriments : exclus, categorie a part pour
    rester transparent sur le fait que ce n'est pas une correspondance
    exacte avec la table synonymes.
  - Une poignee de mots ambigus (ex. "son" = grammaire possessive OU
    "son de ble" = l'ingredient bran) sont signales explicitement plutot
    que classes en silence dans un sens ou l'autre.
"""

import re
from collections import Counter

import psycopg2

from nutrition_kb.agent.normalize import normalize
from nutrition_kb.db import DSN

OUT_PATH = "food_keywords_review.txt"

# --- Mots-frontiere : jamais retires, quelle que soit la categorie qui
# pourrait sembler les capturer. Documente pour que ce ne soit jamais
# "corrige" par erreur dans un futur ajustement des listes ci-dessous.
PROTECTED_KEYWORDS = {
    "feuilles", "feuille", "farine", "graine", "graines", "huile", "pate",
    "jus", "beurre", "fruit", "fruits",
}

# --- 1. Grammaticaux ------------------------------------------------------
STOPWORDS_GRAMMAR = {
    "de", "sans", "avec", "a", "et", "non", "ni", "d", "en", "la", "du",
    "au", "l", "n", "ou", "aux", "il", "qui", "pour", "dans", "ne", "ce",
    "cet", "cette", "ces", "y", "s", "se", "est", "ex",
    # fragments isoles sans valeur lexicale (typos/artefacts de tokenisation)
    "w", "f", "e", "er", "rit",
}

# --- 2. Preparation / etat physique (formes flechies reellement observees) -
STOPWORDS_PREP_STATE = {
    "cru", "crue", "crus", "crues",
    "cuit", "cuite", "cuits", "cuites",
    "bouilli", "bouillie", "bouillis", "bouillies",
    "grille", "grillee", "grilles", "grillees", "griller",
    "frais", "fraiche", "fraiches",
    "seche", "seches", "sechee", "sechees",
    "egoutte", "egouttee", "egouttes", "egouttees",
    "trempe", "trempee", "trempes", "trempees",
    "fume", "fumee", "fumes", "fumees",
    "mur", "mure", "murs", "mures",
    "blanchi", "blanchie", "blanchis", "blanchies",
    "decortique", "decortiquee", "decortiques", "decortiquees",
    "poli", "polie", "polis", "polies",
    # trouves dans les vraies donnees, meme famille (methode de preparation) :
    "vapeur", "mijote", "mijotee", "mijotes", "mijotees",
    "frit", "frite", "frites", "frits",
    "degraissee", "ecreme", "fermente", "fermentee",
    "pasteurise", "sterilise", "condense", "clarifie",
    "moulu", "moulue", "rape", "hachee", "epluchee", "egrene",
    "ecaille", "vide", "lave", "tamisee",
    "liquide", "solide",
    "entier", "entiers", "entiere", "complet", "complete", "completes",
    # trouves en relisant la liste "gardes" : meme famille (etat/preparation),
    # mal classes dans une premiere passe :
    "salee", "concentre", "poudre", "conserve",
    # "sale" ICI = 'salé' (Beurre... salé), pas 'sale' (dirty) -- meme piege
    # de collision que 'salé'/'sale' deja rencontre dans nutrient_synonym
    # (cf. ajustement precedent sur detect_nutrient). Confirme sur la vraie
    # donnee avant de le retirer, pas suppose.
    "sale",
}

# --- 3. Provenance / qualificatif -----------------------------------------
STOPWORDS_QUALIF = {
    "burkina", "faso", "nord",
    "blanc", "blanche", "blancs", "blanches",
    "rouge", "rouges",
    "jaune", "jaunes",
    "noir", "noire",
    "vert", "verte", "verts", "vertes",
    "brun", "brune",
    "clair", "claire", "pale", "fonce",
    "enrichi", "enrichie", "enrichis",
    "ingredient", "ingredients",
    "recette", "recettes",
    "moyenne", "moyen", "moyennes", "moyens", "moderee",
    "environ", "env",
    # trouves dans les vraies donnees, meme famille (provenance geographique) :
    "nigeria", "ghana", "guinee", "benin", "angole", "mali", "niger",
    "senegal", "liberia", "togo", "sierra", "leone", "cote", "ivoire",
    "bissau", "afrique", "africaine", "africain", "jamaique",
    # metadonnees generiques de la fiche, pas de l'aliment :
    "differentes", "variete", "varietes", "melange", "specifies",
    "cultivars", "combines", "partiellement", "comestible", "g", "mcg",
    "raffinee", "raffine",
    # trouves en relisant la liste "gardes" : contexte d'usage/modificateur,
    # jamais identifiant d'aliment :
    "ajoute", "age", "mois", "prealablement", "faible",
}

# --- 4. Nutriment/composition generique (hors detect_food, meme esprit que
# la table nutrient_synonym mais pas une correspondance exacte -- cf. docstring)
STOPWORDS_NUTRIENT_GENERIC = {
    "vitamine", "vitamines", "acide", "folique", "fer", "zinc", "alcool",
    "grasse", "graisse", "maigre", "matiere", "teneur",
}

# --- 5. Mots ambigus : signales, PAS classes automatiquement --------------
# (mot, raison de l'ambiguite)
AMBIGUOUS = {
    "son": "grammaire (possessif 'son/sa') OU aliment reel ('son de ble' = bran)",
    "mat": "sens peu clair hors contexte, frequence non negligeable (5)",
    "vand": "fragment, probablement un mot en langue locale non identifie (5)",
    "est": "verbe 'etre' (grammaire) le plus souvent, mais confirmer",
}

# --- 6. Corrections issues de la triangulation manuelle (fichier utilisateur,
# 2026-09-XX) : appliquees TELLES QUELLES, pas rediscutees. -----------------

# a) aliments confirmes absents de l'extraction auto (verifie : aucun des 11
# n'etait deja present dans les 663 tokens avant ajout).
MANUAL_ADDITIONS = {
    "betterave", "celeri", "champignon", "courgette", "fraise", "datte",
    "raisin", "salade", "kapok", "silure", "amarante",
}

# c) bruit residuel confirme par la triangulation manuelle.
MANUAL_REMOVALS_NOISE = {
    "base", "longue", "dure", "molle", "simple", "uniquement", "naturel",
    "preparee", "preparees", "conservation", "plates", "allongees", "intro",
    "enfants", "nature", "humide", "special", "super", "grande", "petit",
    "petites", "doux", "faux", "trois", "pure", "casse", "corps", "race",
    "locale", "sec",
}
MANUAL_REMOVALS_FRAGMENTS = {
    "dmr", "esr", "tzpb", "ikmv", "ikmp", "bix", "spp", "mix", "jl", "sr",
    "b", "ben", "cou", "kam", "oko", "nin", "ki",
    # 'to' EXPLICITEMENT exclu de cette liste : c'est le plat to, on le garde.
}

# --- 7. Round 2 de la triangulation manuelle : resolution des 4 ambigus +
# nouveau bruit residuel repere en relisant la liste "gardes" finale. -------

# Resolution explicite des mots AMBIGUOUS (remplace leur entree dans le
# dict AMBIGUOUS -- ils ne doivent plus apparaitre comme "a trancher").
AMBIGUOUS_RESOLVED_KEEP = {"son"}  # 'son de ble' = bran, aliment reel
AMBIGUOUS_RESOLVED_REMOVE = {"mat", "vand", "est"}  # fragments/grammaire

MANUAL_REMOVALS_ROUND2_QUALIF = {
    "veloute", "decoloree", "tigree", "sucree", "amer", "ameres", "douces",
    "rose", "epaisse", "sauvage", "indigene", "europeenne", "chinoise",
    "fetide", "molle", "plante", "amara",
}
MANUAL_REMOVALS_ROUND2_COMPOUND_FRAGMENTS = {
    "chair", "filet", "peau", "eaux", "cuisson", "terre", "chandelle",
    "oeil", "pinces", "corps", "coque", "aretes", "gnon",
}
MANUAL_REMOVALS_ROUND2_UNKNOWN = {
    "koeg", "toeg", "koeeg", "koeng", "koing", "maas", "maass", "maasse",
    "maane", "eindo", "sine", "pesgo", "siikam", "kaam", "kmaan", "kui",
    "kou", "koum", "maan", "isu", "wesln", "kanss", "moomd", "peeleg",
    "kiou", "baraand", "rougougdga", "koko", "naagdme", "gougba", "gbaeve",
    "poza", "rica", "gnonli", "tchobal", "bite", "pele", "goine", "datou",
    "kaman", "fornio", "kundu", "giwa", "abuja", "pepa", "akoko", "oko",
    "chika", "sinkarzie", "manipintar",
}

# Garde explicite -- connaissance terrain de l'utilisateur, non discutee.
# Sert de garde-fou : si l'un de ces mots finissait dans "removed" (par
# erreur de classification ailleurs), l'assertion dans main() le signalerait
# au lieu de le laisser disparaitre en silence.
GARDER_EXPLICITE = {
    "to", "foufou", "foutou", "gari", "soumbala", "gombo", "nere", "karite",
    "baling", "gappal", "fura", "jollof", "kenkey", "ogi", "souma", "ziim",
    "nayoungn", "djoumble", "tei", "moui", "gonre", "wesla", "banakou",
    "kalogo", "pigri", "tehi", "kamoag", "saagbo", "zeedo", "zeindo",
    "zindo", "boussan", "touba", "faro", "sagabo",
}


def _nutrient_synonyms() -> set:
    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT synonym FROM kb.nutrient_synonym")
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def tokenize(name: str) -> list:
    # normalize() ne decompose pas les ligatures (oe, ae) -- ce ne sont pas
    # des caracteres accentues au sens Unicode NFKD, donc [a-z]+ les saute
    # silencieusement sans ce correctif ('oeuf' deviendrait 'uf').
    n = normalize(name).replace("œ", "oe").replace("æ", "ae")
    return re.findall(r"[a-z]+", n)


def classify(counter: Counter, nutrient_synonyms: set):
    kept = {}
    removed = {}  # token -> (count, reason)
    ambiguous = {}

    for token, count in counter.items():
        if token in AMBIGUOUS:
            ambiguous[token] = (count, AMBIGUOUS[token])
            continue
        if token in PROTECTED_KEYWORDS:
            kept[token] = count
            continue
        if token in nutrient_synonyms:
            removed[token] = (count, "nutriment (table nutrient_synonym)")
        elif token in STOPWORDS_NUTRIENT_GENERIC:
            removed[token] = (count, "nutriment/composition generique")
        elif token in STOPWORDS_GRAMMAR:
            removed[token] = (count, "grammatical")
        elif token in STOPWORDS_PREP_STATE:
            removed[token] = (count, "preparation/etat")
        elif token in STOPWORDS_QUALIF:
            removed[token] = (count, "provenance/qualificatif")
        elif len(token) < 2:
            removed[token] = (count, "fragment (1 lettre)")
        else:
            kept[token] = count

    return kept, removed, ambiguous


def build_vocabulary() -> dict:
    """Reconstruit le vocabulaire final (gardes/retires) depuis zero.

    Point d'entree UNIQUE de la logique de classification : le rapport
    (main() ci-dessous) ET le peuplement (seed_food_keywords.py) appellent
    tous les deux CETTE fonction, pour ne jamais risquer que la liste
    peuplee en base diverge silencieusement de la liste montree en revue.
    """
    conn = psycopg2.connect(DSN)
    with conn.cursor() as cur:
        cur.execute("SELECT name_fr FROM kb.food")
        names = [r[0] for r in cur.fetchall()]
    conn.close()

    counter = Counter()
    for name in names:
        counter.update(tokenize(name))

    nutrient_synonyms = _nutrient_synonyms()
    kept, removed, ambiguous = classify(counter, nutrient_synonyms)

    # --- Corrections issues de la triangulation manuelle (cf. section 6) ---
    manual_additions_applied = {}
    for word in MANUAL_ADDITIONS:
        norm = normalize(word)
        if norm in kept:
            raise RuntimeError(f"Ajout manuel {norm!r} deja present dans les gardes -- verifier la liste.")
        kept[norm] = 0  # frequence 0 : absent de l'auto-extraction, ajoute a la main
        manual_additions_applied[norm] = "ajout manuel (absent de l'extraction auto, confirme via triangulation)"

    manual_removed = {}
    for word in MANUAL_REMOVALS_NOISE | MANUAL_REMOVALS_FRAGMENTS:
        if word in kept:
            count = kept.pop(word)
            reason = "bruit residuel (triangulation manuelle)"
            removed[word] = (count, reason)
            manual_removed[word] = (count, reason)
        # si le mot n'etait pas dans "kept" (deja retire ou jamais present),
        # rien a faire -- pas une erreur, juste une confirmation redondante.

    # Garde explicite demandee : 'to' (plat) ne doit JAMAIS etre retire meme
    # s'il apparait dans une liste de fragments par ailleurs.
    assert "to" in kept, "'to' (plat) a disparu des gardes -- ne doit jamais etre retire."

    # --- Round 2 : resolution des 4 ambigus + nouveau bruit residuel -------
    for word in AMBIGUOUS_RESOLVED_KEEP:
        count, _reason = ambiguous.pop(word)
        kept[word] = count
    for word in AMBIGUOUS_RESOLVED_REMOVE:
        count, reason = ambiguous.pop(word)
        removed[word] = (count, f"ambigu, tranche par l'utilisateur ({reason})")
    if ambiguous:
        raise RuntimeError(f"Mots ambigus non resolus par l'utilisateur : {sorted(ambiguous)}")

    round2_removed = {}
    round2_words = (
        MANUAL_REMOVALS_ROUND2_QUALIF
        | MANUAL_REMOVALS_ROUND2_COMPOUND_FRAGMENTS
        | MANUAL_REMOVALS_ROUND2_UNKNOWN
    )
    for word in round2_words:
        if word in kept:
            count = kept.pop(word)
            reason = "bruit residuel (triangulation manuelle, round 2)"
            removed[word] = (count, reason)
            round2_removed[word] = (count, reason)

    # Garde explicite (connaissance terrain) : si l'un de ces mots avait ete
    # capture par une des listes de retrait ci-dessus (round 1 ou round 2),
    # ceci l'aurait fait disparaitre en silence -- l'assertion l'empeche.
    missing_garde = GARDER_EXPLICITE - set(kept)
    assert not missing_garde, f"Mots a garder explicitement mais absents des gardes : {sorted(missing_garde)}"

    # --- Controle de collision : aucun synonyme de nutriment ne doit se
    # retrouver dans le vocabulaire aliment (sinon detect_nutrient et
    # detect_food matcheraient tous les deux le meme mot, ambigu pour le
    # routeur en aval).
    collisions = nutrient_synonyms & set(kept)
    assert not collisions, f"Collision food_keyword/nutrient_synonym : {sorted(collisions)}"

    return {
        "names": names,
        "counter": counter,
        "kept": kept,
        "removed": removed,
        "nutrient_synonyms": nutrient_synonyms,
        "collisions": collisions,
        "manual_additions_applied": manual_additions_applied,
        "manual_removed": manual_removed,
        "round2_removed": round2_removed,
        "round2_words": round2_words,
    }


def main() -> int:
    v = build_vocabulary()
    names, counter = v["names"], v["counter"]
    kept, removed = v["kept"], v["removed"]
    nutrient_synonyms, collisions = v["nutrient_synonyms"], v["collisions"]
    manual_additions_applied, manual_removed = v["manual_additions_applied"], v["manual_removed"]
    round2_removed, round2_words = v["round2_removed"], v["round2_words"]
    ambiguous: dict = {}  # tous resolus dans build_vocabulary() a ce stade

    lines = []
    lines.append(f"Vocabulaire food_keyword -- propose a partir de {len(names)} noms (food.name_fr)")
    lines.append(f"Tokens uniques : {len(counter)}  |  gardes : {len(kept)}  |  retires : {len(removed)}  |  ambigus : {len(ambiguous)}")
    lines.append("")
    lines.append("=" * 78)
    lines.append("CONTROLE DE COLLISION avec kb.nutrient_synonym")
    lines.append("=" * 78)
    if collisions:
        lines.append(f"  ECHEC : {sorted(collisions)} present(s) dans food_keyword ET nutrient_synonym.")
    else:
        lines.append(f"  OK : aucun des {len(nutrient_synonyms)} synonymes de nutriment "
                      f"({', '.join(sorted(nutrient_synonyms))}) n'est present dans food_keyword.")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"CORRECTIONS MANUELLES APPLIQUEES (triangulation, {len(manual_additions_applied)} ajouts / {len(manual_removed)} retraits)")
    lines.append("=" * 78)
    lines.append(f"  Ajoutes : {sorted(manual_additions_applied)}")
    lines.append(f"  Retires : {sorted(manual_removed)}")
    not_found = sorted((MANUAL_REMOVALS_NOISE | MANUAL_REMOVALS_FRAGMENTS) - set(manual_removed) - {"to"})
    if not_found:
        lines.append(f"  Demandes en retrait mais deja absents des gardes (rien a faire) : {not_found}")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"ROUND 2 -- resolution des ambigus + nouveau bruit ({len(round2_removed)} retires)")
    lines.append("=" * 78)
    lines.append(f"  Ambigus GARDES  : {sorted(AMBIGUOUS_RESOLVED_KEEP)}")
    lines.append(f"  Ambigus RETIRES : {sorted(AMBIGUOUS_RESOLVED_REMOVE)}")
    lines.append(f"  Retires (round 2) : {sorted(round2_removed)}")
    not_found2 = sorted(round2_words - set(round2_removed))
    if not_found2:
        lines.append(f"  Demandes en retrait mais deja absents des gardes (rien a faire) : {not_found2}")
    lines.append(f"  Garde explicite verifiee (connaissance terrain) : {len(GARDER_EXPLICITE)} mots, tous presents.")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"MOTS AMBIGUS RESTANTS -- a trancher explicitement ({len(ambiguous)})")
    lines.append("=" * 78)
    if not ambiguous:
        lines.append("  (aucun -- tous resolus)")
    for token, (count, reason) in sorted(ambiguous.items(), key=lambda kv: -kv[1][0]):
        lines.append(f"  {token:20} freq={count:4}  -- {reason}")
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"MOTS RETIRES ({len(removed)}), par raison")
    lines.append("=" * 78)
    by_reason: dict = {}
    for token, (count, reason) in removed.items():
        by_reason.setdefault(reason, []).append((token, count))
    for reason in sorted(by_reason):
        words = sorted(by_reason[reason], key=lambda t: -t[1])
        lines.append(f"\n--- {reason} ({len(words)}) ---")
        lines.append(", ".join(f"{t}({c})" for t, c in words))
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"MOTS GARDES -- candidats mots-cles d'aliment ({len(kept)})")
    lines.append("=" * 78)
    for token, count in sorted(kept.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {token:20} freq={count}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[build_food_keywords] {len(kept)} gardes, {len(removed)} retires, {len(ambiguous)} ambigus.")
    print(f"[build_food_keywords] Detail ecrit dans {OUT_PATH}")
    print("[build_food_keywords] AUCUNE ecriture en base -- kb.food_keyword reste vide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
