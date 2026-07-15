\pset pager off
SELECT 'sodium non-africain' AS metric, count(*) AS n
FROM gold.v_food_hypertension WHERE sodium_provenance = 'NON_AFRICAN'
UNION ALL
SELECT 'potassium mesure a zero', count(*)
FROM gold.v_food_hypertension WHERE potassium_mg = 0;
