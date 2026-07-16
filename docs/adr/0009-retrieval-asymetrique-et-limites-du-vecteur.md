# ADR 0009 — e5-small pour retrieval asymétrique ; négation et magnitudes hors du vecteur

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Décideurs** : l'équipe (Sawadogo Rahimah + mentor technique IA)
- **Portée** : couche RAG (choix du modèle d'embedding, périmètre de la recherche vectorielle)

---

## Contexte

L'ADR 0008 documente la mécanique d'encodage (modèle solidaire de sa colonne
`embedding_model`, normalisation L2 + distance cosinus). Cette ADR-ci
documente une décision différente : **quel type de question le vecteur a le
droit de répondre**, et lequel il doit laisser à autre chose.

Un test comparatif sur les mêmes requêtes a opposé deux modèles :

- `paraphrase-multilingual-MiniLM-L12-v2` (v1) : entraîné pour la similarité
  entre phrases de **style comparable** (paraphrase/STS). Un test de
  contrôle (chercher avec le texte exact d'un chunk) donnait un résultat
  parfait — la mécanique était saine — mais une question naturelle (« puis-je
  manger du poisson grillé avec mon diabète ? ») faisait remonter une
  **patate douce** (riche en glucides) dans le top 5. Faux positif dangereux
  pour une app santé.
- `intfloat/multilingual-e5-small` (v2) : entraîné en paires query/passage
  contrastées, donc pour la recherche **asymétrique** question→passage, qui
  est l'usage réel du RAG. Même test : la patate douce disparaît, la bonne
  réponse remonte en position 1 (distance 0.097 contre 0.50).

## Décision

**`intfloat/multilingual-e5-small` est retenu pour le retrieval asymétrique,
avec les préfixes `"query: "`/`"passage: "` obligatoires (cf. ADR 0008,
Décision 3). La négation et les jugements de magnitude ne sont pas du ressort
du vecteur : ils relèvent de la recherche hybride SQL.**

Deux limites ont été mesurées, pas supposées, après le passage à e5-small :

1. **Négation lexicale.** « aliment très salé » remonte des plats étiquetés
   « bouilli **sans sel** » — la négation dans le nom de préparation (note de
   cuisson : pas de sel ajouté) est confondue avec l'affirmation recherchée
   (teneur intrinsèque élevée en sodium). Atténué par le changement de
   modèle (distances divisées par ~2), pas éliminé.
2. **Jugement de magnitude.** « aliment riche en sodium » ne retrouve pas
   fiablement `Sel` (38 800 mg) ou `Bouillon-cube` (19 000 mg) — les chunks
   n'énoncent jamais qu'un aliment est « riche » ou « très salé » en toutes
   lettres, seulement un nombre en mg. Rien ne relie ce nombre à un jugement
   de magnitude pour un modèle purement textuel.

Ces deux limites ne sont **pas des bugs à corriger dans l'embedding** : ce
sont des questions auxquelles un vecteur de texte ne peut structurellement
pas répondre de façon fiable, parce que la réponse dépend d'un seuil
numérique ou d'une négation grammaticale, pas d'une proximité sémantique.
La base a déjà la réponse exacte et typée (`sodium_mg`, `status`,
`provenance` dans `gold.v_food_hypertension`/`v_food_diabetes`) : une requête
du type « aliments avec sodium_mg > 1000 » se répond en SQL, correctement,
à coup sûr — pas en espérant qu'un embedding l'ait appris par cœur.

**Conséquence pour la couche recherche (à construire, pas construite ici)** :
le moteur de recherche final devra combiner recherche vectorielle (questions
conceptuelles : « aliment qui aide contre l'hypertension ») et filtres SQL
directs sur les colonnes typées (questions à seuil : « aliments à moins de
X mg de sodium »), plutôt que de tout confier à l'embedding.

## Conséquences

**Positives**
- Le choix du modèle est justifié par un test reproductible (mêmes requêtes,
  deux modèles), pas par une réputation ou une taille de fichier.
- Le périmètre du vecteur est explicite : personne ne sera surpris qu'une
  requête à seuil numérique donne un résultat médiocre en recherche pure —
  c'est attendu, documenté, et une solution (hybride) est déjà nommée.

**Négatives / coûts**
- La couche recherche ne peut pas se limiter à « encoder la question et
  chercher le plus proche » : elle doit détecter (ou router explicitement)
  les questions à seuil/négation vers un chemin SQL, ce qui est un
  développement en plus, pas gratuit.
- Cette limite n'est vérifiée que sur un échantillon de requêtes ad hoc
  (sodium, poisson/glucides) — pas un jeu de test formalisé. À surveiller si
  d'autres formulations révèlent d'autres angles morts.

## Alternatives écartées

- **Garder `paraphrase-multilingual-MiniLM-L12-v2`** : écartée après preuve
  concrète d'un faux positif dangereux (patate douce sur une question
  diabète) — inacceptable dans une app santé, même si le modèle était plus
  simple à utiliser (pas de préfixes).
- **Essayer de résoudre la magnitude/négation en enrichissant la prose**
  (ex. ajouter « riche en sodium » dans les chunks au-dessus d'un seuil) :
  déplacerait le problème sans le résoudre (quel seuil ? dans quelle langue ?
  recalculé à chaque changement de barème) et dupliquerait en texte une
  information déjà présente, typée et fiable dans les colonnes SQL. Écartée
  au profit de la recherche hybride.
