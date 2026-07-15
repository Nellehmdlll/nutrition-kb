-- ============================================================================
--  NUTRITION KB — Schéma PostgreSQL
--  Source : FAO/INFOODS WAFCT 2019 (usage non commercial ; licence FAO requise
--           pour tout usage commercial — copyright@fao.org)
-- ============================================================================
--
--  PRINCIPE DIRECTEUR : « make illegal states unrepresentable ».
--  Tout ce qui ne doit pas exister doit être IMPOSSIBLE à écrire — pas
--  seulement déconseillé. Les CHECK ci-dessous ne sont pas de la décoration :
--  ils sont la dernière ligne de défense, celle qui ne dépend pas de la
--  discipline du développeur ni de la couverture des tests.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS kb;
SET search_path TO kb, public;


-- ---------------------------------------------------------------------------
--  1. TYPES ÉNUMÉRÉS — deux axes ORTHOGONAUX
-- ---------------------------------------------------------------------------
--  value_status : ce qu'on sait de la VALEUR
--  provenance   : d'où vient l'ÉCHANTILLON
--  Une valeur peut être MEASURED+NON_AFRICAN, ou ESTIMATED+AFRICAN, etc.
--  En revanche MEASURED et TRACE s'excluent -> ENUM, pas booléens.
-- ---------------------------------------------------------------------------

CREATE TYPE value_status AS ENUM (
    'MEASURED',   -- nombre nu dans la source        -> value NOT NULL
    'ESTIMATED',  -- entre [crochets] : empruntée/calculée -> value NOT NULL
    'TRACE'       -- 'tr' : présent mais NON QUANTIFIÉ     -> value IS NULL
);
-- NOTE : pas de 'NOT_DETERMINED' ici.
-- Une cellule non déterminée = ABSENCE DE LIGNE dans food_value.
-- C'est déductible du produit cartésien (food × component) : on ne stocke pas
-- ce que le schéma sait déjà. La grille complète est reconstruite par la vue
-- v_food_nutrient_grid ci-dessous (LEFT JOIN).

CREATE TYPE provenance AS ENUM (
    'AFRICAN',      -- l'aliment a une ligne "Non-African data", cellule non marquée
    'NON_AFRICAN',  -- cellule marquée 'oa' (originating abroad)
    'UNKNOWN'       -- l'aliment n'a AUCUNE ligne de provenance
);
-- UNKNOWN concerne 539 aliments / 1028 (dont 91 des 116 aliments burkinabè),
-- massivement des plats calculés depuis leur recette (biblio_source =
-- 'calc. from recipe'). L'absence de preuve n'est pas la preuve de l'absence.


-- ---------------------------------------------------------------------------
--  2. SOURCES — la KB est multi-sources DÈS LA CONCEPTION
-- ---------------------------------------------------------------------------
--  Sans cette table, l'assistant IA ne peut pas CITER. Une base de
--  connaissances qui ne peut pas citer n'est qu'une base de données.
-- ---------------------------------------------------------------------------

CREATE TABLE source (
    source_id     TEXT PRIMARY KEY,           -- 'WAFCT_2019', 'BF_MS_2005'
    title         TEXT        NOT NULL,
    publisher     TEXT        NOT NULL,
    year          SMALLINT    NOT NULL,
    citation      TEXT        NOT NULL,       -- citation exacte exigée par l'éditeur
    license       TEXT        NOT NULL,
    sha256        CHAR(64),                   -- lien vers raw/sources/MANIFEST.json
    priority      SMALLINT    NOT NULL,       -- 1 = fait autorité pour les valeurs
    CONSTRAINT source_year_sane CHECK (year BETWEEN 1900 AND 2100)
);

INSERT INTO source VALUES (
    'WAFCT_2019',
    'FAO/INFOODS Food Composition Table for Western Africa (2019)',
    'FAO', 2019,
    'Vincent, A., Grande, F., Compaoré, E., et al. 2020. FAO/INFOODS Food Composition Table for Western Africa (2019). Rome, FAO.',
    'Usage non commercial autorisé avec citation. Licence requise pour usage commercial (copyright@fao.org).',
    NULL, 1
);


