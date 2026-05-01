$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  $lines = git log --date=iso-strict --pretty=format:"%aI%x09%s"
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
  [System.IO.File]::WriteAllText($outPath, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}
finally {
  Pop-Location
}
