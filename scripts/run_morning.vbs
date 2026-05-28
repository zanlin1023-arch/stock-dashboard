' 🌅 morning 추천 — 평일 07:30 KST 작업 스케줄러용
' 콘솔 창 안 보이게 hidden 실행 + 로그 파일에 결과 기록
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\stock-dashboard"
sh.Run "cmd /c py scripts\daily_recommend.py --session morning > logs\morning_%date:~0,4%-%date:~5,2%-%date:~8,2%.log 2>&1", 0, False
