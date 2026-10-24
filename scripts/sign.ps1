<#
Signs files with Authenticode (SHA-256, with a trusted timestamp so the signature outlives the certificate).

  scripts/sign.ps1 -Files dist\COOL68\COOL68.exe, release\COOL68-Setup-1.0.0.exe
  scripts/sign.ps1 -Files x.exe -PfxPath cert.pfx -PfxPassword (Read-Host -AsSecureString)

Without -PfxPath it uses the self-signed certificate from scripts/new-selfsigned-cert.ps1.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string[]]$Files,
    [string]$PfxPath,
    [securestring]$PfxPassword,
    [string]$Subject = "CN=COOL 68 Control Center (self-signed)",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)
$ErrorActionPreference = "Stop"
if ($PfxPath) {
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($PfxPath, $PfxPassword)
} else {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $Subject } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if (-not $cert) { throw "No code-signing certificate found. Run scripts/new-selfsigned-cert.ps1 first, or pass -PfxPath." }
}
foreach ($f in $Files) {
    $res = Set-AuthenticodeSignature -FilePath $f -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $TimestampServer
    if (-not $res.SignerCertificate) { throw "Signing failed for ${f}: $($res.StatusMessage)" }
    Write-Host ("signed {0}  ({1})" -f $f, $res.Status)
}
