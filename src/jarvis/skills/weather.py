"""Weather through Open-Meteo (no API key required)."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from pydantic import BaseModel

from jarvis.config import AppConfig
from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES: dict[int, str] = {
    0: "ясно",
    1: "в основном ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "слабая морось",
    53: "морось",
    55: "сильная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "сильный ледяной дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    77: "снежная крупа",
    80: "небольшие ливни",
    81: "ливни",
    82: "сильные ливни",
    85: "снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}

_STOPWORDS = {
    "какая",
    "какой",
    "погода",
    "погоду",
    "сейчас",
    "сегодня",
    "завтра",
    "будет",
    "ли",
    "ожидается",
    "можно",
    "узнать",
    "на",
    "улице",
    "скажи",
    "подскажи",
    "мне",
    "градусов",
    "температура",
    "дождь",
    "снег",
    "ветер",
    "гроза",
    "облачно",
    "ясно",
    "солнце",
}

_TIME_WORDS = {"завтра", "сегодня", "сейчас", "утром", "днем", "вечером", "ночью"}

_CITY_ALIASES = {
    "мск": "Москва",
    "питер": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "екб": "Екатеринбург",
    "нью йорк": "Нью-Йорк",
}

_ENDINGS = (
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ой",
    "ей",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ий",
    "ем",
    "ом",
    "ах",
    "ях",
    "ую",
    "юю",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "и",
    "ы",
    "о",
    "ь",
)


def _stem_word(word: str) -> str:
    for ending in _ENDINGS:
        if len(word) > len(ending) + 2 and word.endswith(ending):
            return word[: -len(ending)]
    return word


def _stems(text: str) -> tuple[str, ...]:
    return tuple(_stem_word(word) for word in normalize_text(text).split())


def city_matches(query: str, candidate: str) -> bool:
    """Compare Russian city names ignoring common case endings."""

    left = _stems(query)
    right = _stems(candidate)
    if not left or not right:
        return False
    return left == right


def _city_variants(city: str) -> list[str]:
    """Build likely nominative spellings for an inflected city name."""

    variants = [city]
    stem = " ".join(_stems(city))
    for suffix in ("", "а", "я", "ь", "й"):
        candidate = f"{stem}{suffix}".strip()
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _plural_ru(value: int, one: str, few: str, many: str) -> str:
    """Pick the Russian noun form for a number (1 градус, 2 градуса, 5 градусов)."""

    absolute = abs(value) % 100
    if 11 <= absolute <= 14:
        return many
    last = absolute % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


class WeatherArgs(BaseModel):
    city: str = ""


class WeatherSkill(BaseSkill):
    name = "weather"
    description = "Сообщить текущую погоду в городе."
    examples = ["какая погода в Москве", "погода на улице"]
    triggers = ["погода", "погоду", "температура на улице", "дождь"]
    args_model: type[BaseModel] = WeatherArgs

    def __init__(self, config: AppConfig, timeout: float = 6.0) -> None:
        self._config = config
        self._timeout = timeout
        self._cache: dict[str, tuple[float, str]] = {}

    def extract_args(self, text: str) -> WeatherArgs:
        normalized = normalize_text(text)
        match = re.search(r"\bв\s+([а-яa-z\- ]+)$", normalized)
        if match:
            city = match.group(1).strip()
        else:
            words = [word for word in normalized.split() if word not in _STOPWORDS]
            city = " ".join(words).strip()
        city = " ".join(
            word
            for word in city.split()
            if word not in _STOPWORDS and word not in _TIME_WORDS
        )
        for alias, target in _CITY_ALIASES.items():
            if city == alias or city_matches(city, alias):
                city = target
                break

        default_city = self._config.weather.default_city
        if city and city_matches(city, default_city):
            city = default_city
        return WeatherArgs(city=city or default_city)

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, WeatherArgs)
        city = args.city or self._config.weather.default_city
        cached = self._cache.get(city.lower())
        if cached and time.time() - cached[0] < self._config.weather.cache_ttl_s:
            return SkillResult.success(cached[1])

        try:
            text = self._fetch(city)
        except httpx.HTTPError:
            return SkillResult.failure("Нет связи с интернетом, погоду узнать не получилось.")
        except ValueError as exc:
            return SkillResult.failure(str(exc))

        self._cache[city.lower()] = (time.time(), text)
        return SkillResult.success(text)

    def _fetch(self, city: str) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            place = self._geocode(client, city)
            latitude = place["latitude"]
            longitude = place["longitude"]
            label = place.get("name", city)

            forecast = client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            forecast.raise_for_status()
            current = forecast.json().get("current", {})

        temperature = round(float(current.get("temperature_2m", 0)))
        feels = round(float(current.get("apparent_temperature", temperature)))
        wind = round(float(current.get("wind_speed_10m", 0)))
        description = WEATHER_CODES.get(int(current.get("weather_code", -1)), "без осадков")

        sign = "плюс" if temperature >= 0 else "минус"
        degrees = _plural_ru(temperature, "градус", "градуса", "градусов")
        wind_word = _plural_ru(wind, "метр", "метра", "метров")
        text = (
            f"В городе {label} сейчас {sign} {abs(temperature)} {degrees}, {description}, "
            f"ветер {wind} {wind_word} в секунду."
        )
        if abs(feels - temperature) >= 2:
            text += f" Ощущается как {feels}."
        return text

    def _geocode(self, client: httpx.Client, city: str) -> dict[str, Any]:
        """Resolve a city, retrying likely nominative forms for Russian cases."""

        for query in _city_variants(city):
            geo = client.get(
                GEO_URL,
                params={"name": query, "count": 5, "language": "ru", "format": "json"},
            )
            geo.raise_for_status()
            results = geo.json().get("results") or []
            matches = [item for item in results if city_matches(city, str(item.get("name", "")))]
            if matches:
                return max(matches, key=lambda item: int(item.get("population") or 0))

        raise ValueError(f"Не нашёл город {city}.")
