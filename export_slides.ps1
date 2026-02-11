# export_slides.ps1 - Export PPTX slides as 1920x1080 PNGs using PowerPoint COM
#
# For each Section PPTX (English and Spanish), exports all slides as PNG images.
# Saves to the corresponding _work directory under the Videos folder.
#
# Usage: powershell -File export_slides.ps1
#   Optional: powershell -File export_slides.ps1 -Module 3
#             (process only Module 3)

param(
    [int]$Module = 0  # 0 = all modules
)

$ErrorActionPreference = 'Stop'
$base = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents'

# Module folder names
$modules = @{
    1 = 'Module 1 - Welcome and Culture'
    2 = 'Module 2 - Hiring Benefits and Supervisor Policy'
    3 = 'Module 3 - Supervisor Expectations and Job Rules'
    4 = 'Module 4 - Leadership'
    5 = 'Module 5 - Safety Leadership'
    6 = 'Module 6 - Accident Investigation'
    7 = 'Module 7 - Company-Owned Vehicles'
}

function Export-SlidesToPNG {
    param(
        [string]$PptxPath,
        [string]$OutputDir,
        [object]$PowerPoint
    )

    if (-not (Test-Path $PptxPath)) {
        Write-Warning "PPTX not found: $PptxPath"
        return $false
    }

    # Create output directory
    if (-not (Test-Path $OutputDir)) {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    }

    Write-Host "  Opening: $(Split-Path $PptxPath -Leaf)"
    # Open(FileName, ReadOnly=-1(msoTrue), Untitled=0(msoFalse), WithWindow=0(msoFalse))
    $pres = $PowerPoint.Presentations.Open($PptxPath, -1, 0, 0)

    try {
        $slideCount = $pres.Slides.Count
        Write-Host "  Exporting $slideCount slides to: $OutputDir"

        for ($i = 1; $i -le $slideCount; $i++) {
            $slide = $pres.Slides.Item($i)
            $filename = "slide_{0:D2}.png" -f $i
            $fullPath = Join-Path $OutputDir $filename
            $slide.Export($fullPath, "PNG", 1920, 1080)
        }

        Write-Host "  Exported $slideCount slides"
        return $true
    }
    finally {
        $pres.Close()
    }
}

# Start PowerPoint
Write-Host "Starting PowerPoint COM..."
$pp = New-Object -ComObject PowerPoint.Application
# Keep it hidden (msoFalse = 0)
# Note: PowerPoint.Application doesn't have a Visible property that hides it completely
# but opening presentations with msoFalse for the Window parameter keeps them hidden

try {
    # Determine which modules to process
    if ($Module -gt 0) {
        $moduleNums = @($Module)
    } else {
        $moduleNums = 1..7
    }

    foreach ($num in $moduleNums) {
        $moduleName = $modules[$num]
        $moduleDir = Join-Path $base $moduleName

        Write-Host ""
        Write-Host ("=" * 60)
        Write-Host "Module $num - $moduleName"
        Write-Host ("=" * 60)

        for ($section = 1; $section -le 3; $section++) {
            $part = $section  # Section N maps to Part N

            # Paths
            $pptxEn = Join-Path $moduleDir "PowerPoints\Module $num Section $section.pptx"
            $pptxEs = Join-Path $moduleDir "PowerPoints\Module $num Section ${section}_es.pptx"
            $workDir = Join-Path $moduleDir "Videos\Module $num Part ${part}_work"
            $slidesEnDir = Join-Path $workDir "slides_en"
            $slidesEsDir = Join-Path $workDir "slides_es"

            Write-Host ""
            Write-Host "--- Section $section / Part $part ---"

            # Check if work dir exists (from previous audio pipeline)
            if (-not (Test-Path $workDir)) {
                Write-Host "  Creating work dir: $workDir"
                New-Item -ItemType Directory -Path $workDir -Force | Out-Null
            }

            # Check if already exported
            $enDone = (Test-Path $slidesEnDir) -and ((Get-ChildItem $slidesEnDir -Filter '*.png' -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)
            $esDone = (Test-Path $slidesEsDir) -and ((Get-ChildItem $slidesEsDir -Filter '*.png' -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0)

            # Export English slides
            if ($enDone) {
                $count = (Get-ChildItem $slidesEnDir -Filter '*.png').Count
                Write-Host "  [SKIP] English slides already exported ($count slides)"
            } else {
                Write-Host "  Exporting English slides..."
                $result = Export-SlidesToPNG -PptxPath $pptxEn -OutputDir $slidesEnDir -PowerPoint $pp
                if (-not $result) {
                    Write-Warning "  Failed to export English slides for Section $section"
                }
            }

            # Export Spanish slides
            if ($esDone) {
                $count = (Get-ChildItem $slidesEsDir -Filter '*.png').Count
                Write-Host "  [SKIP] Spanish slides already exported ($count slides)"
            } else {
                if (Test-Path $pptxEs) {
                    Write-Host "  Exporting Spanish slides..."
                    $result = Export-SlidesToPNG -PptxPath $pptxEs -OutputDir $slidesEsDir -PowerPoint $pp
                    if (-not $result) {
                        Write-Warning "  Failed to export Spanish slides for Section $section"
                    }
                } else {
                    Write-Warning "  Spanish PPTX not found: $pptxEs"
                    Write-Warning "  Run translate_pptx.py first!"
                }
            }
        }
    }

    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host "EXPORT COMPLETE"
    Write-Host ("=" * 60)

    # Summary
    Write-Host ""
    Write-Host "Summary:"
    foreach ($num in $moduleNums) {
        $moduleName = $modules[$num]
        $moduleDir = Join-Path $base $moduleName
        for ($section = 1; $section -le 3; $section++) {
            $workDir = Join-Path $moduleDir "Videos\Module $num Part ${section}_work"
            $enCount = 0
            $esCount = 0
            $slidesEnDir = Join-Path $workDir "slides_en"
            $slidesEsDir = Join-Path $workDir "slides_es"
            if (Test-Path $slidesEnDir) {
                $enCount = (Get-ChildItem $slidesEnDir -Filter '*.png' -ErrorAction SilentlyContinue | Measure-Object).Count
            }
            if (Test-Path $slidesEsDir) {
                $esCount = (Get-ChildItem $slidesEsDir -Filter '*.png' -ErrorAction SilentlyContinue | Measure-Object).Count
            }
            $status = if ($enCount -gt 0 -and $esCount -gt 0) { "[OK]  " } else { "[MISS]" }
            Write-Host "  $status Module $num Part $section - EN: $enCount slides, ES: $esCount slides"
        }
    }
}
finally {
    Write-Host ""
    Write-Host "Closing PowerPoint..."
    $pp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
