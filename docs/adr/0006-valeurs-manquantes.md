# ADR 0006 — Valeurs manquantes : combler seulement si un défaut est démontrablement sûr, sinon exposer le manque

- **Statut** : Accepté — **révisé le 2026-07-15** (v2)
- **Date initiale** : 2026-07-15
- **Décideurs** : l'équipe (Sawadogo Rahimah + mentor technique)
- **Portée** : couche gold, vues destinées à l'application et au RAG
- **Historique** :
  - v1 — « calculer avec un défaut sûr + drapeau » (cas déclencheur : fibres/diabète)
  - v2 — révision après le cas ratio Na/K : un défaut sûr n'existe pas toujours ;
    ajout de la règle de décision explicite et de la distinction entre les raisons
    d'un résultat manquant.

---

## Contexte

La source (FAO/INFOODS WAFCT 2019) est incomplète par endroits. La couche gold
produit des grandeurs **calculées** pour l'application, dont un opérande peut être
manquant. Deux cas concrets ont éprouvé la règle :

1. **Fibres (diabète)** — une soustraction. Fibre manquante → combler par 0
   **surestime** le sucre effectif : erreur dans le sens sûr pour le patient.
2. **Ratio Na/K (hypertension)** — une division. Potassium manquant → aucune
   valeur de remplacement n'est sûre : 0 fait exploser le ratio (faux positif),
   une valeur haute masque le danger (faux négatif). **Pas de défaut sûr.**

La v1 de cet ADR supposait implicitement qu'un défaut sûr existe toujours. Le
cas 2 prouve que non. D'où cette révision.

## Décision (v2)

**On ne comble une valeur manquante QUE si l'on peut démontrer que l'erreur
introduite va dans le sens sûr pour le patient. Si aucun défaut n'est
démontrablement sûr, on NE calcule PAS : on expose le manque.**

Arbre de décision, à appliquer à chaque grandeur dérivée :

```
Un opérande peut-il être manquant ?
├── NON  → calcul direct.
└── OUI  → existe-t-il une valeur de remplacement dont l'erreur va, de façon
           DÉMONTRABLE, dans le sens sûr pour le patient ?
           ├── OUI → calculer avec ce défaut + exposer un DRAPEAU d'hypothèse
           │         (cas fibres : défaut 0, drapeau fiber_is_assumed_zero).
           └── NON → NE PAS calculer. Résultat = NULL + exposer la RAISON
                     (cas Na/K : ratio_unavailable_reason).
```

### Distinguer les raisons d'un résultat manquant

Un résultat `NULL` n'est jamais livré nu. On distingue POURQUOI il est nul, car
les causes n'ont pas le même sens médical ni le même message utilisateur :

- **opérande NON DÉTERMINÉ** (jamais mesuré) → « donnée non mesurée »
- **opérande MESURÉ À ZÉRO** (valeur réelle 0, ex. K=0 dans un produit raffiné)
  → « aliment sans <nutriment> » ; le ratio est mathématiquement non défini,
  pas inconnu.

C'est la même distinction que `NOT_DETERMINED` vs `TRACE` en couche silver :
« on ne sait pas » ≠ « on sait que c'est zéro ». Elle se propage jusqu'à la gold.

### Le sens du défaut reste à prouver au cas par cas

Quand un défaut sûr existe, son sens ne se généralise pas mécaniquement. Il se
démontre pour chaque grandeur :
- soustraction d'un composant favorable (fibres) → défaut 0 surestime le risque
  = sens sûr.
- ce raisonnement est FAUX pour une division, une moyenne, ou tout composant
  dont l'absence n'a pas d'effet monotone connu sur le risque.

## Conséquences

**Positives**
- L'app ne fabrique jamais de faux positif par division (le cas `80 / 0`).
- Chaque `NULL` porte sa raison : l'assistant peut l'expliquer au lieu d'afficher
  une case vide qui ressemble à un bug.
- Règle unificatrice cohérente avec `TRACE`/`NOT_DETERMINED` (silver) et
  `provenance` : à chaque niveau, on calcule au mieux ET on transporte
  l'imperfection à côté.

**Négatives / coûts**
- Certaines grandeurs sont `NULL` là où l'utilisateur aimerait un chiffre. C'est
  assumé : mieux vaut « indisponible, voici pourquoi » qu'un chiffre faux.
- Chaque grandeur dérivée coûte des colonnes supplémentaires (drapeau OU raison).
- L'app ET le RAG doivent LIRE ces colonnes et les afficher, sinon le bénéfice
  est annulé. La responsabilité se déplace vers la présentation, ne disparaît pas.

## Alternatives écartées

- **Toujours combler avec un défaut** (v1 appliquée aveuglément) : produit des
  faux positifs sur les divisions. Écartée — c'est précisément ce que la v2 corrige.
- **Toujours laisser NULL dès qu'un opérande manque** : perdrait le cas fibres,
  où combler avec 0 est démontrablement sûr et garde l'aliment exploitable. Écartée.
- **Imputation statistique** (moyenne du groupe) : invente une donnée
  indistinguable d'une vraie mesure. Contraire à la traçabilité. Écartée.