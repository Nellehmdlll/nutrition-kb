# ADR 0007 — La génération de prose des chunks vit en Python, pas en SQL

- **Statut** : Accepté — **complété le 2026-07-15** (le jour même, cas du zéro structurel)
- **Date** : 2026-07-15
- **Décideurs** : l'équipe (Sawadogo Rahimah + mentor technique IA)
- **Portée** : couche RAG (génération des chunks, `gold.chunk`)

---

## Contexte

`gold.chunk.content` doit contenir une prose autoportante, citable, qui
transporte le statut/provenance de chaque nutriment (cf. ADR 0006). Il fallait
décider où cette prose est produite : dans la vue SQL elle-même (`CASE`,
concaténation de chaînes), ou en Python, à partir d'une vue SQL qui ne fait
que rassembler les données.

Le choix s'est fait par construction, sans y penser au départ : les vues gold
(`v_food_base`, `v_food_diabetes`, `v_food_hypertension`) exposent des
colonnes typées (`sodium_mg`, `sodium_status`, `sodium_provenance`...), et des
fonctions Python (`render_hypertension_chunk`, etc.) assemblent le texte final.

## Décision

**La génération de prose des chunks vit en Python, pas en SQL, parce que c'est
de la présentation.**

La formulation d'une phrase (« environ 61 mg de sodium, valeur estimée,
d'après des données non africaines ») va changer souvent : reformulations,
ajout des alias mooré, nuances de vocabulaire, corrections de grammaire
(l'élision « de énergie » → « d'énergie » a été corrigée trois fois en cours
de route). Aucun de ces changements n'est un changement de données.

- **SQL** produit des faits typés et vérifiables (valeur, statut, provenance) :
  c'est la couche où l'exactitude se garantit (`CHECK`, `FOREIGN KEY`, vues
  contrôlées par des requêtes de non-régression).
- **Python** produit la formulation : c'est la couche où la prose se teste
  (jeux de cas limites, comme les 4 aliments-témoins de l'angle hypertension)
  et se corrige par un commit, jamais par une migration de base.

## Conséquences

**Positives**
- Une reformulation de phrase = un commit sur `chunks.py`, testé par
  `pytest`, sans toucher `schema.sql` ni les données.
- Les fonctions de rendu sont pures (une ligne de vue gold → une chaîne) :
  testables isolément, sans base de données, comme `parse_value`.
- Le SQL reste focalisé sur ce qu'il fait bien : agréger, typer, contraindre.

**Négatives / coûts**
- Deux couches à maintenir en cohérence : si une vue gold change de colonne,
  les fonctions Python qui la lisent doivent être mises à jour (déjà vécu :
  l'ajout de `sodium_status`/`potassium_status` à `v_food_hypertension`).
- La prose n'est pas requêtable en SQL (on ne peut pas faire un `WHERE
  content LIKE '%estimée%'` fiable pour de l'analytique) — non-problème ici,
  puisque les colonnes typées sous-jacentes (`status`, `provenance`) restent
  interrogeables directement.

## Alternatives écartées

- **Génération en SQL** (`CASE WHEN status = 'ESTIMATED' THEN ... END`
  concaténé dans la vue) : chaque reformulation deviendrait une migration de
  vue. Contraire à la nature du texte, qui est de la présentation, pas une
  vérité à figer. Écartée.

---

## Complément — le zéro structurel change le DISCOURS, pas seulement le chiffre

Trouvé en relisant le chunk diabète de l'huile de maïs : « contient environ
0 g de glucides disponibles […] apporte aussi environ 0 g de fibres, qui
ralentissent l'absorption des glucides. » Phrase grammaticalement correcte,
sémantiquement absurde (rien à ralentir), et un faux positif de recherche —
le chunk contient « glucides », « fibres », « glycémie », donc remonte sur
une question diabète pour ne rien dire d'utile.

212 aliments sur 1028 (21 %) ont des glucides disponibles mesurés à zéro —
surtout des viandes et poissons, pas des cas exotiques. Deux options :
supprimer leur chunk diabète, ou changer sa forme. La suppression perdrait
une vraie réponse utile (« puis-je manger du poisson grillé ? » → « oui,
aucun impact glycémique direct » est une information thérapeutique
précieuse, pas un remplissage). **Décision : on garde le chunk, mais quand
la grandeur centrale de l'angle est nulle ou non mesurée, la prose change de
forme — une phrase courte, adaptée au sens du zéro, puis on s'arrête**
(fibres et densité glucidique n'ont plus de sens à énoncer une fois qu'il
n'y a pas de glucides à moduler).

Ceci renforce la décision initiale plutôt que de la remettre en cause :
c'est précisément parce que ce genre de branchement est **sémantique** (la
signification d'un zéro dépend du domaine — nutrition, pas type SQL) qu'il
n'a pas sa place dans une vue. Une vue peut dire qu'une valeur est nulle ;
seul le code de présentation peut décider que ce zéro-là mérite un autre
discours.
