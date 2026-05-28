' Stock Dashboard - morning recommendation, weekday 07:30 KST (Task Scheduler)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\stock-dashboard"
sh.Run "cmd /c py scripts\daily_recommend.py --session morning > logs\morning_%date:~0,4%-%date:~5,2%-%date:~8,2%.log 2>&1", 0, False
