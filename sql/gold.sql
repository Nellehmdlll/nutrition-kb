-- ============================================================================
--  GOLD — Forme A (relationnelle, orientée application)
--  Toutes les vues DÉRIVENT de la silver. Aucune donnée nouvelle ici.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS gold;

-- ---------------------------------------------------------------------------
--  Fonction utilitaire : récupérer UNE valeur nutritionnelle d'un aliment.
--  Évite de répéter le motif LEFT JOIN food_value ... AND tagname=... partout.
--  SQL scalaire, inlinée par PostgreSQL -> pas de coût par appel.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION gold.nutrient(p_food TEXT, p_tag TEXT, p_unit TEXT)
RETURNS NUMERIC
LANGUAGE sql STABLE AS $$
    SELECT value
    FROM kb.food_value
    WHERE food_code = p_food AND tagname = p_tag AND unit = p_unit
$$;

CREATE OR REPLACE FUNCTION gold.nutrient_provenance(p_food TEXT, p_tag TEXT, p_unit TEXT)
RETURNS TEXT
LANGUAGE sql STABLE AS $$
    SELECT provenance::TEXT
    FROM kb.food_value
    WHERE food_code = p_food AND tagname = p_tag AND unit = p_unit
$$;


-- ---------------------------------------------------------------------------
--  1. VUE DE BASE — l'identité + les macros, commune à toutes les pathologies
-- ---------------------------------------------------------------------------
--  Toute vue pathologie l'étend, pour ne pas dupliquer nom/catégorie/énergie.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW gold.v_food_base AS
SELECT
    f.food_code,
    f.name_fr,
    f.name_en,
    fc.name_en                              AS category,
    f.is_recipe_based,                      -- plat calculé depuis recette (provenance UNKNOWN)
    gold.nutrient(f.food_code, 'ENERC', 'kcal') AS energy_kcal,
    gold.nutrient(f.food_code, 'PROTCNT', 'g') AS protein_g,
    gold.nutrient(f.food_code, 'FAT', 'g')     AS fat_g,
    gold.nutrient(f.food_code, 'CHOAVLDF', 'g') AS carb_available_g
FROM kb.food f
JOIN kb.food_category fc ON fc.category_id = f.category_id;


-- ---------------------------------------------------------------------------
--  2. VUE DIABÈTE
-- ---------------------------------------------------------------------------
--  CORRECTION MAJEURE vs l'esquisse initiale :
--  CHOAVLDF (glucides DISPONIBLES) est calculé PAR DIFFÉRENCE par la FAO, donc
--  les fibres en sont DÉJÀ retirées. Il ne faut RIEN soustraire :
--  carb_available_g EST déjà l'équivalent « glucides nets » pour le diabète.
--  L'ancienne formule (CHOAVLDF - FIBTG) soustrayait les fibres deux fois et
--  produisait 94 valeurs négatives (son de blé, soja, pois bambara).
--
--  Conséquence : plus de COALESCE, plus de valeur manquante à combler ici,
--  donc l'ADR 0006 ne s'applique pas à cette vue (aucune soustraction).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW gold.v_food_diabetes AS
SELECT
    b.food_code,
    b.name_fr,
    b.category,
    b.energy_kcal,

    -- Ce qui fait monter la glycémie : glucides disponibles (fibres déjà exclues).
    b.carb_available_g                        AS glycemic_carbs_g,

    -- Les fibres, exposées séparément : elles RALENTISSENT l'absorption.
    -- Information utile en soi, PAS à soustraire de carb_available_g.
    gold.nutrient(b.food_code, 'FIBTG', 'g')  AS fiber_g,

    -- Densité glucidique = glucides / énergie. Aide à comparer des aliments
    -- à apport calorique différent. NULLIF évite la division par zéro (ex. huiles).
    ROUND(
        b.carb_available_g / NULLIF(b.energy_kcal, 0) * 100, 1
    )                                         AS carbs_per_100kcal,

    b.is_recipe_based
FROM gold.v_food_base b;


-- ---------------------------------------------------------------------------
--  Contrôle qualité : à lancer après création, doit renvoyer 0 ligne.
--  Si une de ces vérités biochimiques est violée -> anomalie à investiguer.
-- ---------------------------------------------------------------------------
-- SELECT food_code, glycemic_carbs_g FROM gold.v_food_diabetes
--   WHERE glycemic_carbs_g < 0 OR glycemic_carbs_g > 100;
