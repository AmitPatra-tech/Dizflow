"""Microphone capture, local Whisper transcription and UI sounds."""
import logging
import threading
import wave
import winsound

import numpy as np
import sounddevice as sd

from .paths import SOUNDS_DIR

log = logging.getLogger("dizflow")
RATE = 16000


def input_devices() -> list[str]:
    """Names of usable microphones (default host API only, so names aren't repeated per driver)."""
    try:
        default_api = sd.default.hostapi if hasattr(sd.default, "hostapi") else 0
        names = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["hostapi"] == default_api and d["name"] not in names:
                names.append(d["name"])
        return names
    except Exception:
        return []


def _device_index(name: str):
    if not name:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0:
            return i
    return None


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.level = 0.0

    def _cb(self, indata, frames, t, status):
        self._frames.append(indata[:, 0].copy())
        self.level = float(np.sqrt(np.mean(indata ** 2)))

    def start(self, device_name: str = ""):
        self._frames = []
        dev = _device_index(device_name)
        info = sd.query_devices(dev if dev is not None else sd.default.device[0], "input")
        self._native = int(info["default_samplerate"])
        # Record at 16 kHz when the device allows it, otherwise at its native rate and resample.
        try:
            sd.check_input_settings(device=dev, samplerate=RATE, channels=1)
            self._rate = RATE
        except Exception:
            self._rate = self._native
        self._stream = sd.InputStream(device=dev, samplerate=self._rate, channels=1, dtype="float32", callback=self._cb)
        self._stream.start()

    def stop(self) -> np.ndarray:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.level = 0.0
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames)
        if self._rate != RATE:
            n = int(len(audio) * RATE / self._rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        return audio


HALLUCINATIONS = {"thank you", "thanks for watching", "you", "bye", "thank you for watching", "subtitles by"}


class Transcriber:
    def __init__(self, settings, on_status=lambda s: None):
        self.s = settings
        self.on_status = on_status
        self.model = None
        self.device = ""
        self.ready = threading.Event()
        self._lock = threading.Lock()
        self.load()

    def load(self):
        self.ready.clear()
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        with self._lock:
            from faster_whisper import WhisperModel
            name = self.s["whisper_model"]
            self.on_status(f"Loading speech model ({name})…")
            attempts = {"auto": [("cuda", "float16"), ("cpu", "int8")],
                        "cuda": [("cuda", "float16")], "cpu": [("cpu", "int8")]}[self.s["device"]]
            self.model = None
            for device, compute in attempts:
                try:
                    try:  # use the cached copy without touching the network; download only if missing
                        m = WhisperModel(name, device=device, compute_type=compute, local_files_only=True)
                    except Exception as e:
                        if "cuda" in str(e).lower() or "cublas" in str(e).lower() or "cudnn" in str(e).lower():
                            raise
                        self.on_status(f"Downloading speech model ({name}) - first time only…")
                        m = WhisperModel(name, device=device, compute_type=compute)
                    list(m.transcribe(np.zeros(RATE, dtype=np.float32))[0])  # warm-up, surfaces CUDA problems
                    self.model, self.device = m, device
                    break
                except Exception as e:
                    log.warning("Whisper on %s unavailable: %s", device, e)
            if self.model:
                self.on_status(f"Ready · {name} on {'GPU' if self.device == 'cuda' else 'CPU'}")
            else:
                self.on_status("Speech model failed to load - check Settings")
            self.ready.set()

    def transcribe(self, audio: np.ndarray, terms: list[str]) -> str:
        self.ready.wait()
        if self.model is None:
            raise RuntimeError("Speech model is not loaded")
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak < 0.01:
            return ""
        audio = audio * min(0.9 / peak, 20.0)
        segments, _ = self.model.transcribe(
            audio, language=self.s["language"] or None, beam_size=5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False, initial_prompt=", ".join(terms) or None)
        text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < 0.6).strip()
        if text.lower().strip(" .!") in HALLUCINATIONS and len(audio) < RATE * 2:
            return ""
        return text


# ------------------------------------------------------------------ sounds
def _tone(path, freqs, dur=0.07, vol=0.25):
    t = np.linspace(0, dur, int(22050 * dur), endpoint=False)
    sig = np.concatenate([np.sin(2 * np.pi * f * t) * np.hanning(len(t)) for f in freqs]) * vol
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())


SOUNDS = {"start": [660, 880], "stop": [880, 660], "error": [300, 220], "done": [990]}


def play(name: str):
    SOUNDS_DIR.mkdir(exist_ok=True)
    path = SOUNDS_DIR / f"{name}.wav"
    if not path.exists():
        _tone(path, SOUNDS[name])
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
