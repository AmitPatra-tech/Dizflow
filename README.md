# Dizflow

Voice-to-text for Windows. Hold **Ctrl + Win** in any app, speak, let go, and clean, ready-to-send text appears at your cursor.

## Features

- **Dictation everywhere:** works in email, chat, docs, browsers and code editors. Speech is recognised **on this PC** with Whisper large-v3-turbo on your NVIDIA GPU. Your audio never leaves the computer.
- **AI writing (Gemini or Claude):** removes "um"s and false starts, applies corrections ("at 3, no wait, at 4" → "at 4"), adds punctuation, and turns "new line" and spoken lists into formatting.
- **App-aware style:** casual in Slack and WhatsApp, formal in Outlook and Word, exact in VS Code and the terminal. You choose the tone per app type on the **Style** page.
- **Command mode (Alt + Win):** select text and say "make this friendlier" or "translate to Hindi". With nothing selected, it writes new text from what you say.
- **Dictionary:** names and jargon that should always be spelled your way.
- **Snippets:** say "my calendar link" and get the full URL.
- **History and stats:** search everything you've said, copy it again, and see words dictated, speaking speed, time saved and your streak.
- **Desktop app:** tray icon, floating recording pill, sounds, start with Windows, first-run setup, microphone picker and level test.

Esc cancels a recording. In Settings you can switch to *press to start / press to stop* and change either shortcut.

## Download

Get **Dizflow-Setup-x.y.z.exe** from the [latest release](https://github.com/AmitPatra-tech/Dizflow/releases/latest) and run it. No admin rights are needed.

- **Windows SmartScreen:** the installer isn't code-signed yet, so Windows may show "Windows protected your PC". Click **More info → Run anyway**.
- **AI cleanup:** needs a free Gemini API key from [Google AI Studio](https://aistudio.google.com). Paste it in the setup wizard or in Settings.
- **Hardware:** an NVIDIA GPU makes transcription near-instant. Without one, Dizflow runs on the CPU. In that case pick the *Small* speech model in Settings.

**Updates are automatic.** Dizflow checks GitHub every few hours, shows a banner when a new version is out, and installs it in one click. Your settings, history and dictionary are kept. You can also go to *Settings → Updates → Check now*.

Settings, history and the dictionary are stored in `%APPDATA%\Dizflow`.

## Develop

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Build the app and installer with `.venv\Scripts\python build.py`. This needs Inno Setup 6 (`winget install JRSoftware.InnoSetup`).

## Publish an update

1. Bump `__version__` in `dizflow/__init__.py`, then commit.
2. Run `.venv\Scripts\python release.py "What's new"`.

The script builds everything, pushes the code, and creates GitHub release `v<version>` with the installer attached. Every installed copy then offers the update.

## Code layout

| File | What it does |
|---|---|
| `main.py` | starts the app (only one copy runs at a time), plus the tray and first-run setup |
| `dizflow/engine.py` | the pipeline: hotkey → record → transcribe → AI → paste → history |
| `dizflow/audio.py` | microphone, Whisper, sounds |
| `dizflow/llm.py` | Gemini / Claude prompts, app style detection, snippets |
| `dizflow/system.py` | global hotkeys, focused app, clipboard, start with Windows |
| `dizflow/store.py` | SQLite history, dictionary, snippets, stats |
| `dizflow/updater.py` | checks GitHub Releases, downloads and runs the new installer |
| `dizflow/ui/` | main window pages, overlay pill, theme |
| `installer.iss` | Inno Setup script for `Setup.exe` (start with Windows, shortcuts, uninstaller) |
