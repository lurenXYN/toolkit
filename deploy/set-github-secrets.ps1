# Set toolkit GitHub Actions deploy secrets (reuse market-desk key by default).
# Usage:
#   .\deploy\set-github-secrets.ps1 -HostName "1.2.3.4"
#   .\deploy\set-github-secrets.ps1 -HostName "1.2.3.4" -User "root" -KeyPath "C:\Users\BSI\market-desk-deploy"
param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$User = "root",

    [string]$KeyPath = "C:\Users\BSI\market-desk-deploy",

    [string]$Repo = "lurenXYN/toolkit"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $KeyPath)) {
    throw "Deploy key not found: $KeyPath"
}

Write-Host "Setting secrets on $Repo ..."
gh secret set DEPLOY_HOST -R $Repo --body $HostName
gh secret set DEPLOY_USER -R $Repo --body $User
Get-Content -Raw $KeyPath | gh secret set DEPLOY_SSH_KEY -R $Repo

Write-Host "Done. Secrets:"
gh secret list -R $Repo
Write-Host ""
Write-Host "Next: bootstrap VPS, then re-run Actions Deploy workflow."
