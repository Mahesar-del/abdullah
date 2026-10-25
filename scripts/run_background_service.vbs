Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get project root directory (parent of scripts/)
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptDir)

' Set working directory to project root
WshShell.CurrentDirectory = projectRoot

' Launch Django Server with Background Auto-Scanner & Evaluator completely hidden (window style 0 = hidden)
cmd = "cmd.exe /c python manage.py runserver 0.0.0.0:8000 --noreload > """ & projectRoot & "\tradesense_service.log"" 2>&1"
WshShell.Run cmd, 0, False

WScript.Echo "TradeSense Pro background service started successfully on port 8000! Check tradesense_service.log for logs."
