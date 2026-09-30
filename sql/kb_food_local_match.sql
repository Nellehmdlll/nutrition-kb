-- ============================================================================
--  KB.FOOD_LOCAL_MATCH -- appariement vernaculaire valide a la main
--  (Temps 3 : kb.food_local_lexicon a propose des candidats, cette table
--  n'accueille QUE ce qui a ete valide -- jamais un appariement automatique).
-- ============================================================================
--
--  Ecart volontaire par rapport a la demande initiale ("PK sur (term,
--  food_code)") : PostgreSQL interdit une valeur NULL dans une colonne de
--  cle primaire, or food_code DOIT pouvoir etre NULL (termes 'absent_wafct'
--  ou 'unknown', ex. voaga/bikalga/scarabe). Cle de substitution (match_id)
--  + UNIQUE (term, food_code) a la place : meme garantie pratique (un couple
--  terme/food_code ne peut pas etre insere deux fois), sans le conflit
--  NULL/PK. Limite mineure acceptee : UNIQUE ne bloque pas deux lignes
--  (terme, NULL) identiques (les NULL ne sont jamais "egaux" entre eux en
--  SQL standard) -- sans consequence ici, chaque terme absent/inconnu n'a
--  qu'UNE seule ligne dans les donnees validees (jamais deux).
CREATE TABLE IF NOT EXISTS kb.food_local_match (
    match_id  BIGSERIAL PRIMARY KEY,
    term      TEXT NOT NULL,
    food_code TEXT REFERENCES kb.food(food_code),  -- NULL ssi status != 'matched'
    lang      TEXT NOT NULL DEFAULT 'und',
    status    TEXT NOT NULL,
    note      TEXT,
    UNIQUE (term, food_code),
    CONSTRAINT food_local_match_lang_valid CHECK (lang IN ('moore', 'fr', 'und')),
    CONSTRAINT food_local_match_status_valid CHECK (status IN ('matched', 'absent_wafct', 'unknown')),
    -- Meme principe que kb.food_value.value_matches_status (schema.sql) :
    -- interdire physiquement l'etat incoherent plutot que compter sur la
    -- discipline du script de seed.
    CONSTRAINT food_local_match_status_food_code_coherent CHECK (
        (status = 'matched' AND food_code IS NOT NULL)
        OR (status IN ('absent_wafct', 'unknown') AND food_code IS NULL)
    )
);
