' 🌙 evening 추천 — 평일 21:00 KST 작업 스케줄러용
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\stock-dashboard"
sh.Run "cmd /c py scripts\daily_recommend.py --session evening > logs\evening_%date:~0,4%-%date:~5,2%-%date:~8,2%.log 2>&1", 0, False
