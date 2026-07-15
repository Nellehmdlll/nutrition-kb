# ADR 0003 — PostgreSQL comme base de connaissances, SQLite embarqué dans l'app

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Portée** : stack de stockage, du pipeline à l'application mobile

---

## Contexte

Le projet doit tenir dans la durée (KB professionnelle et réutilisable) ET
alimenter une application mobile utilisable au Burkina Faso, où la connectivité
peut être dégradée ou absente. La question initiale « SQLite ou PostgreSQL ? »
supposait un choix exclusif ; l'analyse a montré que ce sont deux étages
complémentaires.

## Décision

**Deux moteurs, à deux étages :**

```
Excel FAO (immuable) ─► Python/pandas ─► raw ─► silver (Parquet)
                                                   │
                                                   ▼
                              PostgreSQL (+ pgvector)   ← la KB, côté serveur
                                                   │  export/build
                                                   ▼
                              SQLite (lecture seule)     ← embarqué dans l'app
```

- **PostgreSQL au centre** : contraintes fortes réellement appliquées
  (`CHECK`, `FOREIGN KEY`, types `ENUM`, `NUMERIC`), `JSONB` pour métadonnées
  irrégulières, et surtout **`pgvector`** pour stocker les embeddings du RAG
  dans la même base que les faits — le RAG devient une jointure SQL, pas une
  synchronisation fragile avec un store vectoriel externe.
- **SQLite en sortie** : la couche gold est exportée en un fichier SQLite de
  quelques Mo, embarqué dans l'app, en lecture seule. Recherche instantanée,
  zéro réseau, zéro coût data pour l'utilisateur — décision produit autant que
  technique dans le contexte burkinabè.

## Conséquences

- Il faut faire tourner un PostgreSQL (Docker en local) et maintenir une étape
  de build PostgreSQL → SQLite. Coût réel, assumé au vu de l'horizon du projet.
- Les contraintes de santé (valeurs non négatives, cohérence statut/valeur) sont
  garanties par le SGBD, pas seulement par le code applicatif.
- L'apprentissage de PostgreSQL (moins maîtrisé au départ) se fait sur un besoin
  réel, ce qui est un objectif de progression assumé du projet.

## Alternatives écartées

- **SQLite seul** : typage permissif (laisserait passer des incohérences), pas
  de pgvector natif. Suffisant pour un prototype jetable, insuffisant pour une
  KB durable. Écarté comme moteur central (conservé comme artefact embarqué).
- **PostgreSQL sur le téléphone** : irréaliste. D'où l'export SQLite.
- **Store vectoriel externe (Pinecone/Chroma) + base séparée** : ajouterait une
  synchronisation fragile entre faits et embeddings. Écarté au profit de
  pgvector co-localisé.
