# Tools

- `install.py`, `download_model.py` — install Python dependencies and the offline Vosk model; called by `setup.bat`.
- `install_ai.py` — set up Ollama and choose a local model; called by `setup_ai.bat`.
- `convert_anim.py` — convert a source video into PNG animation frames under `assets/anim/`.
- `make_media.py` — generate repository banner and optional preview GIFs.
- `make_release.py` / `make_release.bat` — build a distributable ZIP without local settings, logs, reports, samples or unpacked models.
- `voice_stats.py` — inspect timing/pitch statistics for a voice recording.

Tests are in `tests/`. One-time `apply_*.py` patchers were removed after their changes were integrated into the application; previous versions remain available in Git history.
