CREATE TABLE IF NOT EXISTS gold.chunk (
    chunk_id      BIGSERIAL PRIMARY KEY,
    food_code     TEXT NOT NULL REFERENCES kb.food(food_code),
    angle         TEXT NOT NULL,        -- 'diabetes' | 'hypertension' | 'macros'
    content       TEXT NOT NULL,        -- LA PROSE : ce qui sera embarqué
    embedding     VECTOR(384),          -- rempli plus tard par le modèle
    source_id     TEXT NOT NULL,        -- pour citer : toujours 'WAFCT_2019'
    UNIQUE (food_code, angle)
);
