$ErrorActionPreference = "Stop"

# git emits commit messages as UTF-8 bytes; force PowerShell to decode native
# command output as UTF-8 too, otherwise non-ASCII (e.g. Chinese) gets mangled
# under the OEM/Big5 console code page before it reaches the UTF-8 writer below.
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  $lines = git -c i18n.logOutputEncoding=UTF-8 log --date=iso-strict --pretty=format:"%aI%x09%s"
  $days = [ordered]@{}

  foreach ($line in $lines) {
    if (-not $line) { continue }
    $parts = $line -split "`t", 2
    if ($parts.Count -lt 2) { continue }

    $dateTime = [datetimeoffset]::Parse($parts[0])
    $date = $dateTime.ToString("yyyy-MM-dd")
    $time = $dateTime.ToString("HH:mm")

    if (-not $days.Contains($date)) {
      $days[$date] = @()
    }

    $days[$date] += [pscustomobject]@{
      time = $time
      message = $parts[1]
    }
  }

  $changelog = @()
  foreach ($date in $days.Keys) {
    $changelog += [pscustomobject]@{
      date = $date
      items = @($days[$date])
    }
  }

  $json = $changelog | ConvertTo-Json -Depth 6
  $outPath = Join-Path $repoRoot "data\changelog.json"
  [System.IO.File]::WriteAllText($outPath, $json + "`n", $utf8NoBom)
}
finally {
  Pop-Location
}
