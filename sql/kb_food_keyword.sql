-- Vocabulaire de mots-cles pour detect_food. Meme esprit que
-- kb.nutrient_synonym : pas de FK vers food (ce n'est pas une table de
-- correspondance mot->aliment, juste un lexique servant a reconnaitre
-- qu'une question parle d'un aliment), colonne lang pour etendre au moore
-- plus tard.
--
-- IMPORTANT : cette table est creee vide ici. Le peuplement est un jugement
-- humain (quels mots sont vraiment des mots-cles d'aliment), pas un calcul
-- automatique -- voir build_food_keywords.py, qui PROPOSE une liste sans
-- rien ecrire en base tant qu'elle n'est pas validee.
CREATE TABLE IF NOT EXISTS kb.food_keyword (
    keyword TEXT NOT NULL,
    lang    TEXT NOT NULL DEFAULT 'fr',
    PRIMARY KEY (keyword, lang)
);
