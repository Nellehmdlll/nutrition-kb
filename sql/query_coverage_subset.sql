\pset pager off
SELECT tagname, unit, n_measured, n_estimated, n_trace,
       n_not_determined, n_non_african, pct_usable
FROM kb.v_nutrient_coverage
WHERE tagname IN ('NA','K','CHOAVLDF','FIBTG','SUGAR','PROCNT','ENERC')
ORDER BY tagname;
