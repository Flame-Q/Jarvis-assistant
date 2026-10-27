"""Voice loop: wake word or push-to-talk -> record -> STT -> assistant -> TTS."""

from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np
from loguru import logger

from jarvis.audio.capture import BLOCK_MS, MicrophoneStream
from jarvis.audio.playback import beep
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.audio.wakeword import WakeWordDetector
from jarvis.config import AppConfig
from jarvis.core.assistant import AssistantService
from jarvis.core.errors import ProviderError
from jarvis.core.events import EventBus
from jarvis.core.fsm import State
from jarvis.providers.stt.base import STTProvider
from jarvis.providers.tts.base import TTSProvider
from jarvis.ui.console import console_ui
from jarvis.ui.hotkeys import HotkeyManager


class VoiceLoop:
    """Runs in daemon threads and never blocks the console or Qt UI.

    Two activation paths share one busy lock:

    * wake word / hotkey: automatic capture until VAD silence;
    * push-to-talk button: capture until the user presses the button again.
    """

    def __init__(
        self,
        *,
        config: AppConfig,
        assistant: AssistantService,
        stt: STTProvider,
        tts: TTSProvider,
        bus: EventBus,
        hotkey: str | None = None,
    ) -> None:
        self._config = config
        self._assistant = assistant
        self._stt = stt
        self._tts = tts
        self._bus = bus
        self._mic = MicrophoneStream()
        self._vad = VoiceActivityDetector()
        self._wakeword = WakeWordDetector(
            model_name=config.assistant.wake_word,
            threshold=config.assistant.sensitivity,
        )
        self._hotkey = hotkey or config.assistant.hotkey
        self._manual_hotkey = config.assistant.manual_hotkey
        self._hotkeys = HotkeyManager()
        self._manual_hotkeys = HotkeyManager()
        self._thread: threading.Thread | None = None
        self._running = False
        self._busy = threading.Lock()
        self._manual_lock = threading.Lock()
        self._manual_stop = threading.Event()
        self._manual_recording = threading.Event()
        self._wakeword_enabled = config.assistant.wake_word_enabled
        self._wakeword_ok = False
        self._wakeword_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def recording(self) -> bool:
        """True while the push-to-talk button is capturing audio."""

        return self._manual_recording.is_set()

    @property
    def busy(self) -> bool:
        """True while any activation is recording or being processed."""

        return self._busy.locked()

    @property
    def wake_word_enabled(self) -> bool:
        return self._wakeword_enabled

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._mic.open()
        except Exception as exc:
            logger.error("Microphone unavailable, voice mode disabled: {}", exc)
            return False

        self._running = True
        self._thread = threading.Thread(target=self._run, name="voice-loop", daemon=True)
        self._thread.start()

        self._hotkeys.register(self._hotkey, self.trigger)
        if self._manual_hotkey:
            self._manual_hotkeys.register(self._manual_hotkey, self._on_manual_hotkey)
        threading.Thread(target=self._warmup, name="voice-warmup", daemon=True).start()
        return True

    def _on_manual_hotkey(self) -> None:
        self.toggle_manual()

    def _warmup(self) -> None:
        try:
            self._stt.warmup()
        except Exception as exc:
            logger.warning("STT warmup failed: {}", exc)
        self._warmup_wakeword()

    def _warmup_wakeword(self) -> None:
        if not self._wakeword_enabled:
            logger.info(
                "Wake word disabled; use the microphone button or {}",
                self._manual_hotkey or self._hotkey,
            )
            return
        if self._wakeword_ok:
            return
        with self._wakeword_lock:
            if not self._wakeword_enabled or self._wakeword_ok:
                return
            try:
                self._wakeword.warmup()
                self._wakeword_ok = True
                logger.info("Wake word ready (threshold {:.2f})", self._wakeword.threshold)
            except Exception as exc:
                logger.warning("Wake word unavailable, use hotkey {}: {}", self._hotkey, exc)

    def trigger(self) -> None:
        """Activate automatic VAD recording from the global hotkey."""

        if not self._running or self._busy.locked():
            return
        threading.Thread(target=self._activate, name="voice-trigger", daemon=True).start()

    def toggle_manual(self) -> bool:
        """Start or stop push-to-talk recording (button and global hotkey)."""

        with self._manual_lock:
            if self._manual_recording.is_set():
                return self.stop_manual_recording()
            return self.start_manual_recording()

    def start_manual_recording(self) -> bool:
        """Begin push-to-talk capture; processing happens after ``stop_manual_recording``."""

        if not self._running:
            logger.warning("Cannot start manual recording: voice loop is not running")
            return False
        if self._tts.is_speaking:
            logger.info("Cannot start manual recording: TTS is speaking")
            return False
        if not self._busy.acquire(blocking=False):
            logger.info("Cannot start manual recording: voice loop is busy")
            return False

        self._manual_stop.clear()
        self._manual_recording.set()
        threading.Thread(target=self._manual_worker, name="voice-manual", daemon=True).start()
        console_ui.listening()
        logger.info("Manual recording started")
        return True

    def stop_manual_recording(self) -> bool:
        """Ask the capture loop to stop; STT and the answer follow immediately."""

        if not self._manual_recording.is_set():
            return False
        self._manual_stop.set()
        logger.info("Manual recording stop requested")
        return True

    def _manual_worker(self) -> None:
        try:
            self._handle_manual_activation()
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("Manual voice activation failed")
            self._assistant.fsm.reset()
        finally:
            self._manual_recording.clear()
            self._manual_stop.clear()
            self._busy.release()

    def _run(self) -> None:
        stale_audio = False
        while self._running:
            # Never consume frames that the active recording worker needs.
            if self._tts.is_speaking:
                if not self._busy.locked():
                    self._mic.drain()
                stale_audio = True
                time.sleep(0.05)
                continue
            if self._busy.locked():
                stale_audio = True
                time.sleep(0.02)
                continue
            if stale_audio:
                self._mic.drain()
                stale_audio = False
            if not self._wakeword_enabled or not self._wakeword_ok:
                time.sleep(0.02)
                continue
            frame = self._mic.read(timeout=0.2)
            if not self._running:
                break
            if frame is None:
                continue
            try:
                score = self._wakeword.process(frame)
            except Exception as exc:  # pragma: no cover
                logger.warning("Wake word failed, switching to hotkey only: {}", exc)
                self._wakeword_ok = False
                continue
            if score >= self._wakeword.threshold:
                logger.info("Wake word detected (score {:.2f})", score)
                self._wakeword.reset()
                self.trigger()

    def _activate(self) -> None:
        if not self._busy.acquire(blocking=False):
            return
        try:
            self._handle_activation()
        except Exception:  # pragma: no cover - keep the loop alive
            logger.exception("Voice activation failed")
            self._assistant.fsm.reset()
        finally:
            self._busy.release()

    def _handle_activation(self) -> None:
        if self._tts.is_speaking:
            return
        started = time.perf_counter()
        self._mic.drain()
        fsm = self._assistant.fsm
        if fsm.state != State.IDLE:
            fsm.force(State.IDLE)
        if not fsm.transition(State.ACTIVATED):
            return
        beep(880, 70)
        fsm.transition(State.LISTENING)
        console_ui.listening()

        audio = self._record_utterance()
        if not self._running or audio.size == 0:
            fsm.transition(State.IDLE)
            return

        self._process_audio(audio, started)

    def _handle_manual_activation(self) -> None:
        started = time.perf_counter()
        self._mic.drain()
        fsm = self._assistant.fsm
        if fsm.state != State.IDLE:
            fsm.force(State.IDLE)
        if not fsm.transition(State.ACTIVATED):
            return
        beep(880, 70)
        fsm.transition(State.LISTENING)

        audio = self._record_manual()
        self._manual_recording.clear()
        if not self._running:
            fsm.force(State.IDLE)
            return
        if audio.size == 0:
            self._tts.speak("Не расслышал, повторите пожалуйста.")
            fsm.transition(State.IDLE)
            return

        self._process_audio(audio, started)

    def _process_audio(self, audio: np.ndarray, started: float) -> None:
        fsm = self._assistant.fsm
        if not fsm.transition(State.TRANSCRIBING):
            fsm.force(State.TRANSCRIBING)
        try:
            with console_ui.thinking():
                text = self._stt.transcribe(audio, 16000)
        except ProviderError as exc:
            logger.error("STT error: {}", exc)
            self._tts.speak(str(exc))
            fsm.force(State.IDLE)
            return

        logger.info("Recognized: {!r}", text)
        if not text.strip():
            self._tts.speak("Не расслышал, повторите пожалуйста.")
            fsm.force(State.IDLE)
            return

        self._bus.publish("recognized", text=text)
        self._assistant.handle_text(text)
        logger.info("Voice command handled in {:.2f}s", time.perf_counter() - started)

    def _record_utterance(self) -> np.ndarray:
        block_ms = BLOCK_MS
        silence_limit = max(1, self._config.stt.vad_silence_ms // block_ms)
        max_frames = int(self._config.stt.max_utterance_s * 1000 / block_ms)
        speech_deadline = time.monotonic() + 6.0
        hard_deadline = time.monotonic() + self._config.stt.max_utterance_s + 2.0

        pre_roll: deque[bytes] = deque(maxlen=max(1, 300 // block_ms))
        frames: list[bytes] = []
        started = False
        silence = 0

        while len(frames) < max_frames:
            if time.monotonic() > hard_deadline:
                logger.warning("Utterance capture reached hard deadline")
                break
            frame = self._mic.read(timeout=0.2)
            if frame is None:
                if not started and time.monotonic() > speech_deadline:
                    break
                continue

            if not started:
                pre_roll.append(frame)
                if self._vad.is_speech(frame):
                    started = True
                    frames.extend(pre_roll)
                    pre_roll.clear()
                    silence = 0
                elif time.monotonic() > speech_deadline:
                    break
                continue

            frames.append(frame)
            if self._vad.is_speech(frame):
                silence = 0
            else:
                silence += 1
                if silence >= silence_limit:
                    break

        if not frames:
            return np.zeros(0, dtype=np.int16)
        return np.frombuffer(b"".join(frames), dtype=np.int16).copy()

    def _record_manual(self) -> np.ndarray:
        """Capture until the user presses stop, with a safety time limit."""

        max_frames = int(self._config.stt.manual_max_utterance_s * 1000 / BLOCK_MS)
        deadline = time.monotonic() + self._config.stt.manual_max_utterance_s
        frames: list[bytes] = []
        while (
            len(frames) < max_frames
            and self._running
            and not self._manual_stop.is_set()
        ):
            if time.monotonic() >= deadline:
                logger.warning("Manual recording reached the time limit")
                break
            frame = self._mic.read(timeout=0.2)
            if frame is not None:
                frames.append(frame)

        if not frames:
            return np.zeros(0, dtype=np.int16)
        return np.frombuffer(b"".join(frames), dtype=np.int16).copy()

    def set_threshold(self, value: float) -> None:
        self._wakeword.threshold = value
        logger.info("Wake word threshold set to {:.2f}", self._wakeword.threshold)

    def set_hotkey(self, hotkey: str) -> None:
        if not hotkey or hotkey == self._hotkey:
            return
        self._hotkey = hotkey
        if self._running:
            self._hotkeys.register(hotkey, self.trigger)

    def set_manual_hotkey(self, hotkey: str) -> None:
        if hotkey == self._manual_hotkey:
            return
        self._manual_hotkey = hotkey
        if not self._running:
            return
        if hotkey:
            self._manual_hotkeys.register(hotkey, self._on_manual_hotkey)
        else:
            self._manual_hotkeys.unregister()

    def set_wake_word_enabled(self, enabled: bool) -> None:
        self._wakeword_enabled = bool(enabled)
        logger.info("Wake word {}", "enabled" if self._wakeword_enabled else "disabled")
        if self._wakeword_enabled and not self._wakeword_ok:
            threading.Thread(
                target=self._warmup_wakeword,
                name="wakeword-warmup",
                daemon=True,
            ).start()

    def stop(self) -> None:
        self._running = False
        self._manual_stop.set()
        self._hotkeys.unregister()
        self._manual_hotkeys.unregister()
        self._mic.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
