\pset pager off
SELECT food_code, name_fr, energy_kcal, glycemic_carbs_g, fiber_g, carbs_per_100kcal, is_recipe_based
FROM gold.v_food_diabetes
WHERE food_code IN ('01_172', '01_188')
ORDER BY food_code;
