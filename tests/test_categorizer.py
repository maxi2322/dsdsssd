from receipt_sorter.categorizer import categorize, categorize_by_rules
from receipt_sorter.config import AppConfig


def test_categorize_by_rules_matches_keyword():
    rules = {"tankstelle": "Fahrzeugkosten"}
    assert categorize_by_rules("Shell Tankstelle Berlin", rules) == "Fahrzeugkosten"


def test_categorize_by_rules_no_match_returns_none():
    rules = {"tankstelle": "Fahrzeugkosten"}
    assert categorize_by_rules("Buchhandlung Meyer", rules) is None


def test_categorize_by_rules_no_merchant_returns_none():
    rules = {"tankstelle": "Fahrzeugkosten"}
    assert categorize_by_rules(None, rules) is None


def test_categorize_uses_rule_before_llm(monkeypatch):
    config = AppConfig()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM haette nicht aufgerufen werden duerfen")

    monkeypatch.setattr("receipt_sorter.categorizer.categorize_with_llm", fail_if_called)
    result = categorize("Shell Tankstelle", 45.0, "text", config)
    assert result.category == "Fahrzeugkosten"
    assert result.source == "regel"


def test_categorize_falls_back_when_llm_disabled():
    config = AppConfig()
    config.llm.enabled = False
    result = categorize("Unbekannter Haendler XYZ", 10.0, "irgendein text", config)
    assert result.category == "Sonstiges"
    assert result.source == "fallback"


def test_categorize_falls_back_without_api_key(monkeypatch):
    config = AppConfig()
    monkeypatch.delenv(config.llm.api_key_env, raising=False)
    result = categorize("Unbekannter Haendler XYZ", 10.0, "irgendein text", config)
    assert result.category == "Sonstiges"
    assert result.source == "fallback"
