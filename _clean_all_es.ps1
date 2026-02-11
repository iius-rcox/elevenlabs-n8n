$base = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents'

# Delete all _es.pptx files
$pptx = Get-ChildItem $base -Recurse -Filter '*_es.pptx'
Write-Output "Deleting $($pptx.Count) _es.pptx files..."
foreach ($f in $pptx) {
    Remove-Item $f.FullName -Force
    Write-Output "  $($f.FullName)"
}

# Delete all _es.mp4 files
$mp4 = Get-ChildItem $base -Recurse -Filter '*_es.mp4'
Write-Output "`nDeleting $($mp4.Count) _es.mp4 files..."
foreach ($f in $mp4) {
    Remove-Item $f.FullName -Force
    Write-Output "  $($f.FullName)"
}

# Delete all slides_es folders
$slidesEs = Get-ChildItem $base -Recurse -Directory -Filter 'slides_es'
Write-Output "`nDeleting $($slidesEs.Count) slides_es folders..."
foreach ($d in $slidesEs) {
    Remove-Item $d.FullName -Recurse -Force
    Write-Output "  $($d.FullName)"
}

# Delete all slide_assembly folders
$assembly = Get-ChildItem $base -Recurse -Directory -Filter 'slide_assembly'
Write-Output "`nDeleting $($assembly.Count) slide_assembly folders..."
foreach ($d in $assembly) {
    Remove-Item $d.FullName -Recurse -Force
    Write-Output "  $($d.FullName)"
}

# Delete extracted spanish_audio.aac files
$aac = Get-ChildItem $base -Recurse -Filter 'spanish_audio.aac'
Write-Output "`nDeleting $($aac.Count) spanish_audio.aac files..."
foreach ($f in $aac) {
    Remove-Item $f.FullName -Force
    Write-Output "  $($f.FullName)"
}

Write-Output "`nDone. Clean slate."
