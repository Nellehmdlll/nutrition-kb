# ADR 0008 — Les embeddings sont solidaires de leur modèle ; normalisation L2 + distance cosinus

- **Statut** : Accepté — **révisé le 2026-07-15** (changement de modèle après test comparatif)
- **Date** : 2026-07-15
- **Décideurs** : l'équipe (Sawadogo Rahimah + mentor technique IA)
- **Portée** : couche RAG (encodage de `gold.chunk`, recherche vectorielle)
- **Historique** :
  - v1 — `paraphrase-multilingual-MiniLM-L12-v2`, choisi pour « ça marche
    partout tout de suite ».
  - v2 — remplacé par `intfloat/multilingual-e5-small` après un test
    comparatif qui a trouvé un faux positif dangereux (voir plus bas).

---

## Contexte

`gold.chunk` a 3084 lignes de prose (cf. ADR 0007) à transformer en vecteurs
pour la recherche par similarité. Trois décisions ne peuvent pas être prises
« au fil de l'eau » sans risquer de corrompre silencieusement l'index plus
tard : quel modèle produit les vecteurs, comment les comparer, et (ajouté en
v2) comment les encoder correctement selon les conventions du modèle.

Modèle retenu (v2) : `intfloat/multilingual-e5-small`, 384 dimensions — la
taille déjà fixée dans `gold.chunk.embedding VECTOR(384)` n'était pas un
hasard, c'est le format natif de cette famille de modèles. Multilingue,
léger, tourne sur CPU.

## Décision 1 — `embedding_model` : les embeddings sont solidaires de leur modèle

**Changer de modèle invalide et régénère l'intégralité de l'index. La colonne
`embedding_model` garantit qu'on ne mélange jamais deux espaces vectoriels.**

Deux vecteurs produits par deux modèles différents ne vivent pas dans le même
espace géométrique : un cosinus calculé entre les deux n'a aucun sens, même si
pgvector ne s'en plaindra jamais — il n'a aucun moyen de le savoir, un
`vector(384)` a la même forme quel que soit son origine. `embedding_model`
rend cette dépendance explicite et pilote la reprise du script d'encodage :
`embedding IS NULL OR embedding_model IS DISTINCT FROM <modèle courant>`.
`IS DISTINCT FROM` plutôt que `<>` : NULL-safe, sinon les chunks jamais
encodés (`embedding_model IS NULL`) échapperaient à la comparaison.

## Décision 2 — Normalisation L2 + distance cosinus, fixées ensemble

Ce modèle (comme le précédent) est entraîné pour que la similarité cosinus
soit la mesure pertinente entre deux phrases. Décision : les vecteurs sont
normalisés à l'encodage (`normalize_embeddings=True`, norme L2 = 1), et la
recherche utilisera l'opérateur pgvector `<=>` (distance cosinus, index
`vector_cosine_ops`).

Ce couple n'est pas arbitraire : une fois les vecteurs normalisés, distance
cosinus et distance euclidienne au carré deviennent équivalentes à une
transformation monotone près (`L2² = 2 − 2·cos`) — donc `<->` (L2) et `<=>`
(cosinus) classeraient de façon identique. Mais `<=>` reste correct même si
un vecteur n'est pas parfaitement normalisé (division par la norme intégrée
au calcul), donc c'est le choix le plus robuste, pas seulement le plus rapide.

Ces deux choix doivent rester cohérents entre eux ET avec l'index pgvector
créé plus tard : normaliser à l'encodage et indexer en L2, ou ne pas
normaliser et indexer en cosinus, produiraient des résultats de recherche
subtilement dégradés sans qu'aucune erreur ne se déclenche — un bug silencieux
classique de recherche vectorielle. D'où la décision figée ici, avant l'index.

## Décision 3 — Les préfixes `query:`/`passage:` vivent dans un module unique

