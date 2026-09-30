import pytest

from nutrition_kb.agent.detect_food import clear_cache, detect_food, detect_known_without_data

# Sous-ensemble representatif du vocabulaire final (365 mots), injecte
# directement : aucun de ces tests ne touche la DB.
KEYWORD_SET = {"gombo", "riz", "poisson", "to", "farine", "huile", "feuilles"}


@pytest.mark.parametrize(
    "question, expected",
    [
        ("le gombo est bon ?", ["gombo"]),
        ("du riz et du poisson", ["poisson", "riz"]),  # dedoublonne, ordre alphabetique
        ("cette assiette est sale", []),  # pas de faux positif : 'sel' n'est plus dans le vocabulaire
        ("raconte-moi ta journee", []),
        ("le tô fait grossir ?", ["to"]),  # accent gere par normalize()
    ],
)
def test_detect_food_cases(question, expected):
    assert detect_food(question, KEYWORD_SET) == expected


def test_detect_food_ignores_substring_inside_another_word():
    # 'to' ne doit matcher que comme MOT ENTIER, jamais comme fragment
    # d'un autre mot qui le contient par hasard (ex. 'tomate').
    keyword_set = {"to"}
    assert detect_food("une tomate bien mure", keyword_set) == []


def test_detect_food_deduplicates_repeated_keyword():
    keyword_set = {"riz"}
    assert detect_food("du riz, encore du riz, toujours du riz", keyword_set) == ["riz"]


def test_detect_food_resolves_vernacular_term_to_food_code():
    # Temps 3 : un terme de kb.food_local_match (injecte ici en dict, pas de
    # DB) renvoie son food_code, pas le terme lui-meme -- different du
    # comportement food_keyword (ou le mot se renvoie lui-meme).
    terms = {"bulvaka": ["04_038"]}
    assert detect_food("le bulvaka est bon ?", terms) == ["04_038"]


def test_detect_food_resolves_term_to_multiple_food_codes():
    # 'dolo' pointe vers DEUX food_code (biere de mil ET de sorgho) --
    # les deux doivent ressortir pour une seule mention du terme.
    terms = {"dolo": ["12_003", "12_004"]}
    assert detect_food("parle-moi du dolo", terms) == ["12_003", "12_004"]


def test_detect_food_combines_keyword_and_resolved_food_code_for_same_term():
    # Un terme present dans LES DEUX sources (ex. 'soumbala', deja un
    # mot-cle food_keyword ET desormais aussi vernaculaire apparie) cumule
    # les deux resultats -- ni l'un ni l'autre n'est perdu.
    terms = {"soumbala": ["soumbala", "03_042"]}
    assert detect_food("le soumbala, c'est quoi ?", terms) == ["soumbala", "03_042"]


def test_detect_food_still_accepts_raw_set_for_backward_compat():
    # Compat retro explicite : un set brut (API historique) continue de
    # fonctionner exactement comme avant cette extension.
    assert detect_food("le gombo est bon ?", {"gombo"}) == ["gombo"]


def test_detect_known_without_data_returns_term_not_food_code():
    # 'voaga' (kapok) est CONNU mais SANS food_code -- detect_known_without_data
    # le signale, detect_food lui ne renverrait jamais rien pour ce terme
    # (aucun food_code associe, cf. test suivant).
    terms = {"voaga": "kapok (Bombax costatum) absent de la WAFCT"}
    assert detect_known_without_data("c'est quoi le voaga ?", terms) == ["voaga"]


def test_detect_food_returns_nothing_for_known_without_data_term():
    # Le terme 'known-without-data' n'existe PAS dans le vocabulaire de
    # detect_food (il n'a pas de food_code) -- vide, pas une erreur.
    assert detect_food("c'est quoi le voaga ?", {"gombo": ["gombo"]}) == []


def test_detect_known_without_data_empty_for_totally_unknown_term():
    terms = {"voaga": "kapok absent"}
    assert detect_known_without_data("c'est quoi le zorglub ?", terms) == []


