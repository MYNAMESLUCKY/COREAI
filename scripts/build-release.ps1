param(
    [Parameter(Mandatory=$true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $repoRoot "dist"
$outDir = Join-Path $distRoot ("Yogz-win-x64-{0}" -f $Version)
$zipPath = $outDir + ".zip"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# Build Go agent
$goAgentDir = Join-Path $repoRoot "backend\go_agent"
Write-Host "Building Go agent..."
go build -o (Join-Path $outDir "agent.exe") .\cmd\agent

# Copy required runtime files (dev packaging)
# Production target: ship python_agent_server.exe instead of raw python files.
Write-Host "Copying backend runtime (dev)..."
Copy-Item -Recurse -Force (Join-Path $repoRoot "backend\python_agent_server.py") $outDir
Copy-Item -Recurse -Force (Join-Path $repoRoot "backend\simple_agent.py") $outDir
Copy-Item -Recurse -Force (Join-Path $repoRoot "backend\requirements.txt") $outDir

# Docs
Copy-Item -Recurse -Force (Join-Path $repoRoot "README.md") $outDir
Copy-Item -Recurse -Force (Join-Path $repoRoot "docs") (Join-Path $outDir "docs")

# Zip
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Write-Host "Creating zip: $zipPath"
Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath

Write-Host "Done. Output: $zipPath"
