\pset pager off
(SELECT * FROM gold.v_food_hypertension WHERE ratio_unavailable_reason IS NULL ORDER BY na_k_ratio LIMIT 2)
UNION ALL
(SELECT * FROM gold.v_food_hypertension WHERE ratio_unavailable_reason = 'aliment sans potassium (ratio non défini)' LIMIT 1)
UNION ALL
(SELECT * FROM gold.v_food_hypertension WHERE ratio_unavailable_reason = 'potassium non mesuré' LIMIT 1)
UNION ALL
(SELECT * FROM gold.v_food_hypertension WHERE ratio_unavailable_reason = 'sodium et potassium non mesurés' LIMIT 1);
