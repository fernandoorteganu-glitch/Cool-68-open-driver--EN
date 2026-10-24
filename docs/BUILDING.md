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

This produces one file in `release/`:

* `COOL68-Open-Driver-Setup-<version>.exe`: the per-user installer (no admin rights, Start menu entry, uninstaller). This is the only file users need.

Add `-Portable` if you also want a single-file `COOL68-Open-Driver-<version>-portable.exe` and a `SHA256SUMS.txt`.
The build prints the installer's SHA-256 at the end, for the release notes.

Add `-Sign` to sign the files; see [SIGNING.md](SIGNING.md).

## Publish a release on GitHub

Releases are published by hand, so the file people download is the installer you built, signed and tested.

1. Change `__version__` in `app/__init__.py`, commit and push to `main`.
2. Build locally with signing: `powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Sign`. It prints the installer's SHA-256.
3. On GitHub: Releases → Draft a new release → create the tag `vX.Y.Z` on `main`.
4. Attach `release/COOL68-Open-Driver-Setup-X.Y.Z.exe` (only that file) and put its SHA-256 in the description.
5. Publish.

The workflow in `.github/workflows/build.yml` also runs on the tag. It runs the tests and builds an unsigned copy of
the installer as a workflow artifact for comparison; it never touches the release.

The installer keeps a fixed `AppId`, so installing a newer version upgrades the old one in place.
