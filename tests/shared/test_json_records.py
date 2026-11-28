"""Every JSON reader in Sentinel applies one rule for text it cannot use."""

import json_records
import pytest


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"note": "\udcff"}', "surrogates not allowed"),
        ('{"note": NaN}', "NaN is not a JSON number"),
        ('{"note": -Infinity}', "-Infinity is not a JSON number"),
        ('{"note": 1e400}', "outside the range of a double"),
        ('{"note": 1' + "0" * 400 + "}", "outside the range of a double"),
        ("[" * 100_000 + "]" * 100_000, "nested too deeply"),
    ],
    ids=[
        "bytes that are not utf-8",
        "not a number",
        "infinity",
        "decimal outside the range of a double",
        "integer outside the range of a double",
        "nested too deeply",
    ],
)
def test_text_a_strict_reader_rejects_does_not_parse(text: str, message: str) -> None:
    """Validates: SettingsThatDefeatTheHooksAreReported, CodexHookInstallKeepsTheUsersHooks."""
    with pytest.raises(ValueError, match=message):
        json_records.parse_json(text)


def test_numbers_inside_the_range_of_a_double_parse() -> None:
    assert json_records.parse_json("[1e308, -1e308, 179769313486231570000000, 0.5]") == [
        1e308,
        -1e308,
        179769313486231570000000,
        0.5,
    ]
