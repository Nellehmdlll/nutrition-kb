import pytest

from nutrition_kb.agent.detect_food import clear_cache, detect_food

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
