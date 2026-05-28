' 📸 보유/관심 종목 자동 스냅샷 — 평일 21:00 KST 작업 스케줄러용
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\stock-dashboard"
sh.Run "cmd /c py scripts\daily_snapshot.py > logs\snapshot_%date:~0,4%-%date:~5,2%-%date:~8,2%.log 2>&1", 0, False