Les modèles e5 exigent de préfixer chaque texte selon son rôle : `"passage: "`
pour ce qui est indexé, `"query: "` pour ce qui cherche — sans ça, la qualité
de recherche dégrade fortement (documenté par les auteurs du modèle). Cette
convention vit dans `nutrition_kb.rag.embedding` (`encode_passages()`,
`encode_query()`), pas recopiée dans le script d'encodage et une future
recherche : un préfixe oublié ou incohérent entre les deux serait un bug
silencieux — aucune erreur, juste une recherche moins bonne, invisible sans
test comparatif.

## Conséquences

**Positives**
- Rejouer le script d'encodage après un changement de modèle régénère
  automatiquement TOUT l'index — aucun vecteur orphelin d'un ancien modèle
  ne peut rester mélangé avec les nouveaux (vécu en pratique : le passage de
  v1 à v2 a réencodé les 3084 lignes sans intervention manuelle).
- Le script est reprenable (commit par lot) : un arrêt en cours de route ne
  perd que le lot en cours, jamais le travail déjà validé.

**Négatives / coûts**
- Un changement de modèle re-encode les 3084 chunks en entier (aucune
  mise à jour incrémentale possible entre deux modèles différents) —
  assumé : c'est le prix de ne jamais mélanger deux espaces vectoriels.

## Alternatives écartées

- **Pas de colonne `embedding_model`, juste `embedding IS NULL`** : impossible
  de savoir si un vecteur existant vient du modèle courant ou d'un modèle
  abandonné. Écartée.
- **Distance L2 sans normalisation** : fonctionnerait, mais rendrait la
  cohérence normalisation/index implicite et fragile à un futur changement
  de l'un sans l'autre. Écartée au profit d'un choix explicite et documenté.

---

## Complément — pourquoi v1 a été abandonné (preuves, pas impression)

`paraphrase-multilingual-MiniLM-L12-v2` (v1) est entraîné pour la similarité
entre phrases de **style comparable** (paraphrase/STS) — pas pour la
recherche asymétrique question→passage, qui est l'usage réel du RAG. Un
test de contrôle (chercher avec le texte exact d'un chunk) donnait un résultat
parfait (distance 0, voisins sémantiquement cohérents), prouvant que la
mécanique d'encodage/stockage/recherche était saine. Mais des questions
naturelles donnaient des résultats nettement dégradés, et un cas concret,
dangereux, a été trouvé : la question « puis-je manger du poisson grillé avec
mon diabète ? » faisait remonter une **patate douce** (riche en glucides,
l'exact contraire de la bonne réponse) dans le top 5.

Passage à `intfloat/multilingual-e5-small` (v2), entraîné spécifiquement en
paires query/passage contrastées. Même test : la patate douce disparaît, la
question retrouve en position 1 exactement le poisson grillé attendu (distance
0.097 contre 0.50 avant), et une requête produit-spécifique (« bouillon cube
salé ») retrouve en position 1 le bon aliment (`13_008`, distance 0.159 contre
0.63 et un résultat sans rapport avant).

**Limite connue, non résolue par ce changement** : les requêtes qualitatives
abstraites sur une grandeur numérique (« aliment riche en sodium », « aliment
très salé ») ne retrouvent toujours pas fiablement les aliments objectivement
les plus salés (sel, bouillon-cube) — la confusion lexicale entre « sans sel »
(note de préparation) et « salé » (teneur intrinsèque) persiste aussi,
atténuée mais pas éliminée. Hypothèse : aucun chunk n'énonce jamais qu'un
aliment est « riche » ou « très salé » en toutes lettres — seulement un
nombre de mg — donc rien ne relie ce nombre à un jugement de magnitude pour
le modèle. Piste pour la couche recherche (pas cette brique) : une recherche
hybride combinant filtre SQL direct (`sodium_mg > seuil`) et recherche
vectorielle, plutôt que de tout attendre de l'embedding pour ce type de
requête.
