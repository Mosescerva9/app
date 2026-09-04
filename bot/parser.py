"""Parse Discord options alerts into structured trades."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class TradeAlert:
    action: Action
    symbol: str
    option_type: OptionType
    strike: float
    expiration: str  # YYYY-MM-DD
    quantity: int | None
    limit_price: float | None
    raw: str
    confidence: str = "high"

    @property
    def contract_key(self) -> str:
        """Stable key for matching entry/exit on the same contract."""
        strike = f"{self.strike:.2f}".rstrip("0").rstrip(".")
        return f"{self.symbol}|{self.expiration}|{strike}|{self.option_type.value}"


# Common alert shapes from options Discord communities.
# Keep patterns ordered: more specific first.
_ACTION = r"(?P<action>BUY|SELL|BOUGHT|SOLD|ENTRY|EXIT|CLOSE|TRIM|ADD|BTO|STC|STO|BTC)"
_SYMBOL = r"(?P<symbol>[A-Z]{1,6})"
_OPT = r"(?P<option_type>CALLS?|PUTS?|C|P)"
_STRIKE = r"(?P<strike>\d+(?:\.\d+)?)"
_PRICE = r"(?:@|at|avg(?:erage)?|price)?\s*\$?(?P<price>\d+(?:\.\d+)?)"
_QTY = r"(?:x|\*|qty|quantity|contracts?)?\s*(?P<qty>\d+)"

# Expiry forms: 3/21, 03/21/26, 2026-03-21, Mar 21, MAR21, 3/21/2026
_EXP_NUMERIC = (
    r"(?P<exp_m>\d{1,2})[/-](?P<exp_d>\d{1,2})(?:[/-](?P<exp_y>\d{2,4}))?"
)
_EXP_ISO = r"(?P<exp_iso>\d{4}-\d{2}-\d{2})"
_MONTHS = (
    "JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|"
    "JANUARY|FEBRUARY|MARCH|APRIL|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER"
)
_EXP_NAMED = rf"(?P<exp_mon>{_MONTHS})\s*(?P<exp_named_d>\d{{1,2}})(?:[,\s]+(?P<exp_named_y>\d{{2,4}}))?"

_EXP = rf"(?:{_EXP_ISO}|{_EXP_NUMERIC}|{_EXP_NAMED})"

PATTERNS: list[re.Pattern[str]] = [
    # BTO AAPL 220C 3/21 @ 1.25 x2
    re.compile(
        rf"(?i)\b{_ACTION}\s+{_SYMBOL}\s+{_STRIKE}\s*{_OPT}\s+{_EXP}(?:\s+{_PRICE})?(?:\s+{_QTY})?",
    ),
    # BUY AAPL 3/21 220 CALL @ 1.25
    re.compile(
        rf"(?i)\b{_ACTION}\s+{_SYMBOL}\s+{_EXP}\s+{_STRIKE}\s*{_OPT}(?:\s+{_PRICE})?(?:\s+{_QTY})?",
    ),
    # AAPL 220 CALL 03/21 BUY @ 1.25
    re.compile(
        rf"(?i)\b{_SYMBOL}\s+{_STRIKE}\s*{_OPT}\s+{_EXP}\s+{_ACTION}(?:\s+{_PRICE})?(?:\s+{_QTY})?",
    ),
    # BUY TO OPEN: TSLA $250 Put exp 2026-07-17 qty 2 @ $8.50
    re.compile(
        rf"(?i)\b{_ACTION}(?:\s+TO\s+OPEN|\s+TO\s+CLOSE)?\s*:?\s*{_SYMBOL}\s+"
        rf"\$?{_STRIKE}\s*{_OPT}\s+(?:exp(?:iry|iration)?\s*)?{_EXP}"
        rf"(?:\s+(?:qty|quantity|x)\s*{_QTY})?(?:\s+{_PRICE})?",
    ),
    # Embed-style: Symbol: NVDA | Strike: 100 | Type: PUT | Exp: 7/17 | Action: BUY | Price: 6
    re.compile(
        rf"(?i)symbol[:\s]+{_SYMBOL}.*?strike[:\s]+\$?{_STRIKE}.*?"
        rf"(?:type|option)[:\s]+{_OPT}.*?(?:exp|expiration|expiry)[:\s]+{_EXP}.*?"
        rf"(?:action|side)[:\s]+{_ACTION}(?:.*?(?:price|avg|@)[:\s]+\$?{_PRICE})?"
        rf"(?:.*?(?:qty|quantity|contracts?)[:\s]+(?P<qty>\d+))?",
        re.DOTALL,
    ),
]

_MONTH_MAP = {
    "JAN": 1,
    "JANUARY": 1,
    "FEB": 2,
    "FEBRUARY": 2,
    "MAR": 3,
    "MARCH": 3,
    "APR": 4,
    "APRIL": 4,
    "MAY": 5,
    "JUN": 6,
    "JUNE": 6,
    "JUL": 7,
    "JULY": 7,
    "AUG": 8,
    "AUGUST": 8,
    "SEP": 9,
    "SEPTEMBER": 9,
    "OCT": 10,
    "OCTOBER": 10,
    "NOV": 11,
    "NOVEMBER": 11,
    "DEC": 12,
    "DECEMBER": 12,
}

_ACTION_MAP = {
    "BUY": Action.BUY,
    "BOUGHT": Action.BUY,
    "ENTRY": Action.BUY,
    "ADD": Action.BUY,
    "BTO": Action.BUY,
    "BTC": Action.BUY,
    "SELL": Action.SELL,
    "SOLD": Action.SELL,
    "EXIT": Action.SELL,
    "CLOSE": Action.SELL,
    "TRIM": Action.SELL,
    "STC": Action.SELL,
    "STO": Action.SELL,
}


def _normalize_option_type(raw: str) -> OptionType:
    u = raw.upper()
    if u.startswith("C"):
        return OptionType.CALL
    if u.startswith("P"):
        return OptionType.PUT
    raise ValueError(f"Unknown option type: {raw}")


def _normalize_action(raw: str) -> Action:
    key = raw.upper()
    if key not in _ACTION_MAP:
        raise ValueError(f"Unknown action: {raw}")
    return _ACTION_MAP[key]


def _year_from_token(token: str | None, month: int, day: int) -> int:
    now = datetime.now()
    if not token:
        # Assume next occurrence of that month/day (including today).
        candidate = now.year
        try:
            if datetime(candidate, month, day).date() < now.date():
                candidate += 1
        except ValueError:
            candidate += 1
        return candidate
    y = int(token)
    if y < 100:
        y += 2000
    return y


def _parse_expiration(groups: dict[str, str | None]) -> str:
    if groups.get("exp_iso"):
        return groups["exp_iso"]

    if groups.get("exp_m") and groups.get("exp_d"):
        month = int(groups["exp_m"])
        day = int(groups["exp_d"])
        year = _year_from_token(groups.get("exp_y"), month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"

    if groups.get("exp_mon") and groups.get("exp_named_d"):
        month = _MONTH_MAP[groups["exp_mon"].upper()]
        day = int(groups["exp_named_d"])
        year = _year_from_token(groups.get("exp_named_y"), month, day)
        return f"{year:04d}-{month:02d}-{day:02d}"

    raise ValueError("Could not parse expiration")


def _clean_text(text: str) -> str:
    # Normalize whitespace and fancy dashes/dollars from Discord embeds.
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("$", "$")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_alert(text: str, default_quantity: int | None = None) -> TradeAlert | None:
    """Return a TradeAlert if the message looks like an options alert."""
    cleaned = _clean_text(text)
    if not cleaned:
        return None

    for pattern in PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        groups = match.groupdict()
        try:
            action = _normalize_action(groups["action"])
            option_type = _normalize_option_type(groups["option_type"])
            expiration = _parse_expiration(groups)
            strike = float(groups["strike"])
            qty_raw = groups.get("qty")
            quantity = int(qty_raw) if qty_raw else default_quantity
            price_raw = groups.get("price")
            limit_price = float(price_raw) if price_raw else None
            return TradeAlert(
                action=action,
                symbol=groups["symbol"].upper(),
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                quantity=quantity,
                limit_price=limit_price,
                raw=cleaned,
            )
        except (KeyError, ValueError, TypeError):
            continue
    return None


def parse_alert_from_parts(parts: Iterable[str], default_quantity: int | None = None) -> TradeAlert | None:
    """Parse from Discord message content + embed fields joined together."""
    joined = "\n".join(p for p in parts if p)
    return parse_alert(joined, default_quantity=default_quantity)