-- ---------------------------------------------------------------------------
--  3. COMPONENT — le référentiel des nutriments
-- ---------------------------------------------------------------------------
--  PK = (tagname, unit) et NON tagname seul.
--  La FAO déclare ENERC deux fois : (ENERC, kJ) et (ENERC, kcal) — deux
--  entrées légitimes avec des formules différentes. Un dedup sur le tagname
--  seul les fusionne en silence. Le tagname INFOODS reste PUR : on n'invente
--  pas d'identifiants 'ENERC_kcal' hors standard.
-- ---------------------------------------------------------------------------

CREATE TABLE component (
    tagname       TEXT NOT NULL,     -- identifiant INFOODS : PROTCNT, NA, CHOAVLDF...
    unit          TEXT NOT NULL,     -- g, mg, µg, kJ, kcal, '-' (sans dimension)
    name_en       TEXT NOT NULL,
    name_fr       TEXT NOT NULL,
    alternatives  TEXT,              -- 'FAT or [FATCE]' -> 'FATCE'
    denominator   TEXT,              -- '100 g EP'
    max_decimals  SMALLINT,
    PRIMARY KEY (tagname, unit)
);


-- ---------------------------------------------------------------------------
--  4. FOOD_CATEGORY / FOOD
-- ---------------------------------------------------------------------------

CREATE TABLE food_category (
    category_id   SMALLSERIAL PRIMARY KEY,
    name_en       TEXT NOT NULL UNIQUE
);

CREATE TABLE food (
    food_code       TEXT PRIMARY KEY,          -- '01_172' — le code FAO, stable
    name_en         TEXT NOT NULL,
    name_fr         TEXT NOT NULL,
    name_scientific TEXT,
    category_id     SMALLINT NOT NULL REFERENCES food_category(category_id),
    biblio_source   TEXT,                      -- 'calc. from recipe', 'AU14(...)'
    source_id       TEXT NOT NULL REFERENCES source(source_id),
    is_recipe_based BOOLEAN GENERATED ALWAYS AS
                    (biblio_source ILIKE 'calc. from recipe%') STORED,
    source_row      INTEGER NOT NULL           -- traçabilité jusqu'à la cellule Excel
);

CREATE INDEX food_name_fr_trgm ON food USING gin (name_fr gin_trgm_ops);
-- (nécessite : CREATE EXTENSION pg_trgm;)
-- Recherche floue sur le nom français : l'utilisateur tape « gombo »,
-- pas « Okra, fresh, raw ». Servira aussi au lexique mooré (food_alias).


-- ---------------------------------------------------------------------------
--  5. FOOD_ALIAS — le lexique local (mooré), prévu dès maintenant
-- ---------------------------------------------------------------------------
--  La table nationale BF 2005 (Ministère de la Santé) alimente CETTE table
--  et JAMAIS food_value. Elle apporte les noms vernaculaires (bulvaka, mana,
--  soumbala, kagha...) — sans eux, l'app est inutilisable à Ouagadougou.
--  Mais ses valeurs nutritionnelles sont une compilation non tracée, avec des
--  erreurs avérées (217 g de protides/100 g), et sans sodium ni potassium.
-- ---------------------------------------------------------------------------

CREATE TABLE food_alias (
    alias_id    BIGSERIAL PRIMARY KEY,
    food_code   TEXT NOT NULL REFERENCES food(food_code) ON DELETE CASCADE,
    alias       TEXT NOT NULL,
    lang        TEXT NOT NULL,     -- 'moore', 'fr', 'dioula'...
    source_id   TEXT NOT NULL REFERENCES source(source_id),
    UNIQUE (food_code, alias, lang)
);


-- ---------------------------------------------------------------------------
--  6. FOOD_VALUE — LE CŒUR (modèle EAV)
-- ---------------------------------------------------------------------------
--  Une ligne = UN FAIT AUTOPORTANT :
--    « aliment X, nutriment Y, valeur Z, confiance C, provenance P, source S »
--  C'est ce qui rend la KB citable par le RAG.
-- ---------------------------------------------------------------------------

