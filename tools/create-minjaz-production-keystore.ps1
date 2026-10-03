param(
    [switch]$ConfigureGitHub,
    [string]$Repository = "i20sss20-maker/MINJAZ",
    [string]$Alias = "minjaz-production"
)

$ErrorActionPreference = "Stop"

function Read-ConfirmedSecret {
    param([string]$Label)
    while ($true) {
        $first = Read-Host "$Label (12+ characters, ASCII recommended)" -AsSecureString
        $second = Read-Host "Confirm $Label" -AsSecureString
        $aPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($first)
        $bPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($second)
        try {
            $a = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($aPtr)
            $b = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bPtr)
            if ($a.Length -lt 12) {
                Write-Warning "$Label must be at least 12 characters."
                continue
            }
            if ($a -ne $b) {
                Write-Warning "Values did not match. Try again."
                continue
            }
            return $a
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($aPtr)
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bPtr)
        }
    }
}

$keytool = Get-Command keytool -ErrorAction SilentlyContinue
if (-not $keytool) {
    throw "keytool was not found. Install/open Android Studio JDK (Java 17+) and run this script again."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$privateDir = Join-Path $repoRoot "release-private"
$keystorePath = Join-Path $privateDir "minjaz-production.jks"
New-Item -ItemType Directory -Force -Path $privateDir | Out-Null

if (Test-Path $keystorePath) {
    throw "Keystore already exists at $keystorePath. Refusing to overwrite the production signing identity."
}

$storePass = Read-ConfirmedSecret "Keystore password"
$keyPass = Read-ConfirmedSecret "Key password"

try {
    $env:MINJAZ_KS_PASS = $storePass
    $env:MINJAZ_KEY_PASS = $keyPass

    $genArgs = @(
        "-genkeypair",
        "-v",
        "-keystore", $keystorePath,
        "-storetype", "JKS",
        "-alias", $Alias,
        "-keyalg", "RSA",
        "-keysize", "4096",
        "-validity", "10000",
        "-dname", "CN=MINJAZ Android Release, O=MINJAZ, C=SA",
        "-storepass:env", "MINJAZ_KS_PASS",
        "-keypass:env", "MINJAZ_KEY_PASS"
    )
    & $keytool.Source @genArgs

    $listArgs = @(
        "-list",
        "-v",
        "-keystore", $keystorePath,
        "-alias", $Alias,
        "-storepass:env", "MINJAZ_KS_PASS"
    )
    & $keytool.Source @listArgs

    $bytes = [IO.File]::ReadAllBytes($keystorePath)
    $base64 = [Convert]::ToBase64String($bytes)

    if ($ConfigureGitHub) {
        $gh = Get-Command gh -ErrorAction SilentlyContinue
        if (-not $gh) {
            throw "GitHub CLI (gh) is not installed. Re-run without -ConfigureGitHub, or install gh first."
        }

        & $gh.Source auth status | Out-Null

        $base64 | & $gh.Source secret set MINJAZ_ANDROID_KEYSTORE_BASE64 --repo $Repository
        $storePass | & $gh.Source secret set MINJAZ_ANDROID_KEYSTORE_PASSWORD --repo $Repository
        $Alias | & $gh.Source secret set MINJAZ_ANDROID_KEY_ALIAS --repo $Repository
        $keyPass | & $gh.Source secret set MINJAZ_ANDROID_KEY_PASSWORD --repo $Repository

        Write-Host ""
        Write-Host "GitHub production signing secrets configured for $Repository."
    }
    else {
        Set-Clipboard -Value $base64
        Write-Host ""
        Write-Host "Keystore created: $keystorePath"
        Write-Host "The Base64 keystore value is now in your clipboard."
        Write-Host "Add these repository secrets in GitHub:"
        Write-Host "  MINJAZ_ANDROID_KEYSTORE_BASE64   = paste clipboard"
        Write-Host "  MINJAZ_ANDROID_KEYSTORE_PASSWORD = the keystore password you entered"
        Write-Host "  MINJAZ_ANDROID_KEY_ALIAS         = $Alias"
        Write-Host "  MINJAZ_ANDROID_KEY_PASSWORD      = the key password you entered"
    }

    Write-Host ""
    Write-Host "IMPORTANT: Back up minjaz-production.jks and both passwords securely. Do not regenerate a different key after release."
}
finally {
    Remove-Item Env:MINJAZ_KS_PASS -ErrorAction SilentlyContinue
    Remove-Item Env:MINJAZ_KEY_PASS -ErrorAction SilentlyContinue
    $storePass = $null
    $keyPass = $null
}
