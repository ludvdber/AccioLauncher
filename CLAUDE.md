# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Accio Launcher is a PyQt6 desktop launcher for Harry Potter PC games. All UI text and code comments are in **French**.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

No test framework is configured yet.

## Architecture

Three-layer structure under `src/`:

- **`src/core/`** — Business logic: configuration (`Config` class with JSON persistence), game catalog management (`GameManager`), download via httpx (`Downloader`), and 7z extraction via py7zr (`Installer`).
- **`src/ui/`** — PyQt6 interface: `MainWindow` (1200×800), `GameCard` widget per game, Qt stylesheets in `styles.py`.
- **`src/data/games.json`** — Static catalog of 6 HP games with download URLs, executable paths, and metadata.

Entry point is `main.py` which creates the `QApplication` and shows `MainWindow`.

## Key Conventions

- Python 3.10+ type hints (`str | Path`, `dict | None`)
- `pathlib.Path` for all filesystem operations
- Default install path: `~/Games/AccioLauncher`, cache: `~/Games/AccioLauncher/.cache`
- Config persisted to `~/Games/AccioLauncher/config.json`
- Dark theme UI (background `#1a1a2e`)
