"""Publish a new Dizflow version so installed copies update themselves.

    1. bump __version__ in dizflow/__init__.py
    2. commit and push
    3. .venv\\Scripts\\python release.py "What's new in this version"

Builds the app + installer, then creates GitHub release v<version> with the installer attached.
Every installed Dizflow checks GitHub Releases and offers the update.
"""
import subprocess
import sys
from pathlib import Path

from dizflow import __version__

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # release notes may contain arrows, emoji…
ROOT = Path(__file__).resolve().parent
texts = [a for a in sys.argv[1:] if not a.startswith("--")]
notes = texts[0] if texts else f"Dizflow {__version__}"
tag = f"v{__version__}"
setup = ROOT / "dist" / "installer" / f"Dizflow-Setup-{__version__}.exe"


def run(*cmd, **kw):
    print(">", " ".join(map(str, cmd)))
    return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip():
    sys.exit("Commit your changes first - the release is built from the committed code.")
if subprocess.run(["gh", "release", "view", tag], cwd=ROOT, capture_output=True).returncode == 0:
    sys.exit(f"Release {tag} already exists - bump __version__ in dizflow/__init__.py first.")

if "--skip-build" not in sys.argv:
    run(sys.executable, "build.py")
if not setup.exists():
    sys.exit(f"Installer not found: {setup}")

run("git", "push")
run("gh", "release", "create", tag, str(setup), "--title", f"Dizflow {__version__}", "--notes", notes)
print(f"\nReleased {tag}. Installed copies will offer the update within a few hours (or via 'Check now').")
