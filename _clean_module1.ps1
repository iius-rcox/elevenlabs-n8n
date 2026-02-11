$base = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\Videos'
foreach ($part in 1..3) {
    $work = Join-Path $base "Module 1 Part ${part}_work"
    $slidesEs = Join-Path $work 'slides_es'
    $assembly = Join-Path $work 'slide_assembly'
    if (Test-Path $slidesEs) {
        Remove-Item $slidesEs -Recurse -Force
        Write-Output "Deleted: $slidesEs"
    }
    if (Test-Path $assembly) {
        Remove-Item $assembly -Recurse -Force
        Write-Output "Deleted: $assembly"
    }
}
