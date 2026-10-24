<#
Creates a self-signed code-signing certificate in your user certificate store (CurrentUser\My).

A self-signed certificate gives the files a valid signature (tamper evidence) but Windows does NOT trust it, so
SmartScreen still shows "unknown publisher". For publicly trusted signing see docs/SIGNING.md.
This script never adds anything to the Trusted Root store.
#>
[CmdletBinding()]
param([string]$Subject = "CN=COOL 68 Control Center (self-signed)", [int]$Years = 3)
$ErrorActionPreference = "Stop"
$existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $Subject -and $_.NotAfter -gt (Get-Date).AddDays(30) } | Select-Object -First 1
if ($existing) {
    Write-Host "Certificate already exists: $($existing.Thumbprint) (expires $($existing.NotAfter.ToShortDateString()))"
    return $existing
}
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject -KeyAlgorithm RSA -KeyLength 3072 `
    -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears($Years)
Write-Host "Created $($cert.Subject)  thumbprint $($cert.Thumbprint)  expires $($cert.NotAfter.ToShortDateString())"
$cert
