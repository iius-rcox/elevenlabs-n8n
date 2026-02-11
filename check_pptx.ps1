try {
    $pp = New-Object -ComObject PowerPoint.Application
    Write-Output "PowerPoint COM available"
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
} catch {
    Write-Output "PowerPoint COM not available: $($_.Exception.Message)"
}
