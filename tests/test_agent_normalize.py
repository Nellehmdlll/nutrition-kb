import pytest

from nutrition_kb.agent.normalize import normalize


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Sodium", "sodium"),
        ("SEL", "sel"),
        ("glucïdes", "glucides"),
        ("  potassium  ", "potassium"),
    ],
)
def test_normalize_cases(raw, expected):
    assert normalize(raw) == expected
