#Requires -Version 5.1
<#
.SYNOPSIS
Run CVAnalysis tests in an isolated, disposable workspace.

.DESCRIPTION
Creates a fresh basetemp and cache under .test_tmp for each run, avoids
Python bytecode files, and removes both after a
successful run.  A failed run keeps its basetemp so the failure can be
inspected.

The project root is derived from this script's location, so it can be invoked
from any directory.

.PARAMETER Python
Python executable to use. Defaults to "python".

.PARAMETER KeepTemp
Keep the basetemp even when all tests pass.

.PARAMETER PytestArgs
Additional pytest arguments, for example: -PytestArgs @('-k','legend').

.PARAMETER Suite
All tests, GUI-focused tests, plotting/text tests, or release checks.

.PARAMETER Targets
Explicit pytest files or node IDs. Replaces the preset Suite targets.

.PARAMETER Durations
Show the slowest N tests; zero disables the duration report.

.EXAMPLE
.\tools\run_tests.ps1

.EXAMPLE
.\tools\run_tests.ps1 -PytestArgs @('-k','liquid_glass','--tb=long')
#>
[CmdletBinding()]
param(
    [string]$Python = 'python',
    [switch]$KeepTemp,
    [ValidateSet('All', 'Gui', 'Plotting', 'Release')]
    [string]$Suite = 'All',
    [string[]]$Targets = @(),
    [ValidateRange(0, 1000)]
    [int]$Durations = 0,
    [string[]]$PytestArgs = @()
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $root '.test_tmp'
$runId = [guid]::NewGuid().ToString('N')
$base = Join-Path $testRoot ('run_' + $runId)
$cacheDir = Join-Path $testRoot ('cache_' + $runId)

foreach ($argument in $PytestArgs) {
    if ($argument -match '^--basetemp(?:=|$)' -or $argument -match 'cache_dir\s*=') {
        throw 'Do not override basetemp or cache_dir; this script isolates both for each run.'
    }
}
foreach ($target in $Targets) {
    if ([string]::IsNullOrWhiteSpace($target) -or $target.StartsWith('-')) {
        throw 'Targets accepts test paths or node IDs; put options in PytestArgs.'
    }
}
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
if (((Get-Item -LiteralPath $testRoot -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Refusing to use a linked test root: $testRoot"
}

$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'

function Remove-DirectoryTree {
    param([string]$Path)
    $absolute = [System.IO.Path]::GetFullPath($Path)
    $allowed = @([System.IO.Path]::GetFullPath($base), [System.IO.Path]::GetFullPath($cacheDir))
    if ($absolute -notin $allowed) { throw "Refusing to clean an unexpected path: $absolute" }
    function Remove-Entry {
        param([string]$Entry)
        $item = Get-Item -LiteralPath $Entry -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) { return }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            if ($item.PSIsContainer) { [System.IO.Directory]::Delete($item.FullName) }
            else { [System.IO.File]::Delete($item.FullName) }
            return
        }
        if ($item.PSIsContainer) {
            foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) {
                Remove-Entry -Entry $child.FullName
            }
        }
        Remove-Item -LiteralPath $item.FullName -Force -ErrorAction Stop
    }
    try { Remove-Entry -Entry $absolute } catch { Write-Warning $_; return $false }
    return -not (Test-Path -LiteralPath $absolute)
}

$exitCode = 1
$originalPath = $env:PATH
Push-Location $root
try {
    # Match build.bat: a selected conda Python must resolve its own DLLs before
    # any other Python installation inherited from the calling shell.
    $pythonCommand = Get-Command -Name $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $pythonHome = Split-Path -Parent $pythonCommand.Source
    if (Test-Path -LiteralPath (Join-Path $pythonHome 'Library\bin')) {
        $env:PATH = (@($pythonHome, (Join-Path $pythonHome 'Library\bin'),
                      (Join-Path $pythonHome 'Scripts')) -join ';') + ';' + $originalPath
    }
    Write-Host "[INFO] Python    : $Python"
    Write-Host "[INFO] Workspace : $root"
    Write-Host "[INFO] Basetemp  : $base"
    Write-Host "[INFO] Cache     : $cacheDir"
    Write-Host "[INFO] Suite     : $Suite"
    Write-Host ''

    $suiteTargets = if ($Targets.Count -gt 0) { $Targets } else { switch ($Suite) {
        'Gui' { @('tests_v2/test_design_system.py', 'tests_v2/test_liquid_glass.py',
                  'tests_v2/test_application_icon.py',
                  'tests_v2/test_dialog_consistency.py',
                  'tests_v2/test_glass_menu.py', 'tests_v2/test_glass_tooltips.py',
                  'tests_v2/test_combo_popups.py', 'tests_v2/test_gui_layout.py',
                  'tests_v2/test_gui_smoke.py', 'tests_v2/test_layout_reflow.py',
                  'tests_v2/test_results_tree.py', 'tests_v2/test_theme.py',
                  'tests_v2/test_settings.py', 'tests_v2/test_tab_close.py',
                  'tests_v2/test_redraw_scope.py', 'tests_v2/test_text_presets.py',
                  'tests_v2/test_plot_color_panel.py', 'tests_v2/test_user_project_feedback.py',
                  'tests_v2/test_it_y_reference.py', 'tests_v2/test_it_reference_layout.py') }
        'Plotting' { @('tests_v2/test_plotting.py', 'tests_v2/test_paper_legend.py',
                       'tests_v2/test_safe_template_format.py', 'tests_v2/test_text_presets.py',
                       'tests_v2/test_it_reference_layout.py', 'tests_v2/test_it_y_reference.py',
                       'tests_v2/test_sweep_reference_display.py', 'tests_v2/test_plot_unit_safety.py') }
        'Release' { @('tests_v2/test_release_contract.py', 'tests_v2/test_application_icon.py') }
        default { @('tests_v2') }
    } }
    Write-Host "[INFO] Targets   : $($suiteTargets -join ', ')"
    $pytestCommand = @(
        '-m', 'pytest',
        '-q',
        '-o', 'addopts=',
        '-o', "cache_dir=$cacheDir",
        '--basetemp', $base,
        '--tb=short'
    ) + $suiteTargets + $PytestArgs
    if ($Durations -gt 0) { $pytestCommand += "--durations=$Durations" }

    & $Python @pytestCommand
    $exitCode = $LASTEXITCODE
}
finally {
    $env:PATH = $originalPath
    Pop-Location
}

if ($exitCode -eq 0) {
    if (-not $KeepTemp) {
        $baseExisted = Test-Path -LiteralPath $base
        if (Remove-DirectoryTree $base) {
            if ($baseExisted) {
                Write-Host "[INFO] Removed basetemp: $base"
            }
        }
        else {
            Write-Warning "Tests passed, but basetemp could not be removed: $base"
        }

        $cacheExisted = Test-Path -LiteralPath $cacheDir
        if (Remove-DirectoryTree $cacheDir) {
            if ($cacheExisted) {
                Write-Host "[INFO] Removed pytest cache: $cacheDir"
            }
        }
        else {
            Write-Warning "Tests passed, but pytest cache could not be removed: $cacheDir"
        }

    }
    else {
        Write-Host "[INFO] Kept basetemp: $base"
        Write-Host "[INFO] Kept cache: $cacheDir"
    }
}
else {
    Write-Host "[INFO] Tests failed; basetemp kept for inspection: $base" -ForegroundColor Yellow
    Write-Host "[INFO] Cache kept for inspection: $cacheDir" -ForegroundColor Yellow
}

exit $exitCode
