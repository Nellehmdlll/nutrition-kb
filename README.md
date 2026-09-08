# nutrition-kb

Un assistant nutritionnel pour les personnes vivant avec le diabète et/ou l'hypertension au Burkina Faso, construit sur la table de composition des aliments FAO/INFOODS (WAFCT 2019) et servi par un LLM local.

## Pourquoi ce projet

Trouver une information nutritionnelle fiable, en français, sur des aliments réellement consommés en Afrique de l'Ouest (gombo, tô, soumbala, niébé...) n'est pas simple : la plupart des bases et applications grand public sont bâties sur des régimes alimentaires occidentaux. Pour une personne diabétique ou hypertendue à Ouagadougou, savoir combien de sodium contient réellement le bouillon-cube qu'elle utilise tous les jours n'est pas un détail, c'est une information qui affecte directement sa santé.

Ce projet part d'une source fiable et citable (la table FAO/INFOODS WAFCT 2019, qui couvre spécifiquement l'Afrique de l'Ouest) pour construire un assistant qui répond en français, sur des aliments locaux, à partir de données réelles , jamais de mémoire.

## Ce que fait l'assistant

Quelques exemples de questions traitées :

- **« Quel aliment contient le plus de sodium ? »** → un classement réel, calculé sur la base (valeur, unité, et sa fiabilité : mesurée ou estimée, provenance connue ou non).
- **« Le gombo est-il bon pour l'hypertension ? »** → une réponse construite à partir des fiches nutritionnelles de la base, sourcée (FAO/INFOODS WAFCT 2019), sans avis médical personnalisé (ce point est expliqué plus bas).
- **« Ma glycémie est à 1,80 g/L, qu'est-ce que je fais ? »** → l'assistant n'interprète JAMAIS une valeur de santé. Il oriente vers un professionnel de santé, sans mélanger ça à un conseil nutritionnel.

L'assistant tourne **entièrement en local** : la base de données et le modèle de langage (Ollama) s'exécutent sur votre machine, aucune question n'est envoyée à un service cloud tiers. Seule exception : le tout premier lancement télécharge le modèle Ollama et le modèle d'embedding depuis leurs dépôts respectifs . Une fois cela fait, tout fonctionne hors-ligne côté données et côté génération.

## Architecture en bref

```
FAO/INFOODS WAFCT 2019 (Excel)
        │
        ▼
  raw       — extraction brute, tout en texte, hashée pour détecter tout changement de source
        │
        ▼
  silver    — modèle EAV typé (un aliment, un nutriment, une valeur, un statut, une provenance)
        │
        ▼
  gold      — PostgreSQL + pgvector : vues relationnelles (diabète, hypertension) + chunks RAG
        │
        ▼
  agent     — routeur par règles (filet de sécurité) + agent LLM local (Ollama, function calling)
```

