-- Lexique local (mooré et autres), germe du futur appariement vernaculaire.
-- PAS de FK vers food : aucun food_code derriere ces termes pour l'instant,
-- c'est le point explicite de cette table -- documenter ce qu'on sait sans
-- pretendre l'avoir deja relie a un aliment WAFCT precis.
--
-- lang DEFAULT 'und' (indetermine), pas 'fr' : la liste source melange des
-- mots clairement non-francais (bikalga, benga, voaga, dolo...) et des
-- locutions descriptives francaises ("feuilles de baobab", "gomme arabique").
-- Deviner laquelle est du moore precisement serait affirmer sans preuve --
-- l'identification precise de la langue est un travail futur, pas fait ici.
CREATE TABLE IF NOT EXISTS kb.food_local_lexicon (
    term  TEXT NOT NULL,
    lang  TEXT NOT NULL DEFAULT 'und',
    note  TEXT,
    PRIMARY KEY (term, lang)
);
