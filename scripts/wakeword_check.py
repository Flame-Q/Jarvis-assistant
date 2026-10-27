"""Interactive wake word check: verifies microphone and 'hey jarvis' detection.

Usage:
    python scripts/wakeword_check.py
    python scripts/wakeword_check.py --device 1 --threshold 0.4
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jarvis.audio.capture import MicrophoneStream  # noqa: E402
from jarvis.audio.wakeword import WakeWordDetector  # noqa: E402
from jarvis.config import load_config  # noqa: E402


def list_devices() -> None:
    print("Доступные устройства ввода:\n")
    for index, device in enumerate(MicrophoneStream.devices()):
        marker = "  <-- по умолчанию" if device.get("max_input_channels", 0) > 0 else ""
        print(
            f"  [{index}] {device['name']} "
            f"(входов: {device['max_input_channels']}, {int(device['default_samplerate'])} Hz){marker}"
        )
    print()


def main() -> int:
    config = load_config(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=None, help="input device index")
    parser.add_argument("--threshold", type=float, default=config.assistant.sensitivity)
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()

    list_devices()
    detector = WakeWordDetector(
        model_name=config.assistant.wake_word, threshold=args.threshold
    )
    print(f"Модель: {config.assistant.wake_word}, порог: {args.threshold}")
    print('Скажите "Hey Jarvis" (лучше по-английски). Ctrl+C — выход.\n')

    peak = 0.0
    detected_at = 0.0
    started = time.time()
    try:
        with MicrophoneStream(device=args.device) as mic:
            print(f"Микрофон: {mic.describe()}\n")
            while time.time() - started < args.seconds:
                frame = mic.read(timeout=0.3)
                if frame is None:
                    continue
                score = detector.process(frame)
                peak = max(peak, score)
                if score >= args.threshold:
                    detected_at = time.time()
                    print(f"\n[OK] Джарвис услышан! score={score:.3f}")
                    detector.reset()
                    peak = 0.0
                else:
                    print(
                        f"\rscore: {score:.3f}   пик: {peak:.3f}   "
                        f"порог: {args.threshold:.2f}   ",
                        end="",
                        flush=True,
                    )
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
    except Exception as exc:
        print(f"\nОшибка: {exc}")
        return 1

    if detected_at == 0.0:
        print("\n\nНи одного срабатывания. Проверьте микрофон, порог или произношение.")
    print(f"Максимальный score: {peak:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
