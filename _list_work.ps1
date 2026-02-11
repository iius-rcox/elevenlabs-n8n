$workDir = 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents\Module 1 - Welcome and Culture\Videos\Module 1 Part 1_work'
Get-ChildItem $workDir -File | ForEach-Object { Write-Output $_.Name }
