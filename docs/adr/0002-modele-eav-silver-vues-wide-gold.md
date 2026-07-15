# ADR 0002 — Modèle EAV en silver, vues « wide » en gold

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Portée** : modélisation des données nutritionnelles

---

## Contexte

Chaque valeur nutritionnelle porte des métadonnées propres : niveau de confiance
(mesurée / estimée / trace), provenance géographique, statistiques (n, SD, min,
max, median), source. Deux familles de modèles étaient possibles.

- **Modèle « wide »** : une ligne par aliment, une colonne par nutriment.
- **Modèle « long » / EAV** (Entity-Attribute-Value) : une ligne par
  (aliment × nutriment), chaque ligne portant ses propres métadonnées.

## Décision

**EAV en couche silver ; vues « wide » matérialisées en couche gold.**

Raisonnement :

- Le modèle wide ne peut pas porter les métadonnées PAR VALEUR sans dupliquer
  chaque colonne de nutriment par une colonne de flag miroir (57 nutriments →
  ingérable). L'EAV attache naturellement statut, provenance et stats à chaque
  fait.
- L'EAV produit des **faits autoportants** (un fait = une ligne), forme idéale
  pour le RAG : chaque ligne devient un chunk citable.
- L'EAV est extensible sans migration de schéma (nouveau nutriment = nouvelles
  lignes, pas nouvelle colonne).
- L'inconfort de lecture de l'EAV (reconstituer un profil complet = pivot) est
  réglé en gold par des vues wide, taillées pour l'app.

On obtient le meilleur des deux : rigueur et métadonnées en amont (silver),
ergonomie en aval (gold).

## Conséquences

- `food_value` compte ~53 652 lignes (une par cellule renseignée) — trivial pour
  PostgreSQL.
- Un attribut absent (ex. `SD` souvent NULL) ne coûte rien en EAV, contrairement
  au wide où il créerait des colonnes creuses. Ce bénéfice est concret : il rend
  gratuit le stockage des statistiques rares.
- La reconstruction d'un profil aliment complet passe par la gold, jamais par
  l'app directement sur la silver.

## Alternatives écartées

- **Wide pur** : simple mais incapable de porter les métadonnées par valeur, et
  rigide face à l'ajout de nutriments. Écarté comme modèle de vérité (conservé
  seulement comme forme de présentation en gold).
- **EAV exposé directement à l'app** : forcerait l'app à pivoter en permanence.
  Écarté au profit des vues gold.
