$files = Get-ChildItem 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents' -Recurse -Filter '*_es.pptx'
foreach ($f in $files | Sort-Object Name) {
    $sizeKB = [math]::Round($f.Length / 1KB)
    Write-Output "$($f.Name)  ($sizeKB KB)"
}
Write-Output ""
Write-Output "Total: $($files.Count) files"
