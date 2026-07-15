\pset pager off
SELECT food_code, name_fr, glycemic_carbs_g
FROM gold.v_food_diabetes
WHERE glycemic_carbs_g < 0 OR glycemic_carbs_g > 100;
