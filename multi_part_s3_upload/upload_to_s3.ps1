[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, ParameterSetName="SinglePut")]
    [string]$PresignedUrl,

    # Local/test: config written to a temp file by the caller on the same machine
    [Parameter(Mandatory=$true, ParameterSetName="MultiPartFile")]
    [string]$MultipartConfigPath,

    # Production SSH: caller pipes JSON to stdin, e.g.:
    #   echo '{...}' | ssh windows_host "pwsh -File upload_to_s3.ps1 -MultipartStdin -FilePath C:\video.mkv"
    [Parameter(Mandatory=$true, ParameterSetName="MultiPartStdin")]
    [switch]$MultipartStdin,

    [Parameter(Mandatory=$true)]
    [string]$FilePath,

    # Number of parts to upload concurrently. Defaults to all parts at once.
    # Lower this if you want to cap bandwidth usage on a shared link.
    [Parameter(Mandatory=$false)]
    [int]$Parallelism = 0
)

if (-not (Test-Path $FilePath)) {
    Write-Error "File not found: $FilePath"
    exit 1
}

$fileInfo = Get-Item $FilePath
$fileSize = $fileInfo.Length

Write-Output "File:     $FilePath"
Write-Output "Size:     $fileSize bytes"

if ($PSCmdlet.ParameterSetName -eq "SinglePut") {
    Write-Output "Uploading to S3 (single PUT)..."

    $headers = @{
        "x-amz-tagging"  = "docType=real-time"
        "Content-Length" = $fileSize
    }

    $startTime = Get-Date
    Invoke-WebRequest -Uri $PresignedUrl -Method Put -Headers $headers -InFile $FilePath -UseBasicParsing
    $elapsed = (Get-Date) - $startTime

    Write-Output "Upload complete in $($elapsed.TotalSeconds.ToString('F2'))s"
}
else {
    if ($PSCmdlet.ParameterSetName -eq "MultiPartFile") {
        $config = Get-Content -Raw $MultipartConfigPath | ConvertFrom-Json
    }
    else {
        $config = [Console]::In.ReadToEnd() | ConvertFrom-Json
    }

    $partSize  = [long]$config.partSizeBytes
    $partCount = [Math]::Ceiling($fileSize / $partSize)

    if ($partCount -gt $config.partUrls.Count) {
        Write-Error "File requires $partCount parts but only $($config.partUrls.Count) presigned part URLs were provided."
        exit 1
    }

    $concurrency = if ($Parallelism -gt 0) { $Parallelism } else { $partCount }
    Write-Output "Uploading to S3 (multi-part: $partCount parts of $([Math]::Round($partSize / 1MB, 0)) MB each, $concurrency concurrent)..."

    $startTime = Get-Date

    $parts = 0..($partCount - 1) | ForEach-Object -ThrottleLimit $concurrency -Parallel {
        $i         = $_
        $partNum   = $i + 1
        $cfg       = $using:config
        $partUrl   = $cfg.partUrls[$i]
        $partBytes = [long]$cfg.partSizeBytes
        $filePath  = $using:FilePath
        $fileSize  = $using:fileSize
        $total     = $using:partCount

        $offset    = $i * $partBytes
        $chunkSize = [Math]::Min($partBytes, $fileSize - $offset)

        $stream = [System.IO.File]::OpenRead($filePath)
        $reader = New-Object System.IO.BinaryReader($stream)
        try {
            $null = $stream.Seek($offset, [System.IO.SeekOrigin]::Begin)
            $data = $reader.ReadBytes($chunkSize)
        }
        finally {
            $reader.Close()
        }

        $client = [System.Net.Http.HttpClient]::new()
        try {
            $attempt = 0
            while ($true) {
                try {
                    $content = [System.Net.Http.ByteArrayContent]::new($data)
                    $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/octet-stream")
                    $resp = $client.PutAsync($partUrl, $content).GetAwaiter().GetResult()
                    $resp.EnsureSuccessStatusCode() | Out-Null
                    $etag = $resp.Headers.GetValues("ETag") | Select-Object -First 1
                    Write-Host "  Part $partNum/$total done ($chunkSize bytes)"
                    return [PSCustomObject]@{ PartNumber = $partNum; ETag = $etag }
                }
                catch {
                    $attempt++
                    if ($attempt -ge 3) { throw "Part $partNum failed after 3 attempts: $_" }
                    $backoff = [Math]::Pow(2, $attempt)
                    Write-Host "  Part $partNum failed (attempt $attempt), retrying in ${backoff}s..."
                    Start-Sleep -Seconds $backoff
                }
            }
        }
        finally {
            $client.Dispose()
        }
    }

    $parts = $parts | Sort-Object PartNumber

    $xml = "<CompleteMultipartUpload>"
    foreach ($p in $parts) {
        $xml += "<Part><PartNumber>$($p.PartNumber)</PartNumber><ETag>$($p.ETag)</ETag></Part>"
    }
    $xml += "</CompleteMultipartUpload>"

    Write-Output "Completing multipart upload..."
    try {
        Invoke-WebRequest -Uri $config.completeUrl -Method Post -Body $xml -ContentType "application/xml" -UseBasicParsing | Out-Null
    }
    catch {
        Write-Output "Complete failed, aborting multipart upload..."
        try {
            Invoke-WebRequest -Uri $config.abortUrl -Method Delete -UseBasicParsing | Out-Null
        }
        catch {
            Write-Warning "Abort request failed: $_"
        }
        throw
    }

    $elapsed = (Get-Date) - $startTime
    Write-Output "Multi-part upload complete in $($elapsed.TotalSeconds.ToString('F2'))s ($partCount parts, $concurrency concurrent)"
}
