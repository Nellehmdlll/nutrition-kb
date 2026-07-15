\pset pager off
SELECT 'a) coherence ratio/raison' AS check_name, count(*) AS n_violations
FROM gold.v_food_hypertension
WHERE (na_k_ratio IS NULL) <> (ratio_unavailable_reason IS NOT NULL)
UNION ALL
SELECT 'b) ratio negatif', count(*)
FROM gold.v_food_hypertension
WHERE na_k_ratio < 0;
