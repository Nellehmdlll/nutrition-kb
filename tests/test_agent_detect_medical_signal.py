import pytest

from nutrition_kb.agent.detect_medical_signal import detect_medical_signal


@pytest.mark.parametrize(
    "question, expected",
    [
        ("ma glycemie est a 18", True),
        ("ma glycémie est à 18", True),  # accent gere par normalize()
        ("mon taux est de 140", True),
        ("ma tension est a 15", True),
        ("j'ai 18 ans", False),  # nombre present, mais AUCUN mot-cle medical
        ("ma tension m'inquiete", False),  # mot-cle present, mais AUCUN nombre
        ("raconte-moi ta journee", False),  # ni l'un ni l'autre
        ("le gombo contient combien de sucre", False),  # 'sucre' present, pas de nombre
    ],
)
def test_detect_medical_signal_cases(question, expected):
    assert detect_medical_signal(question) == expected
