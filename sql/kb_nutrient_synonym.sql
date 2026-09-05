-- Table de synonymes pour le routeur (detection de nutriment par regles).
--
-- Pointe vers tagname SEUL, pas vers (tagname, unit) : au moment de router
-- une question, on sait qu'on parle de "sodium", pas encore si la reponse
-- portera sur mg ou une autre unite -- ce choix se fait plus tard, cote
-- reponse. Consequence directe : pas de FOREIGN KEY vers kb.component, dont
-- la PK est composite (tagname, unit) et ne peut donc pas etre referencee
-- par tagname seul. La verification que chaque tagname existe reellement se
-- fait au moment du peuplement (cf. seed_nutrient_synonyms.py), pas via une
-- contrainte SQL.
--
-- PRIMARY KEY (synonym, lang) : un synonyme ne doit pointer que vers UN SEUL
-- tagname par langue -- sinon detect_nutrient() n'aurait aucun moyen de
-- choisir. Le constraint le rend impossible a violer, pas seulement
-- deconseille.
CREATE TABLE IF NOT EXISTS kb.nutrient_synonym (
    synonym  TEXT NOT NULL,   -- deja normalise (cf. normalize()) : minuscules, sans accents
    tagname  TEXT NOT NULL,   -- ex. 'NA', 'CHOAVLDF' -- doit exister dans kb.component
    lang     TEXT NOT NULL DEFAULT 'fr',
    PRIMARY KEY (synonym, lang)
);
