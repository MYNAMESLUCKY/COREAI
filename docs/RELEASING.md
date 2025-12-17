# Releasing Yogz (Windows)

This document describes how to publish a professional downloadable build using **GitHub Releases**.

## What users download

A single zip file per version, for example:

- `Yogz-win-x64-v0.1.0.zip`

Contents (current dev layout):

- `agent.exe`
- `backend/` runtime files needed for Python service (temporary until Python is packaged)

> Production target: include `python_agent_server.exe` (PyInstaller) instead of raw Python.

## Versioning

Use semver:

- `v0.1.0`, `v0.1.1`, `v1.0.0`, ...

## Build artifacts

From a PowerShell prompt:

```powershell
# From repo root
.\scripts\build-release.ps1 -Version v0.1.0
```

The script will create:

- `dist\Yogz-win-x64-v0.1.0\`
- `dist\Yogz-win-x64-v0.1.0.zip`

## Publish to GitHub Releases

1. Create a Git tag

```powershell
git tag v0.1.0
git push origin v0.1.0
```

2. Create a GitHub Release

- Go to your repo → **Releases** → **Draft a new release**
- Choose tag `v0.1.0`
- Upload `dist\Yogz-win-x64-v0.1.0.zip`

3. Share the download link

GitHub will generate a stable link like:

- `https://github.com/<org>/<repo>/releases/download/v0.1.0/Yogz-win-x64-v0.1.0.zip`

## Recommended: signing

To reduce Windows SmartScreen warnings:

- Sign `agent.exe` with Authenticode
- Optionally sign the zip

## Recommended: checksums

Add a checksum file per release:

```powershell
Get-FileHash .\dist\Yogz-win-x64-v0.1.0.zip -Algorithm SHA256
```

Paste the SHA256 into the GitHub Release notes.

## Roadmap for a production installer

- MSIX (preferred) or Inno Setup
- Automatic updates (MSIX) or `winget` distribution
- Bundle Python service as `python_agent_server.exe`
