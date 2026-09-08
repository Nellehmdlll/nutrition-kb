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

## 3. Le garde-fou anti-invention (agent LLM) ne détecte que l'invention CHIFFRÉE

- **Symptôme** : le LLM peut affirmer une caractéristique nutritionnelle
  fausse sans qu'aucun garde-fou ne s'en aperçoive (ex. « le quinoa est riche
  en fer »), tant qu'aucun chiffre accompagné d'une unité (mg, g, kcal...)
  n'apparaît dans la phrase.
- **Cause** : le garde-fou code (`llm_agent.py`, `_looks_fabricated`) repose
  sur une regex qui cherche un motif « chiffre + unité nutritionnelle » dans
  la réponse, combiné à « aucun outil n'a renvoyé de données ». Une
  affirmation qualitative sans valeur chiffrée n'a pas de signal exploitable
  aussi simplement — l'ancrer nécessiterait de comparer le SENS de la phrase
  aux données réellement disponibles, un problème bien plus dur qu'une regex
  (et non résolu ici).
- **Piste** : rien de simple identifié pour l'instant. Pistes à explorer plus
  tard : forcer systématiquement un appel d'outil avant toute affirmation
  portant sur un aliment (contrainte de function calling plus stricte), ou un
  second passage LLM « juge » qui vérifie chaque affirmation contre les
  données effectivement récupérées dans le tour.
- **Statut** : assumé — risque résiduel connu, non couvert par le code actuel.
- **Voir aussi** : `src/nutrition_kb/agent/llm_agent.py` (`_looks_fabricated`,
  `_NUTRITION_VALUE_RE`), `tests/test_agent_llm_agent.py`.

## 4. Le LLM peut donner un conseil médical/diététique prescriptif malgré l'interdiction v1

- **Symptôme** : le LLM répond parfois par une consigne de conduite interdite
  en v1 (observé : « Oui, vous pouvez manger du soumbala » à une question sur
  l'hypertension), alors que `docs/system_prompt.md` interdit explicitement de
  dicter la conduite (section FIDÉLITÉ AUX DONNÉES : décrire = autorisé,
  dicter = interdit).
- **Cause** : cette frontière n'est appliquée QUE par le system prompt — rien
  côté code ne vérifie ni ne bloque une réponse qui la franchit. Un modèle de
  8B tournant en local ne suit pas les instructions de prompt de façon fiable
  à 100 %, quelle que soit leur clarté.
- **Piste** : le prompt a été renforcé avec des exemples explicites
  autorisé/interdit et un test simple à s'appliquer (cf.
  `docs/system_prompt.md`, section FIDÉLITÉ AUX DONNÉES). Un détecteur côté
  code (ex. regex sur les tournures de permission/injonction : « vous
  pouvez », « évitez », « vous devriez »...) est envisagé mais volontairement
  PAS implémenté maintenant — faux positifs/négatifs mal maîtrisés sans avoir
  observé davantage de cas réels d'abord.
- **Statut** : PARTIELLEMENT réglé, honnêtement — le renforcement du prompt
  réduit le risque, il ne l'élimine PAS. C'est un pansement, pas une barrière
  garantie. Faille connue et assumée pour cette version.
- **Voir aussi** : `docs/system_prompt.md` (section FIDÉLITÉ AUX DONNÉES,
  sous-section « Exemples concrets »).

## 5. « Faux ami lexical » : search_vector peut substituer un aliment absent par un aliment présent qui lui ressemble par le nom

- **Symptôme** : un aliment ABSENT de la base mais lexicalement proche d'un
  aliment PRÉSENT peut voir les valeurs de ce voisin retournées par
  `search_vector` et présentées comme réponse, sans que rien ne signale la
  substitution. Exemple mesuré : « foie gras » (absent) fait remonter « foie
  d'agneau »/« foie de bœuf » (mot « foie » partagé).
- **Preuve chiffrée** (mesurée, `intfloat/multilingual-e5-small`, seuil actuel
  0.18) :
  - `foie gras` (absent) → `foie d'agneau`/`foie de bœuf` à distance **0.156**
    — **sous le seuil, donc retourné** comme un match valide.
  - `foie de bœuf` (présent, vrai match) → lui-même à distance **0.101**.
  - `quinoa`, `sushis`, `caviar` (absents, sans voisin lexical proche) →
    distance **0.18–0.20** — au-dessus du seuil, **correctement rejetés**
    (`no_result`).
- **Cause** : `search_vector` est une recherche par PROXIMITÉ SÉMANTIQUE, pas
  par nom exact (cf. ADR 0009). Deux aliments qui partagent un mot ont un sens
  proche pour l'embedding même quand ce sont des aliments différents. Le seuil
  ne peut pas les séparer : le faux ami (0.156) vit dans la même zone de
  distance que de possibles vrais matchs un peu plus lointains — le baisser
  pour éliminer le faux ami éliminerait aussi des matchs légitimes.
- **Pourquoi pas de barrière côté code** : vérifier que le chunk retourné
  correspond bien à l'aliment demandé exigerait que `detect_food()`
  reconnaisse l'aliment nommé dans la question — or un aliment ABSENT de la
  base n'est par construction pas dans `kb.food_keyword`, donc `detect_food()`
  est aveugle exactement sur les cas où cette vérification serait utile.
  Option écartée pour cette raison (pas par facilité).
- **Atténuation** : le prompt système demande désormais explicitement à
  l'agent de vérifier que l'aliment des données correspond à l'aliment
  demandé, et de signaler toute substitution AVANT toute valeur (cf.
  `docs/system_prompt.md`, section FIDÉLITÉ AUX DONNÉES). Réduit le risque,
  ne l'élimine PAS — un LLM de 8B peut oublier de le faire.
- **Statut** : limite connue, assumée pour la v1.
- **Piste v2** : liste d'aliments connus-absents (pour un rejet explicite
  précoce), ou comparaison nom-à-nom floue question↔chunk (approche
  différente de `detect_food()`, pas soumise au même angle mort). Chantier
  séparé, pas engagé ici.
- **Voir aussi** : `docs/adr/0009-retrieval-asymetrique-et-limites-du-vecteur.md`
  (même famille que négation/magnitude), `docs/system_prompt.md` (section
  FIDÉLITÉ AUX DONNÉES).
