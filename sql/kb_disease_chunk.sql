-- ============================================================================
--  KB.DISEASE_CHUNK -- base de connaissances MALADIE (contenu educatif OMS)
--
--  SEPAREE de gold.chunk (nutrition), meme si meme PostgreSQL : domaine,
--  source et cycle de vie differents -- un chunk nutrition decrit un
--  ALIMENT (derive des vues gold), un chunk maladie decrit une MALADIE
--  (source de verite lui-meme, jamais derive d'autre chose). D'ou sa place
--  dans le schema kb (source de verite), pas gold (vues derivees).
--
--  Une ligne = UNE SECTION de fiche OMS (« Symptômes », « Prévention »...).
--  content est le texte OMS ORIGINAL, jamais reformule au stockage --
--  fidelite a la source, meme principe que la couche raw pour la FAO. La
--  reformulation en francais simple, si besoin, se fait au moment de la
--  reponse (LLM), pas ici.
-- ============================================================================

CREATE TABLE IF NOT EXISTS kb.disease_chunk (
    chunk_id        BIGSERIAL PRIMARY KEY,
    disease         TEXT NOT NULL,        -- 'diabete' | 'hypertension'
    section         TEXT NOT NULL,        -- titre de section OMS, tel quel
    content         TEXT NOT NULL,        -- texte OMS ORIGINAL, non reformule
    embedding       VECTOR(384),          -- rempli par embed_disease_chunks.py
    -- Meme raison que gold.chunk.embedding_model (cf. gold_chunk_table.sql) :
    -- un embedding est solidaire du modele qui l'a produit, deux modeles ne
    -- vivent pas dans le meme espace vectoriel.
    embedding_model TEXT,
    source_id       TEXT NOT NULL REFERENCES kb.source(source_id),
    UNIQUE (disease, section)
);

-- ---------------------------------------------------------------------------
--  Enregistrement de la source OMS -- meme table que WAFCT_2019 (kb.source),
--  meme discipline de citation/licence.
--
--  sha256 laisse NULL (comme WAFCT_2019) : ce champ documente un lien vers un
--  MANIFEST.json d'integrite pour un fichier source UNIQUE ingere par le
--  pipeline raw -- il n'y a pas d'equivalent ici (deux fiches distinctes
--  pointent sur CETTE MEME ligne de citation, pas UN fichier).
-- ---------------------------------------------------------------------------

INSERT INTO kb.source (source_id, title, publisher, year, citation, license, sha256, priority)
VALUES (
    'OMS_2024',
    'Fiches d''information OMS -- Diabète et Hypertension',
    'Organisation mondiale de la Santé (OMS)', 2024,
    'Organisation mondiale de la Santé. Diabète [et] Hypertension. Aide-mémoire, 2024. '
    'Disponible sur : https://www.who.int/fr/news-room/fact-sheets/detail/diabetes '
    'et https://www.who.int/fr/news-room/fact-sheets/detail/hypertension',
    'CC BY-NC-SA 3.0 IGO -- usage non commercial, citation obligatoire. Toute adaptation '
    'doit porter la mention qu''elle n''a pas ete creee par l''OMS et n''est pas approuvee par elle.',
    NULL, 1
)
ON CONFLICT (source_id) DO NOTHING;
