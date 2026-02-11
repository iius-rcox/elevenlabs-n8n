$base = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents'
$files = Get-ChildItem $base -Recurse -Filter '*_es.pptx'
Write-Output "Deleting $($files.Count) _es.pptx files:"
foreach ($f in $files) {
    Write-Output "  $($f.Name)"
    Remove-Item $f.FullName -Force
}
Write-Output "Done."
