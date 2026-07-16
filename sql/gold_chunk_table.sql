CREATE TABLE IF NOT EXISTS gold.chunk (
    chunk_id      BIGSERIAL PRIMARY KEY,
    food_code     TEXT NOT NULL REFERENCES kb.food(food_code),
    angle         TEXT NOT NULL,        -- 'diabetes' | 'hypertension' | 'macros'
    content       TEXT NOT NULL,        -- LA PROSE : ce qui sera embarqué
    embedding     VECTOR(384),          -- rempli par le script d'encodage
    -- Les embeddings sont solidaires de leur modele : deux vecteurs produits
    -- par deux modeles differents ne vivent pas dans le meme espace (cosinus
    -- incoherent, sans erreur visible). embedding_model rend cette
    -- dependance explicite ; le script d'encodage (re)traite les lignes ou
    -- embedding IS NULL OR embedding_model IS DISTINCT FROM <modele courant>
    -- (IS DISTINCT FROM, pas <> : <> renvoie NULL -- donc "ne matche pas" --
    -- sur les lignes jamais encodees, exactement l'inverse de ce qu'on veut).
    embedding_model TEXT,
    source_id     TEXT NOT NULL,        -- pour citer : toujours 'WAFCT_2019'
    UNIQUE (food_code, angle)
);
