# ADR 0004 — Couche raw : sources originales hashées + extraction Parquet 100 % string

- **Statut** : Accepté
- **Date** : 2026-07-15
- **Portée** : couche d'ingestion (bronze)

---

## Contexte

Contrainte fondatrice du projet : ne jamais modifier les données sources, et
pouvoir prouver à tout moment la fidélité de la donnée ingérée. La question
« Parquet ou CSV pour la couche raw ? » a d'abord été posée comme un choix de
format, avant de révéler une question plus profonde : **qu'est-ce qui constitue
la preuve ?**

## Décision

**La preuve, c'est le fichier source original conservé + son empreinte SHA-256.
L'extraction se fait en Parquet, 100 % typé `string`, sans aucune coercition.**

Structure :

```
raw/
├── sources/
│   ├── WAFCT_2019.xlsx              ← fichier ORIGINAL, tel quel
│   ├── BF_table_nationale_2005.pdf  ← idem
│   └── MANIFEST.json                ← SHA-256, taille, date, provenance, licence
└── extracted/
    └── *.parquet                    ← projection fidèle, tout en string
```

Principes :

- **La couche raw ne type rien.** Tout est `string` : `"0.5"`, `"[2.5]"`, `"tr"`,
  `"oa"`, `""`. Typer, c'est interpréter ; interpréter, c'est décider ; et raw
  est la couche où l'on ne décide rien. `read_excel(dtype=str)` — invariant.
- **La preuve passe par le hash, pas par la lisibilité.** Comme l'original est
  conservé et hashé, l'extrait n'a pas besoin d'être lisible à l'œil : n'importe
  qui peut vérifier l'intégrité par `sha256sum`. Un CSV « lisible » ne prouve
  rien (altérable sans trace).
- **Parquet plutôt que CSV** une fois la lisibilité hors sujet : format binaire
  typé (pas de round-trip texte ambigu — les en-têtes WAFCT contiennent des
  `\n`, le séparateur décimal `,` francophone entre en collision avec le CSV,
  Excel mutile silencieusement un CSV réenregistré), et métadonnées (hash source,
  feuille, date, version du script) embarquées DANS le fichier.
- **Traçabilité par ligne** : `_source_file`, `_source_sheet`, `_source_row`
  (numéro de ligne Excel réel), `_ingested_at`.
- **Idempotence** : réexécution identique ; si le SHA-256 d'une source a changé,
  erreur bloquante — jamais d'écrasement silencieux.

### Précision importante sur la nature de la fidélité

L'extraction passe par openpyxl, qui type déjà les cellules. La couche raw est
donc une **projection via openpyxl**, pas une copie binaire octet-à-octet :
`str(float(...))` peut différer de la graphie du XML (ex. `"614.30000000000007"`
→ `"614.3000000000001"`) sur ~50 cellules, sans aucune perte numérique
(`float(a) == float(b)`). La preuve d'intégrité reste le SHA-256 de l'original,
pas l'octet du Parquet. Fidélité « au double IEEE-754 » assumée.

## Conséquences

- Reproductibilité totale : tout doute sur une valeur remonte à la cellule via
  `_source_row`, et à l'octet via le fichier original hashé.
- Le test de fidélité doit emprunter un **chemin indépendant** (lecture XML brute
  via zipfile), sinon il valide openpyxl contre openpyxl (circulaire). Il doit
  aussi vérifier la **complétude** (nombre de cellules), pas seulement la
  non-corruption des cellules échantillonnées — deux propriétés distinctes.
- Les feuilles non tabulaires (Introduction, Data sources) sont extraites quand
  même, en grille de cellules brutes : raw ne trie pas.

## Alternatives écartées

- **CSV** : texte ambigu (encodage, `\n` dans en-têtes, collision décimale FR,
  corruption Excel), non typé. La lisibilité/diffabilité qu'il offre est rendue
  inutile par la conservation de l'original. Écarté.
- **Extraction typée en raw** : détruirait l'information de qualité (`[...]`,
  `tr`) et prendrait des décisions interdites à ce niveau. Écarté.
- **Copie binaire octet-à-octet sans openpyxl** : coût élevé (gérer soi-même
  sharedStrings, formats, fusions) pour un bénéfice numérique nul. Écarté.
