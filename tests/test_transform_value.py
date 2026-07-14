import pytest

from nutrition_kb.transform.value import ParsedValue, Provenance, ValueStatus, parse_value


@pytest.mark.parametrize(
    "raw, is_oa, expected",
    [
        ("1.00", False, ParsedValue(1.0, ValueStatus.MEASURED, Provenance.AFRICAN)),
        ("[0.2]", False, ParsedValue(0.2, ValueStatus.ESTIMATED, Provenance.AFRICAN)),
        ("tr", False, ParsedValue(None, ValueStatus.TRACE, Provenance.AFRICAN)),
        ("4.6", True, ParsedValue(4.6, ValueStatus.MEASURED, Provenance.NON_AFRICAN)),
        ("[61]", True, ParsedValue(61.0, ValueStatus.ESTIMATED, Provenance.NON_AFRICAN)),
        ("", False, ParsedValue(None, ValueStatus.NOT_DETERMINED, Provenance.AFRICAN)),
        (None, False, ParsedValue(None, ValueStatus.NOT_DETERMINED, Provenance.AFRICAN)),
    ],
)
def test_parse_value_cases(raw, is_oa, expected):
    assert parse_value(raw, is_oa) == expected


def test_parse_value_unparsable_raises():
    with pytest.raises(ValueError):
        parse_value("abc", False)
