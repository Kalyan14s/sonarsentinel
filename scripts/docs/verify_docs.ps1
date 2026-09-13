<#
.SYNOPSIS
  Verifies SonarSentinel documentation.
  1. Relative Markdown links resolve and #anchors exist (GitHub-style heading slugs)
  2. Every referenced ID (FR, NFR, US, AC, TC, ST, EP, ADR, TD) is defined in its source document
  3. ASCII wireframe frames in docs/wireframes have consistent widths
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/docs/verify_docs.ps1
#>
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$files = Get-ChildItem -Path $Root -Recurse -Filter *.md -File -Force |
  Where-Object { $_.FullName -notmatch '\\(node_modules|\.git)\\' }
$problems = 0

function Get-RelPath([string]$p) { $p.Substring($Root.Length).TrimStart('\') }

# ---------- 1. Links and anchors ----------
$slugCache = @{}
function Get-Slugs([string]$path) {
  if ($slugCache.ContainsKey($path)) { return ,$slugCache[$path] }
  $slugs = New-Object 'System.Collections.Generic.HashSet[string]'
  $inCode = $false
  foreach ($line in [System.IO.File]::ReadAllLines($path, $utf8)) {
    if ($line.StartsWith('```')) { $inCode = -not $inCode; continue }
    if ($inCode) { continue }
    if ($line -match '^(#{1,6})\s+(.*)$') {
      $t = $Matches[2].Trim().ToLowerInvariant() -replace '`', ''
      $t = [regex]::Replace($t, '[^\p{L}\p{Nd}\s_-]', '')
      $t = $t -replace ' ', '-'
      $base = $t; $i = 1
      while (-not $slugs.Add($t)) { $t = "$base-$i"; $i++ }
    }
  }
  $slugCache[$path] = $slugs
  return ,$slugs
}

$linkRx = [regex]'\[[^\]]*\]\(([^)\s]+)\)'
$linkCount = 0
foreach ($f in $files) {
  $inCode = $false; $n = 0
  foreach ($line in [System.IO.File]::ReadAllLines($f.FullName, $utf8)) {
    $n++
    if ($line.StartsWith('```')) { $inCode = -not $inCode; continue }
    if ($inCode) { continue }
    $scan = [regex]::Replace($line, '`[^`]*`', '')   # ignore inline code spans
    foreach ($m in $linkRx.Matches($scan)) {
      $target = $m.Groups[1].Value
      if ($target -match '^(https?:|mailto:)') { continue }
      $linkCount++
      $parts = $target.Split('#', 2)
      $anchor = $null; if ($parts.Count -gt 1) { $anchor = $parts[1] }
      if ($parts[0] -eq '') { $resolved = $f.FullName }
      else { $resolved = [System.IO.Path]::GetFullPath((Join-Path $f.DirectoryName $parts[0])) }
      if (-not (Test-Path -LiteralPath $resolved)) {
        Write-Host ("LINK    {0}:{1} -> {2}" -f (Get-RelPath $f.FullName), $n, $target); $problems++; continue
      }
      if ($anchor -and $resolved.EndsWith('.md') -and -not (Get-Slugs $resolved).Contains($anchor)) {
        Write-Host ("ANCHOR  {0}:{1} -> {2}" -f (Get-RelPath $f.FullName), $n, $target); $problems++
      }
    }
  }
}

# ---------- 2. ID cross-references ----------
$defs = New-Object 'System.Collections.Generic.HashSet[string]'
$sources = @(
  @{ File = 'docs\PRD.md'; Patterns = @('^\| (FR-[A-Z]+-\d{2}) ', '^\| (NFR-\d{2}) ', '^\| (US-\d{2}) ', '\*\*(AC-\d{2}) ') },
  @{ File = 'docs\testing\TEST_CASES.md'; Patterns = @('^\| (TC-[A-Z0-9]+-\d{3}) ') },
  @{ File = 'docs\planning\PRODUCT_BACKLOG.md'; Patterns = @('^\| (ST-\d{3}) ', '^\| (EP-\d{2}) ') },
  @{ File = 'docs\architecture\08-architecture-decisions.md'; Patterns = @('^## (ADR-\d{3}) ') },
  @{ File = 'docs\testing\TEST_PLAN.md'; Patterns = @('^\| (TD-\d{2}) ') }
)
foreach ($s in $sources) {
  $text = [System.IO.File]::ReadAllText((Join-Path $Root $s.File), $utf8)
  foreach ($p in $s.Patterns) {
    foreach ($m in [regex]::Matches($text, $p, 'Multiline')) { [void]$defs.Add($m.Groups[1].Value) }
  }
}
$refRx = [regex]'\b(FR-[A-Z]+-\d{2}|NFR-\d{2}|US-\d{2}|AC-\d{2}|TC-[A-Z0-9]+-\d{3}|ST-\d{3}|EP-\d{2}|ADR-\d{3}|TD-\d{2})\b'
foreach ($f in $files) {
  $n = 0
  foreach ($line in [System.IO.File]::ReadAllLines($f.FullName, $utf8)) {
    $n++
    foreach ($m in $refRx.Matches($line)) {
      if (-not $defs.Contains($m.Value)) {
        Write-Host ("ID      {0}:{1} -> {2} is not defined" -f (Get-RelPath $f.FullName), $n, $m.Value); $problems++
      }
    }
  }
}

# ---------- 3. Wireframe frame widths ----------
$wfDir = Join-Path $Root 'docs\wireframes'
if (Test-Path $wfDir) {
  foreach ($f in Get-ChildItem -Path $wfDir -Filter *.md -File) {
    $inBlock = $false; $width = -1; $n = 0
    foreach ($line in [System.IO.File]::ReadAllLines($f.FullName, $utf8)) {
      $n++
      if ($line.StartsWith('```')) { $inBlock = ($line -eq '```text') -and -not $inBlock; $width = -1; continue }
      if ($inBlock -and ($line.StartsWith('|') -or $line.StartsWith('+'))) {
        if ($width -lt 0) { $width = $line.Length }
        elseif ($line.Length -ne $width) {
          Write-Host ("FRAME   {0}:{1} width {2}, expected {3}" -f (Get-RelPath $f.FullName), $n, $line.Length, $width); $problems++
        }
      }
    }
  }
}

Write-Host ("Checked {0} Markdown files, {1} relative links, {2} defined IDs. Problems: {3}" -f $files.Count, $linkCount, $defs.Count, $problems)
if ($problems -gt 0) { exit 1 }
