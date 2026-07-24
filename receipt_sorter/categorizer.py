from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

FALLBACK_CATEGORY = "Sonstiges"


@dataclass
class CategoryResult:
    category: str
    source: str  # "regel" | "ki" | "fallback"
    note: str = ""


def categorize_by_rules(merchant: Optional[str], rules: dict) -> Optional[str]:
    """Schnelle, kostenlose Zuordnung anhand von Stichwörtern im Händlernamen."""
    if not merchant:
        return None
    lower = merchant.lower()
    for keyword, category in rules.items():
        if keyword in lower:
            return category
    return None


def _build_prompt(merchant: Optional[str], amount: Optional[float], raw_text: str, categories: list) -> str:
    snippet = raw_text.strip()[:800]
    return (
        "Du bist ein Assistent fuer die deutsche Finanzbuchhaltung. "
        "Ordne den folgenden Beleg genau einer dieser Kategorien zu: "
        f"{', '.join(categories)}.\n\n"
        f"Haendler: {merchant or 'unbekannt'}\n"
        f"Betrag: {amount if amount is not None else 'unbekannt'} EUR\n"
        f"Belegtext (Auszug):\n{snippet}\n\n"
        "Antworte ausschliesslich als JSON im Format "
        '{"category": "<eine der genannten Kategorien>"}. Kein weiterer Text.'
    )


def _get_api_key(config) -> str:
    api_key = os.environ.get(config.llm.api_key_env)
    if not api_key:
        raise RuntimeError(f"Umgebungsvariable {config.llm.api_key_env} ist nicht gesetzt.")
    if "..." in api_key:
        raise RuntimeError(
            f"{config.llm.api_key_env} enthaelt noch den Platzhalter aus .env.example "
            "(z.B. 'sk-ant-...') statt eines echten API-Keys. Bitte in .env bzw. im "
            "API-Key-Feld einen echten Key von console.anthropic.com / platform.openai.com eintragen."
        )
    return api_key


def _call_anthropic(prompt: str, config) -> str:
    import anthropic

    api_key = _get_api_key(config)
    client = anthropic.Anthropic(api_key=api_key, timeout=config.llm.timeout_seconds)
    response = client.messages.create(
        model=config.llm.model,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


def _call_openai(prompt: str, config) -> str:
    from openai import OpenAI

    api_key = _get_api_key(config)
    client = OpenAI(api_key=api_key, timeout=config.llm.timeout_seconds)
    response = client.chat.completions.create(
        model=config.llm.model,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def _extract_category_from_response(raw_response: str, categories: list) -> Optional[str]:
    text = raw_response.strip()
    candidate = text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        candidate = str(data.get("category", "")).strip()
    except (ValueError, json.JSONDecodeError):
        pass

    for category in categories:
        if category.lower() == candidate.lower():
            return category
    for category in categories:
        if category.lower() in candidate.lower():
            return category
    return None


def categorize_with_llm(merchant, amount, raw_text, config) -> tuple[Optional[str], Optional[str]]:
    """Gibt (Kategorie, Fehlermeldung) zurueck - genau einer der beiden Werte ist None."""
    prompt = _build_prompt(merchant, amount, raw_text, config.categories)

    last_error = None
    for attempt in range(1, config.llm.max_retries + 1):
        try:
            if config.llm.provider == "anthropic":
                raw_response = _call_anthropic(prompt, config)
            elif config.llm.provider == "openai":
                raw_response = _call_openai(prompt, config)
            else:
                return None, "Kein LLM-Anbieter konfiguriert (llm.provider = 'none')"
            category = _extract_category_from_response(raw_response, config.categories)
            if category:
                return category, None
            last_error = f"Unerwartete Antwort ohne bekannte Kategorie: {raw_response!r}"
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "KI-Kategorisierung fehlgeschlagen (Versuch %s/%s): %s",
                attempt, config.llm.max_retries, exc,
            )
            # Bei falschem/Platzhalter-Key oder falschem Anbieter aendert ein Retry nichts.
            if isinstance(exc, RuntimeError):
                break
            time.sleep(min(2 ** attempt, 10))
    logger.error("KI-Kategorisierung endgueltig fehlgeschlagen: %s", last_error)
    return None, last_error


def categorize(merchant, amount, raw_text, config) -> CategoryResult:
    """Kategorisiert einen Beleg: zuerst Regeln (schnell/kostenlos), dann optional KI."""
    rule_category = categorize_by_rules(merchant, config.rules)
    if rule_category:
        return CategoryResult(category=rule_category, source="regel")

    if config.llm.enabled and config.llm.provider != "none" and config.get_api_key():
        llm_category, error = categorize_with_llm(merchant, amount, raw_text, config)
        if llm_category:
            return CategoryResult(category=llm_category, source="ki")
        return CategoryResult(
            category=FALLBACK_CATEGORY, source="fallback",
            note=f"KI-Kategorisierung fehlgeschlagen: {error}",
        )

    return CategoryResult(
        category=FALLBACK_CATEGORY, source="fallback",
        note="Keine Regel getroffen, KI deaktiviert oder kein API-Key gesetzt",
    )
