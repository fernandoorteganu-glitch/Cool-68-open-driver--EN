# Building and releasing

## Set up

Python 3.10 or newer (developed on 3.14, CI uses 3.12), Windows.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python gui.py                    # run from source
```

## Tests

```powershell
python -m pytest                 # unit tests, no keyboard needed
python tools\hardware_selftest.py --yes
```

The hardware self-test writes temporary values to a connected COOL 68 (a remapped key, an actuation point, lighting, a
profile switch, a polling-rate change) and restores each one in a `finally` block. Close the app and the vendor tool
first, because only one program can use the configuration interface. Use `--skip-polling` to leave the polling rate alone.

## Code layout

| Path | |
|---|---|
| `cool68.py` | the driver; no GUI code, usable on its own |
| `app/` | the Qt app: `main.py` window, `pages_a.py` / `pages_b.py` pages, `widgets.py` custom widgets, `effects.py` lighting preview, `keys.py` key names, `store.py` macro storage, `theme.py` |
| `docs/PROTOCOL.md` | the USB protocol |
| `installer/COOL68.iss` | Inno Setup script |
| `scripts/` | build, sign and certificate scripts |
| `tools/` | hardware self-test |

Macros are stored in `%APPDATA%\COOL68\macros.json` because the keyboard cannot read them back. Unexpected errors are
logged to `%APPDATA%\COOL68\error.log`.

## Build a release

```powershell
winget install JRSoftware.InnoSetup                       # once; installs for your user, no admin needed
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

This produces, in `release/`:

* `COOL68-Setup-<version>.exe`: per-user installer (no admin rights, Start menu entry, uninstaller)
* `COOL68-<version>-portable.exe`: single-file build
* `SHA256SUMS.txt`

Add `-Sign` to sign the files; see [SIGNING.md](SIGNING.md).

## Cut a release on GitHub

1. Change `__version__` in `app/__init__.py`.
2. Commit, then `git tag v1.2.3 && git push --tags`.
3. The workflow runs the tests, builds, and attaches the files to a new GitHub Release.

The installer keeps a fixed `AppId`, so installing a newer version upgrades the old one in place.
