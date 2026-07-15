\pset pager off
WITH choavldf AS (
    SELECT food_code, value AS choavldf_g FROM kb.food_value WHERE tagname = 'CHOAVLDF' AND unit = 'g'
),
fibtg AS (
    SELECT food_code, value AS fibtg_g FROM kb.food_value WHERE tagname = 'FIBTG' AND unit = 'g'
)
SELECT count(*) AS n_negative_with_old_formula
FROM choavldf c
JOIN fibtg f ON f.food_code = c.food_code
WHERE c.choavldf_g - f.fibtg_g < 0;
