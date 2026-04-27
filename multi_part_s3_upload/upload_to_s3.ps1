[CmdletBinding()]
param(
    # Base64-encoded presigned GET URL for the multipart metadata JSON.
    # Mirrors the ${METADATA_URL_B64} substitution in Export_Video.ps1 / LineVuConnect.py.
    [Parameter(Mandatory=$true)]
    [string]$PreSignedUrlB64,

    [Parameter(Mandatory=$true)]
    [string]$FilePath,

    # Max concurrent part uploads. Defaults to 4, matching Export_Video.ps1.
    [Parameter(Mandatory=$false)]
    [int]$Parallelism = 4
)

if (-not (Test-Path $FilePath)) {
    Write-Error "File not found: $FilePath"
    exit 1
}

$fileInfo = Get-Item $FilePath
$fileSize = $fileInfo.Length
Write-Output "File:  $FilePath"
Write-Output "Size:  $([Math]::Round($fileSize / 1MB, 2)) MB"

# Decode URL — same logic as Export_Video.ps1 line 58
$presignedUrl = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($PreSignedUrlB64))
Write-Output "Fetching multipart upload metadata..."
$mpResp = Invoke-WebRequest -Uri $presignedUrl -Method Get -UseBasicParsing
$mp = $mpResp.Content | ConvertFrom-Json

$partSz    = [long]$mp.partSize
$partUrls  = $mp.partUrls
$completeUrl = $mp.completeUrl
$numParts  = [Math]::Ceiling($fileSize / $partSz)

if ($numParts -gt $partUrls.Count) {
    Write-Error "File requires $numParts parts but only $($partUrls.Count) presigned URLs were provided."
    exit 1
}

$concurrency = [Math]::Min($Parallelism, $numParts)
Write-Output "Uploading $numParts parts of $([Math]::Round($partSz / 1MB, 0)) MB each ($concurrency concurrent)..."

$startTime = Get-Date

# Runspace-based parallel upload — same mechanism as Export_Video.ps1
$etags = [System.Collections.Concurrent.ConcurrentDictionary[int,string]]::new()
$pool  = [System.Management.Automation.Runspaces.RunspaceFactory]::CreateRunspacePool(1, $concurrency)
$pool.Open()
$jobs = @()

for ($i = 0; $i -lt $numParts; $i++) {
    $ps = [System.Management.Automation.PowerShell]::Create()
    $ps.RunspacePool = $pool
    $null = $ps.AddScript({
        param($idx, $url, $path, $sz, $total, $dict, $numParts)
        $offset    = [long]$idx * [long]$sz
        $chunkSize = [Math]::Min($sz, $total - $offset)
        $buf       = [byte[]]::new($chunkSize)
        $fs        = [System.IO.File]::OpenRead($path)
        $fs.Seek($offset, [System.IO.SeekOrigin]::Begin) | Out-Null
        $fs.Read($buf, 0, $chunkSize) | Out-Null
        $fs.Close()
        $resp = Invoke-WebRequest -Uri $url -Method Put -Body $buf -UseBasicParsing
        $etag = $resp.Headers['ETag']
        if ($etag -is [System.Object[]]) { $etag = $etag[0] }
        $dict[$idx + 1] = $etag
        Write-Host "  Part $($idx + 1)/$numParts done ($chunkSize bytes)"
    }).AddParameters(@{
        idx      = $i
        url      = $partUrls[$i]
        path     = $FilePath
        sz       = $partSz
        total    = $fileSize
        dict     = $etags
        numParts = $numParts
    })
    $jobs += [PSCustomObject]@{ PS = $ps; IA = $ps.BeginInvoke() }
}

foreach ($job in $jobs) { $job.PS.EndInvoke($job.IA); $job.PS.Dispose() }
$pool.Close()
$pool.Dispose()

Write-Output "All parts uploaded. Completing multipart upload..."

# Build completion XML — same structure as Export_Video.ps1
$xml = "<?xml version=""1.0"" encoding=""UTF-8""?><CompleteMultipartUpload>"
for ($p = 1; $p -le $numParts; $p++) {
    $xml += "<Part><PartNumber>$p</PartNumber><ETag>$($etags[$p])</ETag></Part>"
}
$xml += "</CompleteMultipartUpload>"

$xmlBytes = [System.Text.Encoding]::UTF8.GetBytes($xml)
Invoke-WebRequest -Uri $completeUrl -Method Post -Body $xmlBytes -ContentType "application/xml" -UseBasicParsing | Out-Null

$elapsed = (Get-Date) - $startTime
Write-Output "Done. $numParts parts uploaded in $($elapsed.TotalSeconds.ToString('F2'))s"
