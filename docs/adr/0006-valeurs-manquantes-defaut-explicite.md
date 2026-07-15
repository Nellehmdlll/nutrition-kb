# ADR 0006 — Valeurs manquantes : calculer avec un défaut, transporter l'imperfection

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Décideurs** : l'équipe (Sawadogo Rahimah. + mentor technique)
- **Portée** : couche gold, vues destinées à l'application et au RAG

---

## Contexte

La source (FAO/INFOODS WAFCT 2019) est incomplète par endroits. Trois formes
d'imperfection coexistent, déjà modélisées en couche silver :

- `TRACE` — présent mais non quantifié (`value IS NULL`)
- `NOT_DETERMINED` — jamais mesuré (absence de ligne dans `food_value`)
- `NON_AFRICAN` — mesuré, mais sur un échantillon non africain

La couche gold doit produire des grandeurs **calculées** pour l'application —
par exemple les glucides nets = glucides disponibles − fibres. Or un opérande
peut être manquant. Le cas déclencheur : `net_carbs = CHOAVLDF − FIBTG`, quand
`FIBTG` est `NOT_DETERMINED`.

## Problème

Deux réflexes naïfs, tous deux dangereux dans un contexte de santé :

1. **Laisser le calcul à NULL** (`x − NULL = NULL`). L'aliment disparaît de
   l'affichage. L'utilisateur ne voit rien — non pas parce que l'aliment est
   inintéressant, mais parce que NOTRE donnée est incomplète. On punit
   l'utilisateur de nos trous.

2. **Remplacer le manquant par une valeur par défaut et l'oublier**
   (`x − COALESCE(FIBTG, 0)`). L'aliment s'affiche avec un chiffre, mais ce
   chiffre est présenté comme s'il était complet. Si les fibres réelles valaient
   50 g, on surestime gravement les glucides nets — et on ment par omission.

## Décision

**On calcule toujours avec un défaut explicite, ET on transporte l'imperfection
dans une colonne séparée, jusqu'à l'utilisateur final.**

Concrètement, toute grandeur dérivée d'un opérande potentiellement manquant
produit TROIS sorties, jamais une seule :

| Sortie | Rôle | Exemple |
|---|---|---|
| la valeur brute de l'opérande | vérité de la source, **NULL préservé** | `fiber_g` (NULL si inconnu) |
| la grandeur calculée avec défaut | l'app voit toujours un chiffre | `net_carbs_g` |
| un drapeau booléen | signale que le défaut a été appliqué | `fiber_is_assumed_zero` |

Le choix du **sens du défaut** suit une règle fixe :

> Quand une valeur par défaut est inévitable, choisir celle dont l'erreur va
> dans le **sens sûr** pour le patient.

Pour les fibres et le diabète : les fibres se soustraient, donc `fibres = 0`
**surestime** les glucides nets. Surestimer le sucre effectif est prudent
(le diabétique évite ou dose vers le haut). Le défaut `0` est donc le sens sûr.
Ce raisonnement doit être refait pour chaque nouvelle grandeur — il ne se
généralise pas aveuglément.

## Conséquences

**Positives**
- L'utilisateur voit toujours une information exploitable (pas de trou muet).
- La vérité brute de la source est préservée (`NULL`) : une donnée corrigée
  dans 6 mois s'intègre sans réécrire l'historique ni le calcul.
- L'assistant IA peut formuler une réponse honnête : « environ X g de glucides
  nets — teneur en fibres inconnue, valeur probablement surestimée ».
- Cohérent avec les décisions déjà prises sur `TRACE` (ADR sur value.py) et sur
  `provenance` : même principe unificateur — **calculer au mieux, transporter
  l'imperfection à côté**.

**Négatives / coûts**
- Chaque grandeur dérivée coûte 2 à 3 colonnes au lieu d'1. Les vues gold sont
  plus larges.
- L'app ET le RAG doivent effectivement LIRE les drapeaux et les afficher.
  Un drapeau ignoré en aval annule tout le bénéfice : la responsabilité se
  déplace vers la couche présentation, elle ne disparaît pas.
- Un défaut « sûr » reste un choix discutable au cas par cas ; il doit être
  documenté pour chaque grandeur, pas appliqué mécaniquement.

## Portée d'application

Cette politique s'applique à TOUTE grandeur calculée en gold à partir d'un
opérande pouvant être `NULL` / `NOT_DETERMINED` / `TRACE`. Toute nouvelle vue
dérivée doit exposer ses drapeaux d'hypothèse.

## Alternatives écartées

- **Imputation statistique** (remplacer le manquant par la moyenne du groupe
  d'aliments) : inventerait une donnée plausible mais fausse, indistinguable
  d'une vraie mesure. Contraire au principe de traçabilité du projet. Écartée.
- **Exclure les aliments à opérande manquant** : ampute le catalogue, et
  précisément sur les aliments les moins documentés — souvent les aliments
  locaux, ceux qui font la valeur du projet. Écartée.
