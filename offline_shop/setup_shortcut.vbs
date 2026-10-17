Option Explicit
Dim shell, fs, folder, shortcut, desktop
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
desktop = shell.SpecialFolders("Desktop")
Set shortcut = shell.CreateShortcut(desktop & "\Family Shop.lnk")
shortcut.TargetPath = folder & "\start_shop.bat"
shortcut.WorkingDirectory = folder
shortcut.Description = "Family Shop - offline stock and accounts"
shortcut.Save
MsgBox "Family Shop shortcut created on your desktop. Keep this app folder in place.", 64, "Family Shop"
