# LabDesk

LabDesk is a native Python desktop workbench for oscilloscope-style waveform acquisition, live preview, export,and report-ready image generation. It runs with a built-in simulated backend and includes an experimental SCPI / pyvisa backend for real instruments.

![LabDesk](assets/logo.jpg)

![Python](https://img.shields.io/badge/python-3.9+-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- Tkinter + Matplotlib desktop UI.
- Simulated backend for demo and development without hardware.
- Experimental VISA / SCPI backend using `pyvisa`.
- Live waveform acquisition with dual preview panes.
- Multi-channel CSV export, SVG export, and PNG/BMP capture.
- Channel, trigger, measurement, export, and raw command tabs.
- INI-based configuration persistence.
- PyInstaller packaging config for Windows builds.

## Screenshots

Add a few app screenshots here before publishing the repository. A good set is:
- main dashboard
- simulated waveform preview
- export panel
- console tab

## Quick Start

```bash
git clone https://github.com/<your-account>/labdesk.git
cd labdesk
pip install -r requirements.txt
python labdesk.py
```

On Windows you can also double-click `bootstrap_labdesk.bat` for a first-run setup,
or `start_labdesk.bat` if the environment is already prepared.

## Simulated Mode

1. Keep `Interface` set to `Simulated`.
2. Click `Discover`.
3. Select a demo resource and click `Connect`.
4. Use `RUN`, `SINGLE`, export, metrics, and console features without hardware.

## Real Instruments

1. Install the dependencies from `requirements.txt`.
2. Install the VISA runtime required by your platform or adapter.
3. Connect the oscilloscope by USB, LAN, GPIB, or another VISA-supported transport.
4. Set `Interface` to `VISA (pyvisa)`.
5. Click `Discover`, choose a VISA resource, then click `Connect`.
6. Use the console tab to test `*IDN?` and `:TRIG:STAT?`.

## Testing

```bash
python -m unittest discover -s tests -v
python -m py_compile labdesk.py core/engine.py core/acquisition.py core/__init__.py
```

## Build

```bash
pip install pyinstaller
pyinstaller LabDesk.spec
```

The executable is generated in `dist/`.

For repeatable Windows packaging, run `build_release.bat`.

## Packaging Notes

- `labdesk.ini` is ignored because it is runtime state.
- `venv/` and `.venv/` are ignored because local environments should not be committed.
- `dist/` and `build/` are ignored because they are generated artifacts.
- `bootstrap_labdesk.bat` is for first-run setup.
- `start_labdesk.bat` is for normal launch.

## License

MIT. See [LICENSE](LICENSE).
