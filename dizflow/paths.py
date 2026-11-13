"""Where Dizflow keeps its data, and how it finds bundled files (works from source and from the .exe)."""
import glob
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Dizflow"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "dizflow.db"
SOUNDS_DIR = DATA_DIR / "sounds"
LOG_PATH = DATA_DIR / "dizflow.log"


def register_cuda_dlls():
    """Make pip-installed cuBLAS / cuDNN DLLs visible to ctranslate2 (GPU Whisper)."""
    roots = [BUNDLE_DIR, Path(sys.prefix) / "Lib" / "site-packages"]
    for root in roots:
        for d in glob.glob(str(root / "nvidia" / "*" / "bin")):
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
