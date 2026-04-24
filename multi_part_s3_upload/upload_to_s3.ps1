param(
    [Parameter(Mandatory=$true)]
    [string]$PresignedUrl,

    [Parameter(Mandatory=$true)]
    [string]$FilePath
)

if (-not (Test-Path $FilePath)) {
    Write-Error "File not found: $FilePath"
    exit 1
}

$fileInfo = Get-Item $FilePath
$fileSize = $fileInfo.Length

Write-Output "File:     $FilePath"
Write-Output "Size:     $fileSize bytes"
Write-Output "Uploading to S3..."

$headers = @{
    "x-amz-tagging" = "docType=real-time"
    "Content-Length" = $fileSize
}

$startTime = Get-Date
Invoke-WebRequest -Uri $PresignedUrl -Method Put -Headers $headers -InFile $FilePath -UseBasicParsing
$elapsed = (Get-Date) - $startTime

Write-Output "Upload complete in $($elapsed.TotalSeconds.ToString('F2'))s"
