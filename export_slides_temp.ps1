$ErrorActionPreference = "Stop"

$sections = @(
    @{
        pptx = "c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\PowerPoints\Module 1 Section 2_es.pptx"
        out  = "c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\PowerPoints\Module 1 Section 2_es_work\slides"
    },
    @{
        pptx = "c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\PowerPoints\Module 1 Section 3_es.pptx"
        out  = "c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\PowerPoints\Module 1 Section 3_es_work\slides"
    }
)

$pp = $null
try {
    $pp = New-Object -ComObject PowerPoint.Application
    foreach ($sec in $sections) {
        $pptxPath = $sec.pptx
        $outDir = $sec.out
        if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
        Write-Host "Opening $pptxPath..."
        $pres = $pp.Presentations.Open($pptxPath, -1, 0, 0)
        try {
            $count = $pres.Slides.Count
            Write-Host "  $count slides"
            for ($i = 1; $i -le $count; $i++) {
                $slide = $pres.Slides.Item($i)
                $fileName = "slide_{0:D2}.png" -f $i
                $fullPath = Join-Path $outDir $fileName
                $slide.Export($fullPath, "PNG", 1920, 1080)
                Write-Host "  Exported: $fileName"
            }
            Write-Host "Done: $count slides exported"
        } finally {
            $pres.Close()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pres) | Out-Null
        }
    }
} finally {
    if ($pp) {
        $pp.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
    }
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
