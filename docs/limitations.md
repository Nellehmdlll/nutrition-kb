# Registre des limitations connues de l'agent

Les trous qu'on assume temporairement pour faire tourner le squelette, pas
des bugs à corriger dans l'urgence — des décisions de portée, notées pour
qu'on les règle en connaissance de cause plus tard, pas qu'on les redécouvre
par hasard dans six mois.

Format par entrée : **symptôme** (ce qu'on observe), **cause** (pourquoi),
**piste** (comment on pense le résoudre), **statut**.

Ce fichier documente ; il ne remplace ni les ADR (`docs/adr/`, pour les
décisions déjà prises et leurs alternatives écartées) ni les commentaires
« LIMITE CONNUE » laissés directement dans le code aux endroits concernés.
Il sert à retrouver d'un coup d'œil toutes les limites actives du système,
sans avoir à relire chaque fichier.

---

## 1. Un adjectif de classement (« salé ») ne route pas vers SQL faute de nutriment nommé

- **Symptôme** : « quel aliment est le plus salé ? » renvoie `clarify` au lieu
  de router vers SQL (classement sur le sodium).
- **Cause** : `'salé'` a été retiré de `nutrient_synonym` (collision avec
  `'sale'` = dirty) et vit maintenant dans `detect_form` comme marqueur de
  `'ranking'` — mais `detect_form` ne dit PAS sur QUEL nutriment classer.
  L'arbre exige un nutriment nommé à l'étape 2, donc « le plus salé » tombe
  en `clarify` faute de nutriment.
- **Piste** : enrichir `detect_form` pour qu'il renvoie aussi le nutriment
  implicite d'un adjectif (`'salé'` → `NA`, `'sucré'` → `CHOAVLDF`, et
  probablement `'gras'`, `'riche'`, `'léger'`...). À traiter en bloc quand on
  affinera `detect_form`.
- **Statut** : assumé pour la v1 du squelette.
- **Voir aussi** : `src/nutrition_kb/agent/router.py` (docstring, section
  « LIMITE CONNUE de l'ordre strict »), `tests/test_agent_router.py::test_route_clarify_when_ranking_marker_names_nothing`.

## 2. Un classement SQL est toujours descendant, même pour « le moins » / « pauvre en »

- **Symptôme** : « quel aliment a le moins de sodium ? » et « quel aliment a
  le plus de sodium ? » renvoient le même classement (les plus salés en
  tête), alors que la question demande l'inverse pour la première.
- **Cause** : `execute()` appelle `query_sql('top_by_nutrient', ...,
  order='desc')` avec `order` figé en dur — `detect_form` ne distingue
  aujourd'hui qu'une seule forme `'ranking'`, sans dire si le classement doit
  être ascendant ou descendant. `order='asc'` est bien géré par l'outil
  (`query_sql`), mais rien en amont ne sait encore le demander.
- **Piste** : quand `detect_form` sera affiné (cf. limite n°1, même chantier),
  lui faire distinguer les marqueurs « le moins », « pauvre en » (→ `asc`) des
  marqueurs « le plus », « riche en », « trop de », « beaucoup de » (→
  `desc`), et faire porter ce choix par la décision plutôt que par une
  constante fixe dans `execute()`.
- **Statut** : assumé pour la v1 du squelette.
- **Voir aussi** : `src/nutrition_kb/agent/execute.py` (constante
  `DEFAULT_ORDER`), `src/nutrition_kb/agent/tools.py` (`_top_by_nutrient`,
  qui sait déjà faire `asc`).
