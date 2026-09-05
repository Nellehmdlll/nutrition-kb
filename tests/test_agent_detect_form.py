import pytest

from nutrition_kb.agent.detect_form import detect_form


@pytest.mark.parametrize(
    "question, expected",
    [
        ("quel aliment est le plus sale", "ranking"),
        ("le gombo est bon pour moi ?", "advice"),
        ("quel aliment contient le moins de sodium", "ranking"),
        ("y a-t-il plus de fibres dans le mil ?", "ranking"),
        ("cet aliment est riche en fer", "ranking"),
        ("cet aliment est pauvre en fibres", "ranking"),
        ("il y a trop de sucre dans ce plat", "ranking"),
        ("y a beaucoup de sel dans le pain ?", "ranking"),
        ("raconte-moi l'histoire du gombo", "advice"),
        ("quel aliment est bon pour le diabete", "ranking"),  # marqueur 'quel aliment'
    ],
)
def test_detect_form_cases(question, expected):
    assert detect_form(question) == expected


def test_detect_form_known_collision_sale_dirty():
    # LIMITE CONNUE, documentee dans detect_form.py : 'salé' normalise en
    # 'sale', qui collide avec le mot francais "sale" (dirty). Verrouille le
    # comportement ACTUEL pour qu'un futur changement soit une decision
    # explicite (apres avoir vu l'agent tourner), pas une regression
    # accidentelle decouverte au hasard.
    assert detect_form("cette assiette est sale") == "ranking"


def test_detect_form_known_collision_sucre_nutrient():
    # Meme limite : 'sucré' normalise en 'sucre', qui collide avec le nom
    # du nutriment "sucre". Verrouille aussi ce comportement actuel.
    assert detect_form("combien de sucre dans le riz") == "ranking"