CREATE TABLE food_value (
    food_code     TEXT NOT NULL REFERENCES food(food_code) ON DELETE CASCADE,
    tagname       TEXT NOT NULL,
    unit          TEXT NOT NULL,

    value         NUMERIC,          -- NULL ssi status = TRACE
    status        value_status NOT NULL,
    provenance    provenance   NOT NULL,

    stat_n        SMALLINT,         -- nb d'échantillons compilés (souvent 1 !)
    stat_sd       NUMERIC,
    stat_min      NUMERIC,
    stat_max      NUMERIC,
    stat_median   NUMERIC,

    source_id     TEXT NOT NULL REFERENCES source(source_id),
    source_row    INTEGER NOT NULL,

    PRIMARY KEY (food_code, tagname, unit),
    FOREIGN KEY (tagname, unit) REFERENCES component(tagname, unit),

    -- ===== LA CONTRAINTE QUI JUSTIFIE TOUT LE TRAVAIL =====
    -- Interdit physiquement « value = 2.5 ET on ne connaît pas la valeur ».
    -- Ce n'est plus une question de discipline : PostgreSQL REFUSE la ligne.
    CONSTRAINT value_matches_status CHECK (
        (status IN ('MEASURED', 'ESTIMATED') AND value IS NOT NULL)
        OR
        (status = 'TRACE' AND value IS NULL)
    ),

    -- Aucun nutriment n'est négatif. Simple, et attrape les décalages de colonnes.
    CONSTRAINT value_non_negative CHECK (value IS NULL OR value >= 0),

    -- Cohérence interne des statistiques.
    CONSTRAINT stats_ordered CHECK (
        stat_min IS NULL OR stat_max IS NULL OR stat_min <= stat_max
    ),
    CONSTRAINT stat_n_positive CHECK (stat_n IS NULL OR stat_n >= 1)
);

CREATE INDEX food_value_tagname_idx ON food_value (tagname, unit);
CREATE INDEX food_value_food_idx    ON food_value (food_code);
-- Pourquoi CES index :
--  - la PK indexe déjà (food_code, tagname, unit) -> « tous les nutriments
--    d'un aliment » est rapide (préfixe de la PK) ;
--  - mais « tous les aliments pauvres en sodium » attaque par tagname, qui
--    n'est PAS en tête de PK -> il faut son propre index.
--  Un index = un arbre trié sur une (ou des) colonne(s) : il évite de lire
--  les 53 652 lignes pour en trouver 40.


-- ---------------------------------------------------------------------------
--  7. LA GRILLE COMPLÈTE — c'est la GOLD qui la reconstruit, pas la silver
-- ---------------------------------------------------------------------------
--  On ne STOCKE pas les 5 972 cellules « non déterminées » : elles sont
--  déductibles du produit cartésien. On les MATÉRIALISE ici, pour que l'app
--  ne confonde jamais « aliment inconnu » et « nutriment non mesuré ».
-- ---------------------------------------------------------------------------

CREATE VIEW v_food_nutrient_grid AS
SELECT
    f.food_code,
    c.tagname,
    c.unit,
    fv.value,
    COALESCE(fv.status::TEXT, 'NOT_DETERMINED') AS status,
    COALESCE(fv.provenance::TEXT, 'UNKNOWN')    AS provenance
FROM food f
CROSS JOIN component c
LEFT JOIN food_value fv
       ON fv.food_code = f.food_code
      AND fv.tagname   = c.tagname
      AND fv.unit      = c.unit;


-- ---------------------------------------------------------------------------
--  8. COUVERTURE — la dette créée par « TRACE -> value NULL »
-- ---------------------------------------------------------------------------
--  Rappel : SUM() IGNORE les NULL. Un total de sodium calculé sur un repas
--  dont 3 ingrédients sur 8 sont en TRACE serait FAUX PAR OMISSION, sans que
--  rien ne l'indique. L'assistant DOIT pouvoir dire « au moins X mg ».
-- ---------------------------------------------------------------------------

CREATE VIEW v_nutrient_coverage AS
SELECT
    tagname,
    unit,
    COUNT(*) FILTER (WHERE status = 'MEASURED')                AS n_measured,
    COUNT(*) FILTER (WHERE status = 'ESTIMATED')               AS n_estimated,
    COUNT(*) FILTER (WHERE status = 'TRACE')                   AS n_trace,
    COUNT(*) FILTER (WHERE status = 'NOT_DETERMINED')          AS n_not_determined,
    COUNT(*) FILTER (WHERE provenance = 'NON_AFRICAN')         AS n_non_african,
    ROUND(100.0 * COUNT(*) FILTER (WHERE value IS NOT NULL) / COUNT(*), 1)
        AS pct_usable
FROM v_food_nutrient_grid
GROUP BY tagname, unit
ORDER BY pct_usable;
