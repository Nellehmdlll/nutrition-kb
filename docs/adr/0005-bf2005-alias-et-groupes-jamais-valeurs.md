# ADR 0005 — La table nationale BF 2005 alimente les alias et la classification, jamais les valeurs

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Portée** : intégration multi-sources de la KB

---

## Contexte

La table nationale du Burkina (Ministère de la Santé, 2005) a été écartée comme
source de valeurs (ADR 0001) : aveugle sur sodium/potassium/fibres, non traçable,
erreurs avérées. Mais elle apporte trois choses que la WAFCT n'a pas :

1. **Un lexique vernaculaire** (mooré) : *bulvaka*, *mana*, *soumbala*, *kagha*,
   *arzantiga*, *voaga*… Un utilisateur à Ouagadougou cherche « bulvaka », pas
   « Corchorus olitorius ». Sans ce lexique, l'app est inutilisable par sa cible.
2. **Une classification pédagogique** en 3 groupes (énergétiques / constructeurs
   / protecteurs), familière au public burkinabè.
3. **Une légitimité institutionnelle** (document du Ministère de la Santé).

## Décision

**La KB est multi-sources dès la conception. La table 2005 alimente `food_alias`
(noms locaux) et la classification pédagogique — et JAMAIS `food_value`.**

Règle inscrite dans le schéma, pas seulement dans les têtes :

- Les valeurs nutritionnelles proviennent exclusivement de la WAFCT 2019.
- La table 2005 peut servir de **jeu de contrôle** : un écart important entre
  WAFCT et BF-2005 sur un même aliment lève une alerte à examiner.
- Chaque alias porte sa `source_id` : la provenance de chaque nom est traçable.

## Conséquences

- Le schéma gagne les tables `source` (multi-sources) et `food_alias` dès le
  départ — architecture plus solide qu'un modèle mono-source.
- L'app peut afficher les noms mooré (différenciateur produit majeur) tout en
  garantissant que les chiffres restent WAFCT (citables).
- L'appariement des ~188 aliments 2005 aux 1028 codes WAFCT est un chantier de
  matching de noms (potentiellement flou) : identifié comme lot de travail
  distinct, différé pour ne pas bloquer la pipeline principale.
- Mélanger les valeurs des deux tables reste interdit : cela contaminerait la
  base et détruirait la citation.

## Alternatives écartées

- **Ignorer la table 2005** : perdrait le lexique mooré et la légitimité
  institutionnelle. Écarté.
- **Importer aussi ses valeurs** (même à titre de complément) : rouvrirait le
  problème de traçabilité et d'erreurs. Écarté sans exception.
