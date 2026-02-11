$workDir = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\Videos\Module 1 Part 1_work'
Get-ChildItem $workDir -Recurse | ForEach-Object {
    $rel = $_.FullName.Substring($workDir.Length + 1)
    Write-Output $rel
}