def test_cache_loads_once_and_can_be_refreshed(monkeypatch):
    """Meme contrat que detect_nutrient : pas de rechargement a chaque appel,
    mais rafraichissable explicitement (clear_cache / force_reload)."""
    import nutrition_kb.agent.detect_food as mod

    calls = []

    def fake_loader(lang="fr"):
        calls.append(lang)
        return {"riz"}

    monkeypatch.setattr(mod, "load_keyword_set", fake_loader)
    mod.clear_cache()

    # try/finally : meme raison que detect_nutrient -- le cache est un
    # GLOBAL du module, monkeypatch ne le restaure pas tout seul. Sans ce
    # nettoyage, le faux set {"riz"} polluerait les tests suivants (ex. le
    # routeur, qui appelle detect_food() sans keyword_set explicite).
    try:
        assert mod.detect_food("du riz") == ["riz"]
        assert mod.detect_food("du riz") == ["riz"]
        assert len(calls) == 1  # 2e appel : servi par le cache

        mod.detect_food("du riz", force_reload=True)
        assert len(calls) == 2  # force_reload contourne le cache

        mod.clear_cache()
        mod.detect_food("du riz")
        assert len(calls) == 3  # apres clear_cache, rechargement au prochain appel
    finally:
        mod.clear_cache()


def test_known_without_data_cache_loads_once_and_can_be_refreshed(monkeypatch):
    """Meme contrat de cache que detect_food, pour le vocabulaire
    connu-sans-donnees (cache SEPARE -- cf. clear_cache() qui vide les deux)."""
    import nutrition_kb.agent.detect_food as mod

    calls = []

    def fake_loader():
        calls.append(1)
        return {"voaga": "kapok absent"}

    monkeypatch.setattr(mod, "load_known_without_data_terms", fake_loader)
    mod.clear_cache()

    try:
        assert mod.detect_known_without_data("c'est quoi le voaga ?") == ["voaga"]
        assert mod.detect_known_without_data("c'est quoi le voaga ?") == ["voaga"]
        assert len(calls) == 1  # 2e appel : servi par le cache

        mod.detect_known_without_data("c'est quoi le voaga ?", force_reload=True)
        assert len(calls) == 2  # force_reload contourne le cache

        mod.clear_cache()
        mod.detect_known_without_data("c'est quoi le voaga ?")
        assert len(calls) == 3  # apres clear_cache, rechargement au prochain appel
    finally:
        mod.clear_cache()


# ---------------------------------------------------------------------------
# Tests contre la VRAIE base (kb.food_local_match, Temps 3) -- meme logique
# que test_agent_router.py : verifier l'orchestration reelle, pas des mocks.
# ---------------------------------------------------------------------------

def test_detect_food_real_db_resolves_bulvaka():
    clear_cache()
    try:
        assert detect_food("le bulvaka est bon ?") == ["04_038"]
    finally:
        clear_cache()


def test_detect_food_real_db_resolves_dolo_to_both_food_codes():
    clear_cache()
    try:
        assert detect_food("parle-moi du dolo") == ["12_003", "12_004"]
    finally:
        clear_cache()


def test_detect_known_without_data_real_db_flags_voaga():
    clear_cache()
    try:
        assert detect_known_without_data("c'est quoi le voaga ?") == ["voaga"]
        # detect_food ne renvoie RIEN pour ce meme terme : aucun food_code
        # associe (status='absent_wafct') -- c'est exactement le point du
        # cas special : connu, mais sans donnees, pas "inconnu".
        assert detect_food("c'est quoi le voaga ?") == []
    finally:
        clear_cache()


def test_detect_food_and_known_without_data_both_empty_for_unknown_term():
    clear_cache()
    try:
        assert detect_food("c'est quoi le zorglub ?") == []
        assert detect_known_without_data("c'est quoi le zorglub ?") == []
    finally:
        clear_cache()
