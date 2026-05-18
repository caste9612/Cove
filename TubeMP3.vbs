' Lancia app.py senza finestra terminale visibile usando pythonw del venv.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = base & "\.venv\Scripts\pythonw.exe"
app = base & "\app.py"
If Not fso.FileExists(pyw) Then
  MsgBox "Manca .venv\Scripts\pythonw.exe. Esegui prima setup.bat.", 16, "TubeMP3"
  WScript.Quit 1
End If
sh.CurrentDirectory = base
sh.Run """" & pyw & """ """ & app & """", 0, False
