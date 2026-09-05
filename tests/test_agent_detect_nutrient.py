import pytest

from nutrition_kb.agent.detect_nutrient import clear_cache, detect_nutrient

# Meme contenu que le peuplement de l'etape B, MOINS 'sale' (salé retire de
# la table synonymes : collision avec le mot francais "sale" = dirty, cf.
# ajustement 2). Injecte directement : aucun de ces tests ne touche la DB.
SYNONYM_MAP = {
    "calories": "ENERC",
    "energie": "ENERC",
    "fibres": "FIBTG",
    "glucides": "CHOAVLDF",
    "potassium": "K",
    "sel": "NA",
    "sodium": "NA",
    "sucre": "CHOAVLDF",
}


@pytest.mark.parametrize(
    "question, expected",
    [
        ("y a beaucoup de sel ?", ["NA"]),
        ("raconte-moi le gombo", []),
        ("combien de potassium dans la banane ?", ["K"]),
        ("ÉNERGIE ?", ["ENERC"]),
        ("Quelle quantite de SUCRE dans ce plat", ["CHOAVLDF"]),
        # extraction, pas selection : les DEUX nutriments mentionnes ressortent.
        # Ordre = ordre du synonym_map (ici alphabetique : 'sel' avant 'sucre').
        ("sel et sucre", ["NA", "CHOAVLDF"]),
    ],
)
def test_detect_nutrient_cases(question, expected):
    assert detect_nutrient(question, SYNONYM_MAP) == expected


def test_detect_nutrient_ignores_substring_inside_another_word():
    # "sel" ne doit matcher que comme MOT ENTIER, jamais comme fragment
    # d'un autre mot qui le contient par hasard.
    synonym_map = {"sel": "NA"}
    assert detect_nutrient("un mot invente artisel", synonym_map) == []


def test_detect_nutrient_deduplicates_repeated_tagname():
    # 'sel' et 'sodium' pointent tous deux vers NA : les mentionner tous les
    # deux ne doit pas produire NA en double dans la liste.
    synonym_map = {"sel": "NA", "sodium": "NA"}
    assert detect_nutrient("du sel et du sodium", synonym_map) == ["NA"]


def test_detect_nutrient_no_longer_matches_dirty_sale():
    # 'sale' (sale/dirty, francais courant) ne doit plus JAMAIS matcher NA :
    # 'salé' a ete retire de la table synonymes precisement pour ca.
    assert detect_nutrient("cette recette est sale", SYNONYM_MAP) == []


def test_cache_loads_once_and_can_be_refreshed(monkeypatch):
    """Le cache ne doit PAS recharger a chaque appel, mais doit pouvoir
    etre force -- via clear_cache() ou force_reload=True."""
    import nutrition_kb.agent.detect_nutrient as mod

    calls = []

    def fake_loader(lang="fr"):
        calls.append(lang)
        return {"sel": "NA"}

    monkeypatch.setattr(mod, "load_synonym_map", fake_loader)
    mod.clear_cache()  # etat propre, independant de l'ordre d'execution des tests

    # try/finally : le cache est un GLOBAL du module -- monkeypatch restaure
    # load_synonym_map a la fin du test, mais PAS le cache lui-meme. Sans ce
    # nettoyage, la fausse map {"sel": "NA"} resterait active pour tous les
    # tests suivants dans la meme session pytest (ex. les tests du routeur,
    # qui appellent detect_nutrient() sans synonym_map explicite -- vecu :
    # ce bug a reellement pollue test_agent_router.py avant d'etre corrige).
    try:
        assert mod.detect_nutrient("du sel") == ["NA"]
        assert mod.detect_nutrient("du sel") == ["NA"]
        assert len(calls) == 1  # 2e appel : servi par le cache, pas de rechargement

        mod.detect_nutrient("du sel", force_reload=True)
        assert len(calls) == 2  # force_reload contourne le cache explicitement

        mod.clear_cache()
        mod.detect_nutrient("du sel")
        assert len(calls) == 3  # apres clear_cache, rechargement au prochain appel
    finally:
        mod.clear_cache()
