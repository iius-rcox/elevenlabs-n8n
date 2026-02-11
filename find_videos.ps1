Get-ChildItem 'c:\Users\rcox\INSULATIONS, INC\Supervisory Training - Documents' -File |
  Where-Object { $_.Name -match 'Module \d+ Part' } |
  ForEach-Object { $_.Name }
