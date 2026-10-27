"""Check available Windows voices and Russian TTS output.

Usage:
    python scripts/tts_check.py
    python scripts/tts_check.py --voice ru --rate 180
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jarvis.config import load_config  # noqa: E402
from jarvis.providers.tts.sapi5_tts import Sapi5TTS, list_voices  # noqa: E402


def main() -> int:
    config = load_config(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default=config.tts.voice)
    parser.add_argument("--rate", type=int, default=config.tts.rate)
    args = parser.parse_args()

    voices = list_voices()
    if not voices:
        print(
            "Не удалось получить голоса Windows SAPI5.\n"
            "Проверьте, что служба Windows Audio запущена и установлен речевой пакет."
        )
        return 1

    print("Доступные голоса:\n")
    russian: list[tuple[str, str]] = []
    for description, token_id in voices:
        is_ru = "ru" in f"{description} {token_id}".lower()
        if is_ru:
            russian.append((description, token_id))
        print(f"  {'[RU]' if is_ru else '    '} {description}\n       {token_id}")

    if not russian:
        print(
            "\nРусский голос не найден.\n"
            "Параметры -> Время и язык -> Язык и регион -> Русский -> "
            "дополнительные параметры -> Речевые пакеты."
        )
        return 1

    chosen = russian[0]
    for candidate in russian:
        if args.voice.lower() in f"{candidate[0]} {candidate[1]}".lower():
            chosen = candidate
            break

    config.tts.voice = chosen[0]
    config.tts.rate = args.rate
    tts = Sapi5TTS(config.tts)
    if not tts.available:
        print("SAPI5 TTS не удалось инициализировать.")
        return 1

    print(f"\nГолос: {chosen[0]}")
    print('Фраза: "Привет! Я Джарвис, твой голосовой ассистент."\n')
    tts.speak("Привет! Я Джарвис, твой голосовой ассистент.")
    tts.wait()
    tts.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
