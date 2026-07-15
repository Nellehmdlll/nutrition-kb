# ADR 0001 — WAFCT 2019 comme source unique des valeurs nutritionnelles

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Portée** : socle de données de toute la KB

---

## Contexte

Le projet vise une base de connaissances nutritionnelle pour le Burkina Faso,
ciblant le diabète et l'hypertension. Deux sources candidates ont été examinées :

1. **FAO/INFOODS WAFCT 2019** — table de composition régionale ouest-africaine,
   1028 aliments, 57 composants, avec tagnames INFOODS standardisés et
   traçabilité de la provenance (drapeau `oa` = données non africaines).
2. **Table nationale du Burkina, Ministère de la Santé (2005)** — 188 aliments,
   13 colonnes.

Exigence forte du projet : ne construire les valeurs nutritionnelles que sur une
source fiable, traçable et citable.

## Décision

**La WAFCT 2019 est la source UNIQUE des valeurs nutritionnelles.**

Motifs déterminants :

- **Elle couvre les nutriments décisifs.** La table 2005 n'expose ni sodium ni
  potassium comme nutriments structurés (essentiels pour l'hypertension), et
  définit les glucides comme totaux fibres comprises (inexploitable pour le
  diabète). La WAFCT donne `NA`, `K`, `CHOAVLDF` (glucides disponibles) et
  `FIBTG` (fibres) séparément — vérifié ensuite à ~100 % de couverture.
- **Elle est traçable.** Le drapeau `oa` documente, valeur par valeur, les
  17,5 % de données non africaines. Une base qui déclare ses emprunts est plus
  fiable qu'une base opaque — pas moins.
- **Elle est légitime localement.** Ella Compaoré (Direction de la Nutrition du
  Burkina) figure parmi ses auteurs : la WAFCT est co-construite par le Burkina,
  successeur naturel de la table 2005.
- **La table 2005 renvoie elle-même vers la FAO** pour tout usage scientifique,
  et contient des valeurs impossibles non corrigées (ex. 217 g de protides/100 g).

## Conséquences

- Toutes les valeurs de `food_value` proviennent de la WAFCT ; le RAG peut donc
  toujours citer « FAO/INFOODS WAFCT 2019 ».
- La table 2005 n'est pas jetée : elle est réaffectée (voir ADR 0005) aux noms
  vernaculaires et à la classification pédagogique — jamais aux valeurs.
- Limite acceptée : aucune donnée « mesurée exclusivement au Burkina » à grande
  échelle n'existe publiquement. Le projet expose son incertitude (provenance,
  statut) plutôt que de prétendre à une précision qu'aucune source n'offre.
- Contrainte légale : usage non commercial autorisé avec citation ; licence FAO
  requise pour tout usage commercial (copyright@fao.org).

## Alternatives écartées

- **Table 2005 comme source des valeurs** : aveugle sur sodium/potassium/fibres,
  non traçable, erreurs avérées. Écartée.
- **Fusionner les valeurs des deux tables** : mélangerait des données de qualité
  et de traçabilité hétérogènes, détruisant la capacité de citation. Écartée.
