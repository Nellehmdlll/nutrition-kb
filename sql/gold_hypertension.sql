-- ============================================================================
--  GOLD — Vue HYPERTENSION
--  Applique l'ADR 0006 v2 : le ratio Na/K n'est calculé que si K > 0 mesuré ;
--  sinon NULL + raison explicite. Aucun défaut n'étant sûr pour une division,
--  on n'invente jamais de potassium.
-- ============================================================================

-- sodium_status / potassium_status : necessaires pour que le rendu texte (RAG)
-- puisse dire "valeur estimee" quand status = ESTIMATED. Meme patron que
-- gold.nutrient() et gold.nutrient_provenance().
CREATE OR REPLACE FUNCTION gold.nutrient_status(p_food TEXT, p_tag TEXT, p_unit TEXT)
RETURNS TEXT
LANGUAGE sql STABLE AS $$
    SELECT status::TEXT
    FROM kb.food_value
    WHERE food_code = p_food AND tagname = p_tag AND unit = p_unit
$$;

-- CREATE OR REPLACE ne peut pas reordonner/inserer des colonnes au milieu
-- d'une vue existante (uniquement en ajouter a la fin) -> DROP explicite.
DROP VIEW IF EXISTS gold.v_food_hypertension;

CREATE VIEW gold.v_food_hypertension AS
WITH nk AS (
    SELECT
        b.food_code,
        b.name_fr,
        b.category,
        b.energy_kcal,
        b.is_recipe_based,
        gold.nutrient(b.food_code, 'NA', 'mg')            AS sodium_mg,
        gold.nutrient(b.food_code, 'K',  'mg')            AS potassium_mg,
        gold.nutrient_status(b.food_code, 'NA', 'mg')     AS sodium_status,
        gold.nutrient_status(b.food_code, 'K',  'mg')     AS potassium_status,
        gold.nutrient_provenance(b.food_code, 'NA', 'mg') AS sodium_provenance,
        gold.nutrient_provenance(b.food_code, 'K',  'mg') AS potassium_provenance
    FROM gold.v_food_base b
)
SELECT
    food_code,
    name_fr,
    category,
    energy_kcal,
    sodium_mg,
    potassium_mg,
    sodium_status,
    potassium_status,

    -- La provenance du SODIUM est ici une information de premier plan :
    -- 167 aliments sur 1028 ont un sodium d'origine NON africaine. Le sel
    -- ajouté variant fortement d'une cuisine à l'autre, une valeur importée
    -- doit être signalée à l'utilisateur, pas présentée comme locale.
    sodium_provenance,
    potassium_provenance,

    -- Ratio Na/K : meilleur indicateur diététique pour l'HTA (on vise un ratio
    -- bas). NULLIF(potassium_mg, 0) protège À LA FOIS le K=0 mesuré (24 aliments)
    -- et le K NULL : dans les deux cas la division rend NULL, jamais d'erreur ni
    -- d'infini. On n'invente aucun potassium (ADR 0006 v2 : pas de défaut sûr
    -- pour une division).
    ROUND(sodium_mg / NULLIF(potassium_mg, 0), 3) AS na_k_ratio,

    -- LA RAISON du NULL, pour que l'assistant explique au lieu d'afficher un vide.
    -- Distingue « on ne sait pas » de « on sait que c'est zéro » (cf. ADR 0006 v2).
    CASE
        WHEN sodium_mg IS NULL AND potassium_mg IS NULL
            THEN 'sodium et potassium non mesurés'
        WHEN sodium_mg IS NULL
            THEN 'sodium non mesuré'
        WHEN potassium_mg IS NULL
            THEN 'potassium non mesuré'
        WHEN potassium_mg = 0
            THEN 'aliment sans potassium (ratio non défini)'
        ELSE NULL  -- ratio calculé normalement
    END                                            AS ratio_unavailable_reason,

    is_recipe_based
FROM nk;


-- ---------------------------------------------------------------------------
--  Contrôles qualité (doivent renvoyer 0 ligne) :
-- ---------------------------------------------------------------------------
-- a) Un ratio non NULL DOIT toujours avoir une raison NULL, et inversement.
--    (cohérence entre la valeur et son explication)
-- SELECT food_code FROM gold.v_food_hypertension
--   WHERE (na_k_ratio IS NULL) <> (ratio_unavailable_reason IS NOT NULL);
--
-- b) Aucun ratio négatif (Na et K sont >= 0 par contrainte silver).
-- SELECT food_code FROM gold.v_food_hypertension WHERE na_k_ratio < 0;
