# Code signing

Windows shows "Windows protected your PC" (SmartScreen) for programs from a publisher it does not know. What that
publisher check needs is a **certificate that Windows trusts**, issued to a verified person or organisation. Here is what
this project does and what your choices are.

## What the release builds use today

`scripts/build.ps1 -Sign` signs the app's `COOL68-Open-Driver.exe`, the installer (and the portable exe with `-Portable`) with **Authenticode (SHA-256 and a
trusted timestamp)** using a **self-signed certificate** made by `scripts/new-selfsigned-cert.ps1`.

* The signature is real: it proves the file has not been altered since it was signed (`Get-AuthenticodeSignature file.exe`).
* Windows does **not** trust a self-signed certificate, so the publisher still shows as unknown and SmartScreen may
  warn on the first run. Users click **More info → Run anyway**.
* Put the installer's SHA-256 (printed at the end of `scripts/build.ps1`) in the release notes so people can verify their download with `Get-FileHash`.
* The script never installs the certificate into the *Trusted Root* store. Don't ask users to do that; it weakens their
  security.

## Getting a publicly trusted signature

| Option | Cost | Notes |
|---|---|---|
| **[SignPath Foundation](https://signpath.org/)** | free for open-source projects | Apply with the public repo; signs from GitHub Actions. The best fit for this project |
| **Azure Trusted Signing** | small monthly fee | Microsoft's service; needs identity validation |
| **Commercial OV / EV certificate** | yearly fee | EV removes the SmartScreen warning fastest; OV builds reputation with downloads |

SmartScreen also builds *reputation* as more people download a signed file, so a new release can still warn for a short while.

### Signing in CI with a certificate you own

Add two repository secrets (Settings → Secrets and variables → Actions):

* `SIGNING_PFX_BASE64`: your `.pfx` file, base64-encoded (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`)
* `SIGNING_PFX_PASSWORD`: its password

The workflow in `.github/workflows/build.yml` then signs its CI build with that certificate. The CI build is only a workflow
artifact; releases are published by hand (see BUILDING.md). Never commit a `.pfx` (`.gitignore` blocks them).

### Signing locally

```powershell
powershell -ExecutionPolicy Bypass -File scripts\new-selfsigned-cert.ps1     # once
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -Sign
Get-AuthenticodeSignature release\COOL68-Open-Driver-Setup-1.0.0.exe | Format-List Status, SignerCertificate
```

With a self-signed certificate `Status` reads `UnknownError` / "not trusted": that is expected, and the signature is still present and valid.
