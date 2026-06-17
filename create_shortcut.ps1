$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Start Helix.lnk")
$Shortcut.TargetPath = "C:\Users\User\appsbyG\Jarvis\start_helix.bat"
$Shortcut.WorkingDirectory = "C:\Users\User\appsbyG\Jarvis"
$Shortcut.Description = "Start Helix AI Assistant"
$Shortcut.IconLocation = "C:\Users\User\appsbyG\Jarvis\frontend\src-tauri\icons\icon.ico"
$Shortcut.WindowStyle = 7
$Shortcut.Save()
Write-Host "Shortcut created on Desktop: 'Start Helix'"