Chaque flèche est une décision documentée, pas une évidence. Les choix détaillés (pourquoi PostgreSQL, pourquoi un modèle EAV, comment les valeurs manquantes sont traitées, quel modèle d'embedding et pourquoi) sont dans [`docs/adr/`](docs/adr/) — une décision par fichier, avec les alternatives écartées et pourquoi.

## Installation & lancement

**Prérequis** : Python ≥ 3.10, Docker (ou un PostgreSQL 16+ avec l'extension `pgvector`), [Ollama](https://ollama.com).

### 1. Environnement Python

```bash
git clone <url-du-depot>
cd nutrition-kb
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -e .
pip install -r requirements-dev.txt   # pour lancer les tests
```

### 2. Base de données

```bash
docker run -d --name nutrition-kb-postgres \
  -e POSTGRES_USER=nutrition \
  -e POSTGRES_PASSWORD=CHANGE_ME \
  -e POSTGRES_DB=nutrition_kb \
  -p 5432:5432 \
  pgvector/pgvector:pg16

export NUTRITION_KB_DSN="postgresql://nutrition:CHANGE_ME@localhost:5432/nutrition_kb"
```

(`NUTRITION_KB_DSN` est lu par `src/nutrition_kb/db.py` ; sans cette variable, un DSN de développement par défaut est utilisé , à ne pas garder tel quel.)

### 3. Schéma

```bash
psql "$NUTRITION_KB_DSN" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "$NUTRITION_KB_DSN" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql "$NUTRITION_KB_DSN" -f sql/schema.sql
psql "$NUTRITION_KB_DSN" -f sql/kb_nutrient_synonym.sql
psql "$NUTRITION_KB_DSN" -f sql/kb_food_keyword.sql
psql "$NUTRITION_KB_DSN" -f sql/kb_food_local_lexicon.sql
psql "$NUTRITION_KB_DSN" -f sql/gold.sql
psql "$NUTRITION_KB_DSN" -f sql/gold_hypertension.sql
psql "$NUTRITION_KB_DSN" -f sql/gold_chunk_table.sql
```

### 4. Pipeline raw → silver → gold

Le fichier source (FAO/INFOODS WAFCT 2019) est déjà versionné dans `data/raw/sources/`.

```bash
python -m nutrition_kb.ingest.raw        # Excel -> data/raw/extracted/ (parquet, tout en texte)
python -m nutrition_kb.transform.silver  # extracted -> data/silver/ (EAV typé, parquet)
python -m nutrition_kb.load.postgres     # silver -> PostgreSQL (schéma kb)
```

### 5. Vocabulaire du routeur (règles)

```bash
python -m nutrition_kb.agent.seed_nutrient_synonyms
python -m nutrition_kb.agent.seed_food_keywords
python -m nutrition_kb.agent.seed_food_local_lexicon
```

### 6. Chunks RAG et embeddings

```bash
python -m nutrition_kb.rag.generate_chunks   # gold -> gold.chunk (prose, un chunk par aliment/angle)
python -m nutrition_kb.rag.embed_chunks      # gold.chunk.content -> vecteurs (pgvector)
```

### 7. Modèle LLM local

```bash
ollama pull llama3.1:8b
```

Ollama doit tourner sur `http://localhost:11434` (le port par défaut, aucune configuration nécessaire).

### 8. Lancer l'agent

```bash
streamlit run app/streamlit_app.py  # interface de chat web — Ollama et PostgreSQL doivent tourner
python scripts/try_llm_agent.py     # agent LLM (Ollama) — mode interactif, avec trace des outils appelés
python scripts/try_agent.py         # agent par règles (sans LLM) — routeur + exécution + réponse
python scripts/try_router.py batch  # juste la décision de routage, sans exécuter les outils
```

### 9. Tests

```bash
pytest -q
```

Une partie de la suite touche la vraie base de données et le vrai modèle Ollama (c'est un choix délibéré,  voir la philosophie de test dans les ADR) : les étapes 2 à 7 doivent être en place pour que tout passe.

## Sources & licence des données

Les données nutritionnelles proviennent de la **FAO/INFOODS West African Food Composition Table (WAFCT) 2019**.

Usage non commercial autorisé avec citation de la source. Toute utilisation commerciale nécessite une licence de la FAO (`copyright@fao.org`). Ce dépôt cite systématiquement la source dans les réponses générées et dans les chunks utilisés pour la recherche.

## Limites connues

Ce projet est **en construction**, et je le dit ouvertement plutôt que de le cacher. Quelques exemples des limites actuellement documentées :

- L'assistant peut confondre un aliment absent de la base avec un aliment présent au nom lexicalement proche (ex. « foie gras » ↔ « foie de bœuf »).
- Le conseil nutritionnel reste volontairement **descriptif**, jamais prescriptif, en v1 (« ceci est pauvre en sodium », jamais « vous devriez en manger ») — le conseil personnalisé est prévu pour une v2, avec un cadre médical adapté.
- La recherche vectorielle a des angles morts connus et mesurés (négation, jugement de magnitude)  documentés plutôt que masqués.

Le registre complet, avec pour chaque limite le symptôme observé, la cause et la piste de résolution envisagée, est dans [`docs/limitations.md`](docs/limitations.md). Les limites propres à la recherche vectorielle sont détaillées dans [`docs/adr/0009`](docs/adr/0009-retrieval-asymetrique-et-limites-du-vecteur.md).

**L'assistant informe sur la composition des aliments ; il ne remplace en aucun cas un professionnel de santé.**

## État du projet / feuille de route

**Fonctionne aujourd'hui** : pipeline complet raw → silver → gold, routeur par règles (filet de sécurité déterministe), agent LLM local avec function calling (recherche sémantique + classement SQL), garde-fous de sécurité côté code (orientation médicale systématique, blocage des valeurs inventées).

**Prévu** :
- Lexique local (mooré et autres langues) , la table est prête (`kb.food_alias`), pas encore peuplée.
- Conseil nutritionnel personnalisé (v2), avec un cadre médical et une segmentation adaptés.
- Déploiement mobile.
