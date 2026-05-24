# LabDesk Release Guide

## Build Requirements

- Python 3.9 or newer
- `pip install -r requirements.txt`
- `pip install pyinstaller`

## Build

```bash
pyinstaller LabDesk.spec
```

Or on Windows:

```bat
build_release.bat
```

## Output

- `dist/LabDesk/` for folder builds
- `dist/LabDesk.exe` if you later switch the spec to a one-file build

## What To Upload To GitHub

- Source files: `labdesk.py`, `core/`, `tests/`, `assets/`
- Documentation: `README.md`, `README_CN.md`, `RELEASE.md`
- Packaging: `LabDesk.spec`, `build_release.bat`
- Startup helpers: `start_labdesk.bat`, `bootstrap_labdesk.bat`
- License and dependency list

## Do Not Commit

- `venv/`, `.venv/`
- `__pycache__/`
- `dist/`, `build/`
- `labdesk.ini`
- `output/`, `logs/`, `screenshots/`
