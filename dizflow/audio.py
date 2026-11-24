"""Microphone capture, local Whisper transcription and UI sounds."""
import logging
import os
import threading
import wave
import winsound

import numpy as np
import sounddevice as sd

from .paths import SOUNDS_DIR

log = logging.getLogger("dizflow")
RATE = 16000


NO_MIC_HELP = ("No microphone found. Connect your earbuds or headset, or turn on your microphone in "
               "Windows Settings → System → Sound → Input.")
# Inputs that record the PC's own sound output, not the user's voice.
_NOT_A_MIC = ("stereo mix", "what u hear", "loopback", "wave out", "sound mapper")
# Prefer the shared-mode Windows audio stack; WDM-KS talks to drivers directly and is often unusable.
_API_ORDER = ("Windows WASAPI", "MME", "Windows DirectSound")


class NoMicrophoneError(RuntimeError):
    pass


_open_streams = 0  # rescanning devices would break an open recording


def _refresh():
    """Re-scan audio devices so earbuds plugged in after Dizflow started are found."""
    if _open_streams:
        return
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def _candidates():
    """Usable microphones as (index, device info, host API name), best first."""
    apis = [h["name"] for h in sd.query_hostapis()]
    out = []
    for i, d in enumerate(sd.query_devices()):
        api = apis[d["hostapi"]]
        if d["max_input_channels"] <= 0 or api not in _API_ORDER:
            continue
        if any(bad in d["name"].lower() for bad in _NOT_A_MIC):
            continue
        out.append((i, d, api))
    return sorted(out, key=lambda c: _API_ORDER.index(c[2]))


def input_devices() -> list[str]:
    """Names of usable microphones for the Settings list (each microphone once)."""
    try:
        names = []
        for _, d, _ in _candidates():
            short = d["name"][:31]  # MME truncates names to 31 characters; don't list a mic twice
            if not any(n[:31] == short for n in names):
                names.append(d["name"])
        return names
    except Exception:
        return []


def pick_device(name: str = ""):
    """Index of the microphone to use: the chosen one, else Windows' default, else the first real mic."""
    cands = _candidates()
    if name:
        for i, d, _ in cands:
            if d["name"] == name or d["name"][:31] == name[:31]:
                return i
    default = sd.default.device[0]
    if default is not None and default >= 0 and any(i == default for i, _, _ in cands):
        return default
    if cands:
        return cands[0][0]
    raise NoMicrophoneError(NO_MIC_HELP)


def mic_status() -> tuple[bool, str]:
    """(ok, text) describing the microphone Dizflow will use."""
    try:
        _refresh()
        i = pick_device("")
        return True, sd.query_devices(i)["name"]
    except NoMicrophoneError:
        return False, NO_MIC_HELP
    except Exception as e:
        return False, f"Microphone problem: {e}"


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.level = 0.0
        self.blocks = 0
        self.device_name = ""

    def _cb(self, indata, frames, t, status):
        mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)  # mix stereo/array mics down
        self._frames.append(mono.copy())
        self.blocks += 1
        self.level = float(np.sqrt(np.mean(mono ** 2)))

    def _open(self, dev, info):
        """Open the device with the first sample rate / channel count it accepts."""
        native = int(info["default_samplerate"])
        last = None
        for rate in dict.fromkeys((RATE, native)):
            for ch in dict.fromkeys((1, min(2, info["max_input_channels"]), info["max_input_channels"])):
                try:
                    stream = sd.InputStream(device=dev, samplerate=rate, channels=ch, dtype="float32", callback=self._cb)
                    self._rate = rate
                    return stream
                except Exception as e:
                    last = e
        raise last

    def start(self, device_name: str = ""):
        self._frames = []
        self.blocks = 0
        try:
            dev = pick_device(device_name)
        except NoMicrophoneError:
            _refresh()  # maybe earbuds were connected since the last scan
            dev = pick_device(device_name)
        info = sd.query_devices(dev)
        self.device_name = info["name"]
        try:
            self._stream = self._open(dev, info)
        except Exception:
            _refresh()
            dev = pick_device(device_name)
            info = sd.query_devices(dev)
            self.device_name = info["name"]
            self._stream = self._open(dev, info)
        global _open_streams
        _open_streams += 1
        self._stream.start()

    def stop(self) -> np.ndarray:
        global _open_streams
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            _open_streams = max(0, _open_streams - 1)
        self.level = 0.0
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._frames)
        if self._rate != RATE:
            n = int(len(audio) * RATE / self._rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        return audio


MODEL_SIZES_MB = {"large-v3-turbo": 1550, "large-v3": 2950, "medium": 1460, "small": 465, "small.en": 465,
                  "base": 140, "base.en": 140}

HALLUCINATIONS = {"thank you", "thanks for watching", "you", "bye", "thank you for watching", "subtitles by"}


class Transcriber:
    def __init__(self, settings, on_status=lambda s: None):
        self.s = settings
        self.on_status = on_status
        self.model = None
        self.device = ""
        self.ready = threading.Event()
        self.downloading = ""  # progress text while the model is being downloaded
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
                        log.info("speech model %s not on this PC (%s) - downloading", name, e)
                        done = threading.Event()
                        threading.Thread(target=self._watch_download, args=(name, done), daemon=True).start()
                        try:
                            m = WhisperModel(name, device=device, compute_type=compute)
                        finally:
                            done.set()
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

    def _watch_download(self, name, done):
        """Report download progress by watching the Hugging Face cache folder grow."""
        from pathlib import Path
        cache = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache" / "huggingface" / "hub")
        total_mb = MODEL_SIZES_MB.get(name)
        while not done.wait(1.5):
            got = sum(f.stat().st_size for d in cache.glob(f"models--*faster-whisper-{name}") for f in
                      (d / "blobs").glob("*") if f.is_file()) // (1 << 20) if cache.exists() else 0
            pct = f" {min(99, got * 100 // total_mb)}%" if total_mb else ""
            self.downloading = f"Downloading speech model{pct} ({got:,} MB{f' of {total_mb:,} MB' if total_mb else ''}) - first time only"
            self.on_status(self.downloading + "…")
        self.downloading = ""

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
