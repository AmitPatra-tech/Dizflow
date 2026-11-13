"""Build dist/Dizflow/Dizflow.exe with PyInstaller.  Run:  .venv\\Scripts\\python build.py"""
import glob
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
SITE = Path(sys.prefix) / "Lib" / "site-packages"

# App icon (.ico) drawn by the same code the app uses.
from PySide6.QtWidgets import QApplication
app = QApplication([])
from dizflow.ui.theme import app_icon
icon_png = ROOT / "build" / "icon.png"
icon_png.parent.mkdir(exist_ok=True)
app_icon(256).pixmap(256, 256).save(str(icon_png))
from PIL import Image
icon_ico = ROOT / "build" / "dizflow.ico"
Image.open(icon_png).save(icon_ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

args = [
    str(ROOT / "main.py"),
    "--name", "Dizflow",
    "--noconfirm",
    "--windowed",
    "--icon", str(icon_ico),
    "--collect-data", "faster_whisper",
    "--collect-binaries", "ctranslate2",
    "--collect-submodules", "google.genai",
    "--hidden-import", "anthropic",
    "--exclude-module", "torch",
    "--exclude-module", "tkinter",
]
# GPU libraries (cuBLAS / cuDNN) so Whisper can use the NVIDIA card.
for dll in glob.glob(str(SITE / "nvidia" / "*" / "bin" / "*.dll")):
    rel = Path(dll).parent.relative_to(SITE)
    args += ["--add-binary", f"{dll}{os.pathsep}{rel.as_posix()}"]

PyInstaller.__main__.run(args)
print("\nBuilt:", ROOT / "dist" / "Dizflow" / "Dizflow.exe")

# Installer: dist/installer/Dizflow-Setup-<version>.exe (needs Inno Setup 6).
import subprocess
from dizflow import __version__
iscc = next((p for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                         Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")) if p.exists()), None)
if iscc:
    subprocess.run([str(iscc), f"/DAppVersion={__version__}", str(ROOT / "installer.iss")], cwd=ROOT, check=True)
    print("Installer:", ROOT / "dist" / "installer" / f"Dizflow-Setup-{__version__}.exe")
else:
    print("Inno Setup not found - skipped Setup.exe (install it with: winget install JRSoftware.InnoSetup)")
