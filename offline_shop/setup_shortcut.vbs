Option Explicit
Dim shell, fs, folder, shortcut, desktop, target, icon, quiet, existingOnly, pythonPath
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
desktop = shell.SpecialFolders("Desktop")
quiet = False
existingOnly = False
pythonPath = ""
If WScript.Arguments.Count > 0 Then pythonPath = WScript.Arguments(0)
If WScript.Arguments.Count > 1 Then quiet = (WScript.Arguments(1) = "quiet")
If WScript.Arguments.Count > 2 Then existingOnly = (WScript.Arguments(2) = "existing")
target = desktop & "\Mutowei Investments.lnk"
If existingOnly And Not fs.FileExists(target) And Not fs.FileExists(desktop & "\Family Shop.lnk") Then WScript.Quit 0
If pythonPath = "" Then
  On Error Resume Next
  pythonPath = shell.Exec("py -3 -c ""import sys; print(sys.executable)""").StdOut.ReadAll
  On Error GoTo 0
  pythonPath = Trim(pythonPath)
End If
If pythonPath <> "" Then
  pythonPath = fs.BuildPath(fs.GetParentFolderName(pythonPath), "pythonw.exe")
End If
Set shortcut = shell.CreateShortcut(target)
If pythonPath <> "" And fs.FileExists(pythonPath) Then
  shortcut.TargetPath = pythonPath
  shortcut.Arguments = Chr(34) & folder & "\app.py" & Chr(34)
Else
  shortcut.TargetPath = folder & "\start_shop.bat"
  shortcut.Arguments = ""
End If
shortcut.WorkingDirectory = folder
shortcut.Description = "Mutowei Investments - WhatKind?"
icon = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\FamilyShop\assets\mutowei-v1.ico"
If fs.FileExists(icon) Then shortcut.IconLocation = icon & ",0"
shortcut.Save
If fs.FileExists(desktop & "\Family Shop.lnk") Then fs.DeleteFile desktop & "\Family Shop.lnk"
WScript.Echo target
If Not quiet Then MsgBox "Mutowei Investments desktop shortcut updated. Keep this app folder in place.", 64, "Mutowei Investments"
