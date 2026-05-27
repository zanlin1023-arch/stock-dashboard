"""다국어 (i18n) — 한국어 / 중국어 번체.

사용: t("key") → 현재 언어 텍스트 반환.
키 없으면 한국어 fallback.
"""
from __future__ import annotations

import streamlit as st


# ──────────────────────────────────────────
# 지원 언어
# ──────────────────────────────────────────
SUPPORTED_LANGS = {
    "ko": "한국어",
    "zh-TW": "繁體中文",
}

DEFAULT_LANG = "ko"


# ──────────────────────────────────────────
# 번역 사전
# ──────────────────────────────────────────
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ════════════════════════════════
    # 공통 (사이드바 / 네비)
    # ════════════════════════════════
    "menu": {"ko": "🗺 메뉴", "zh-TW": "🗺 選單"},
    "nav_home": {"ko": "🏠 홈 / 종목 분석", "zh-TW": "🏠 首頁 / 個股分析"},
    "nav_dashboard": {"ko": "📊 대시보드", "zh-TW": "📊 儀表板"},
    "nav_analyze": {"ko": "🔬 종목 분석", "zh-TW": "🔬 個股分析"},
    "nav_recommend": {"ko": "🎯 추천 종목", "zh-TW": "🎯 推薦個股"},
    "nav_holdings": {"ko": "💼 보유 종목", "zh-TW": "💼 持股"},
    "nav_watchlist": {"ko": "⭐ 관심 종목", "zh-TW": "⭐ 自選股"},
    "nav_history": {"ko": "📜 분석 히스토리", "zh-TW": "📜 分析歷史"},
    # 추천 종목 sub-nav (세션별)
    "nav_rec_morning": {"ko": "🌅 morning (장 시작 전)", "zh-TW": "🌅 morning (開盤前)"},
    "nav_rec_intraday": {"ko": "☀️ intraday (장 중)", "zh-TW": "☀️ intraday (盤中)"},
    "nav_rec_evening": {"ko": "🌙 evening (장 마감 후)", "zh-TW": "🌙 evening (收盤後)"},
    # 분석 히스토리 sub-nav (카테고리별)
    "nav_hist_auto_hold": {"ko": "💼 자동·보유 일일", "zh-TW": "💼 自動·持股每日"},
    "nav_hist_auto_watch": {"ko": "⭐ 자동·관심 일일", "zh-TW": "⭐ 自動·自選每日"},
    "nav_hist_manual": {"ko": "👤 수동 분석", "zh-TW": "👤 手動分析"},
    "btn_home": {"ko": "🏠 홈", "zh-TW": "🏠 首頁"},
    "btn_back": {"ko": "← 뒤로", "zh-TW": "← 返回"},
    "btn_recommend_short": {"ko": "🎯 추천", "zh-TW": "🎯 推薦"},
    "btn_holdings_short": {"ko": "💼 보유", "zh-TW": "💼 持股"},
    "btn_watchlist_short": {"ko": "⭐ 관심", "zh-TW": "⭐ 自選"},

    # ════════════════════════════════
    # 인증
    # ════════════════════════════════
    "auth_title": {"ko": "🔒 분석 대시보드", "zh-TW": "🔒 分析儀表板"},
    "auth_prompt": {"ko": "비밀번호를 입력하세요.", "zh-TW": "請輸入密碼。"},
    "auth_password": {"ko": "비밀번호", "zh-TW": "密碼"},
    "auth_login": {"ko": "로그인", "zh-TW": "登入"},
    "auth_no_pw": {"ko": "⚠️ 앱 비밀번호가 설정되지 않았습니다.", "zh-TW": "⚠️ 應用密碼未設定。"},
    "auth_wrong": {"ko": "❌ 비밀번호가 틀렸습니다.", "zh-TW": "❌ 密碼錯誤。"},

    # ════════════════════════════════
    # 홈 / 종목 분석
    # ════════════════════════════════
    "home_title": {"ko": "📊 분석 대시보드", "zh-TW": "📊 分析儀表板"},
    "home_subtitle": {
        "ko": "KOSPI/KOSDAQ — 일목균형표 + 백테스팅 + 펀더멘털 종합 분석",
        "zh-TW": "KOSPI/KOSDAQ — 一目均衡表 + 回測 + 基本面綜合分析",
    },
    "analyze_page_title": {"ko": "종목 분석", "zh-TW": "個股分析"},
    "dashboard_title": {"ko": "포트폴리오 대시보드", "zh-TW": "投資組合儀表板"},
    "dashboard_subtitle": {
        "ko": "보유 종목 종합 분석 + 자동 시그널 감지",
        "zh-TW": "持股綜合分析 + 自動訊號偵測",
    },
    "dashboard_no_holdings": {
        "ko": "보유 종목이 없습니다.",
        "zh-TW": "尚無持股。",
    },
    "dashboard_loading": {
        "ko": "🔍 보유 종목 분석 중 (실시간 시세 + 일목 분석)...",
        "zh-TW": "🔍 持股分析中 (即時報價 + 一目分析)...",
    },
    "best_worst": {"ko": "베스트 / 워스트", "zh-TW": "最佳 / 最差"},
    "best": {"ko": "베스트", "zh-TW": "最佳表現"},
    "worst": {"ko": "워스트", "zh-TW": "最差表現"},
    "portfolio_weight": {"ko": "종목별 비중", "zh-TW": "個股權重"},
    "per_stock_returns": {"ko": "종목별 수익률", "zh-TW": "個股報酬率"},
    "alerts": {"ko": "주의 종목 / 시그널", "zh-TW": "注意個股 / 訊號"},
    "no_alerts": {"ko": "✅ 현재 특이 시그널 없음 — 안정", "zh-TW": "✅ 目前無異常訊號 — 穩定"},
    "alert_overbought": {"ko": "과매수 — 단기 차익실현 검토", "zh-TW": "超買 — 考慮短期獲利了結"},
    "alert_oversold": {"ko": "과매도 — 반등 가능성", "zh-TW": "超賣 — 反彈可能"},
    "alert_bearish_full": {"ko": "구름 아래 + TK 데드 — 약세 추세", "zh-TW": "雲下 + TK死叉 — 弱勢趨勢"},
    "alert_review_stop": {"ko": "손절 검토 필요", "zh-TW": "考慮停損"},
    "alert_take_profit": {"ko": "분할 익절 검토", "zh-TW": "考慮分批停利"},
    "holdings_summary": {"ko": "보유 종목 요약", "zh-TW": "持股摘要"},
    "dashboard_footer_hint": {
        "ko": "캐시 5분 · 보유 추가/수정은 💼 持股 페이지에서",
        "zh-TW": "快取5分鐘 · 持股新增/修改請至 💼 持股頁面",
    },
    "search_header": {"ko": "🔍 종목 검색", "zh-TW": "🔍 個股搜尋"},
    "search_input": {"ko": "종목명 또는 종목코드", "zh-TW": "股票名稱或代碼"},
    "search_placeholder": {
        "ko": "예: 삼성전자 또는 005930",
        "zh-TW": "例: 三星電子 或 005930",
    },
    "analyze_period": {"ko": "분석 기간 (일)", "zh-TW": "分析期間 (天)"},
    "save_to_db": {"ko": "📥 결과를 DB에 저장", "zh-TW": "📥 將結果儲存至資料庫"},
    "btn_analyze": {"ko": "🚀 분석 시작", "zh-TW": "🚀 開始分析"},
    "db_connected": {"ko": "✅ DB 연결됨", "zh-TW": "✅ 資料庫已連線"},
    "db_disconnected": {"ko": "⚠️ DB 미연결 (분석만 가능)", "zh-TW": "⚠️ 資料庫未連線 (僅可分析)"},
    "version": {"ko": "버전", "zh-TW": "版本"},

    # 분석 결과
    "analyzing": {"ko": "분석 중...", "zh-TW": "分析中..."},
    "analysis_complete": {"ko": "✅ 분석 완료", "zh-TW": "✅ 分析完成"},
    "analysis_failed": {"ko": "❌ 분석 실패", "zh-TW": "❌ 分析失敗"},
    "current_price": {"ko": "현재가", "zh-TW": "目前股價"},
    "period_return": {"ko": "수익률", "zh-TW": "報酬率"},
    "volume": {"ko": "거래량", "zh-TW": "成交量"},
    "rsi_overbought": {"ko": "🔴 과매수", "zh-TW": "🔴 超買"},
    "rsi_oversold": {"ko": "🟢 과매도", "zh-TW": "🟢 超賣"},
    "rsi_neutral": {"ko": "🟡 중립", "zh-TW": "🟡 中立"},

    # 일목 의사결정
    "ichimoku_decision": {"ko": "📌 일목균형표 종합 판단", "zh-TW": "📌 一目均衡表綜合判斷"},
    "position": {"ko": "위치", "zh-TW": "位置"},
    "tk_state": {"ko": "TK 상태", "zh-TW": "TK 狀態"},
    "chikou": {"ko": "후행스팬", "zh-TW": "遲行線"},
    "cloud_above": {"ko": "구름 위 (강세)", "zh-TW": "雲層上方 (強勢)"},
    "cloud_below": {"ko": "구름 아래 (약세)", "zh-TW": "雲層下方 (弱勢)"},
    "cloud_inside": {"ko": "구름 안 (횡보)", "zh-TW": "雲層內 (盤整)"},
    "tk_bull": {"ko": "전환선 > 기준선 ✅", "zh-TW": "轉換線 > 基準線 ✅"},
    "tk_bear": {"ko": "전환선 < 기준선 ⚠️", "zh-TW": "轉換線 < 基準線 ⚠️"},
    "chikou_above": {"ko": "26일전 위 ✅", "zh-TW": "26日前之上 ✅"},
    "chikou_below": {"ko": "26일전 아래 ⚠️", "zh-TW": "26日前之下 ⚠️"},

    # 가격 가이드
    "price_guide": {"ko": "🎯 가격 가이드", "zh-TW": "🎯 價格指引"},
    "target_v": {"ko": "1차 익절", "zh-TW": "第一停利點"},
    "target_n": {"ko": "표준 목표", "zh-TW": "標準目標價"},
    "target_e": {"ko": "강세 목표", "zh-TW": "強勢目標價"},
    "stop_loss": {"ko": "🛡 손절", "zh-TW": "🛡 停損"},

    # 차트
    "ichimoku_chart": {"ko": "📈 일목균형표 차트", "zh-TW": "📈 一目均衡表圖"},
    "chart_failed": {"ko": "차트 생성 실패", "zh-TW": "圖表生成失敗"},
    "signals": {"ko": "🚨 시그널", "zh-TW": "🚨 訊號"},
    "moving_averages": {"ko": "📊 이동평균선 상세", "zh-TW": "📊 移動平均線詳細"},
    "ichimoku_wave": {"ko": "🌊 일목 파동 (A → B → C)", "zh-TW": "🌊 一目波動 (A → B → C)"},
    "add_to_watch": {"ko": "⭐ 관심 종목 추가", "zh-TW": "⭐ 加入自選股"},
    "add_to_watch_done": {"ko": "✅ 관심 종목에 추가됨", "zh-TW": "✅ 已加入自選股"},
    "db_save_done": {"ko": "📥 DB 저장 완료", "zh-TW": "📥 已儲存至資料庫"},

    # 첫 화면 (분석 전)
    "intro_prompt": {
        "ko": "👈 사이드바에서 종목을 입력하고 **분석 시작** 버튼을 눌러주세요.",
        "zh-TW": "👈 在側邊欄輸入股票後點擊 **開始分析**。",
    },
    "intro_features": {
        "ko": "### 🎯 이 대시보드가 제공하는 것",
        "zh-TW": "### 🎯 本儀表板提供",
    },
    "disclaimer": {
        "ko": "⚠️ 본 분석은 참고용입니다. 투자 결정은 본인 책임입니다.",
        "zh-TW": "⚠️ 本分析僅供參考。投資決定請自行負責。",
    },

    # ════════════════════════════════
    # 🎯 추천 종목 페이지
    # ════════════════════════════════
    "recommend_title": {"ko": "🎯 신규 종목 추천", "zh-TW": "🎯 新個股推薦"},
    "recommend_morning": {"ko": "🌅 장 시작 전", "zh-TW": "🌅 開盤前"},
    "recommend_intraday": {"ko": "☀️ 장 중", "zh-TW": "☀️ 盤中"},
    "recommend_evening": {"ko": "🌙 장 마감 후", "zh-TW": "🌙 收盤後"},
    "current_mode": {"ko": "자동 추천 모드", "zh-TW": "自動推薦模式"},
    "tier_n": {"ko": "Tier별 추천 수", "zh-TW": "每階層推薦數"},
    "exclude_holdings": {"ko": "보유 종목 제외", "zh-TW": "排除持股"},
    "exclude_watchlist": {"ko": "관심 종목 제외", "zh-TW": "排除自選股"},
    "refresh_analysis": {"ko": "🔄 새로 분석", "zh-TW": "🔄 重新分析"},
    "cache_hint": {"ko": "⏱ 캐시 10분 · 새로 분석 시 30초~1분", "zh-TW": "⏱ 快取10分鐘 · 重新分析需30秒~1分鐘"},
    "tier_large": {"ko": "🏛 대형주", "zh-TW": "🏛 大型股"},
    "tier_mid": {"ko": "🏢 중형주", "zh-TW": "🏢 中型股"},
    "tier_small": {"ko": "🏠 소형주", "zh-TW": "🏠 小型股"},
    "tier_large_desc": {"ko": "시총 5조원 이상", "zh-TW": "市值5兆韓元以上"},
    "tier_mid_desc": {"ko": "5천억 ~ 5조원", "zh-TW": "5,000億 ~ 5兆"},
    "tier_small_desc": {"ko": "1천억 ~ 5천억원", "zh-TW": "1,000億 ~ 5,000億"},
    "score": {"ko": "추천 점수", "zh-TW": "推薦分數"},
    "market_cap": {"ko": "시가총액", "zh-TW": "市值"},
    "foreign_5d": {"ko": "외인 5일", "zh-TW": "外資5日"},
    "inst_5d": {"ko": "기관 5일", "zh-TW": "投信5日"},
    "detail_analysis": {"ko": "🔬 상세 분석", "zh-TW": "🔬 詳細分析"},
    "loading_recommend": {
        "ko": "🔍 시장 데이터 수집 + 외인/기관 수급 계산 + 점수화 (30초~1분 소요)...",
        "zh-TW": "🔍 收集市場數據 + 外資/投信買賣 + 評分 (約30秒~1分鐘)...",
    },
    "no_recommend": {"ko": "⚠️ 추천 종목이 없습니다.", "zh-TW": "⚠️ 沒有推薦個股。"},
    "current_kst": {"ko": "현재 한국 시각", "zh-TW": "目前韓國時間"},
    "no_saved_recs": {"ko": "저장된 추천 없음", "zh-TW": "尚無已儲存的推薦"},
    "no_saved_recs_hint": {
        "ko": "아직 저장된 추천이 없습니다. '🚀 지금 분석 실행' 버튼을 누르거나, 매일 16:30 KST 자동 실행을 기다리세요.",
        "zh-TW": "尚無已儲存的推薦。請點擊 '🚀 立即分析' 按鈕,或等待每日 16:30 KST 自動執行。",
    },
    "no_recs_for_date": {"ko": "저장된 추천 없음", "zh-TW": "此日期無已儲存的推薦"},
    "filter_date": {"ko": "📅 조회 날짜", "zh-TW": "📅 查詢日期"},
    "filter_latest": {"ko": "📅 최신", "zh-TW": "📅 最新"},
    "filter_session": {"ko": "⏰ 세션", "zh-TW": "⏰ 時段"},
    "btn_run_now": {"ko": "🚀 지금 분석 실행", "zh-TW": "🚀 立即分析"},
    "btn_7d_trend": {"ko": "🔍 7일 추이 분석", "zh-TW": "🔍 7日趨勢分析"},
    "rec_date": {"ko": "📅 추천 일자", "zh-TW": "📅 推薦日期"},
    "rec_total": {"ko": "📊 총 추천", "zh-TW": "📊 推薦總數"},
    "rec_session_count": {"ko": "⏰ 세션", "zh-TW": "⏰ 時段"},
    "rec_analyzed_at": {"ko": "🕐 분석 시각", "zh-TW": "🕐 分析時間"},
    "trend_title": {"ko": "📊 7일 추천 종목 추이", "zh-TW": "📊 7日推薦個股趨勢"},
    "trend_caption": {
        "ko": "최근 7일간 어떤 종목이 자주 추천됐는지 + 신규/탈락",
        "zh-TW": "最近7日內哪些個股被頻繁推薦 + 新增/移除",
    },
    "analysis_time": {"ko": "🕐 분석 시각", "zh-TW": "🕐 分析時間"},
    "running_analysis": {
        "ko": "🔍 추천 분석 중 (30초~6분)... 끝나면 DB에 저장됩니다.",
        "zh-TW": "🔍 推薦分析中 (30秒~6分鐘)... 完成後將儲存至資料庫。",
    },
    "save_done_template": {
        "ko": "✅ {n}건 저장 완료 — 페이지 새로고침",
        "zh-TW": "✅ 已儲存 {n} 筆 — 重新整理頁面",
    },
    "session_morning_label": {"ko": "장 시작 전", "zh-TW": "開盤前"},
    "session_intraday_label": {"ko": "장 중", "zh-TW": "盤中"},
    "session_evening_label": {"ko": "장 마감 후", "zh-TW": "收盤後"},

    # ════════════════════════════════
    # 💼 보유 종목 페이지
    # ════════════════════════════════
    "holdings_title": {"ko": "💼 보유 종목", "zh-TW": "💼 持股"},
    "holdings_add": {"ko": "➕ 보유 종목 추가", "zh-TW": "➕ 新增持股"},
    "avg_price": {"ko": "평단가 (원)", "zh-TW": "平均成本 (韓元)"},
    "quantity": {"ko": "수량", "zh-TW": "數量"},
    "purchase_date_unknown": {"ko": "매수일 모름 / 입력 안 함", "zh-TW": "不知道購買日期 / 不輸入"},
    "purchase_date": {"ko": "매수일 (선택)", "zh-TW": "購買日期 (選填)"},
    "note_optional": {"ko": "메모 (선택)", "zh-TW": "備註 (選填)"},
    "btn_register": {"ko": "💾 등록", "zh-TW": "💾 註冊"},
    "btn_autofill": {"ko": "🔮 자동 채우기", "zh-TW": "🔮 自動填寫"},
    "autofill_loading": {"ko": "종목 정보 수집 중...", "zh-TW": "收集個股資訊中..."},
    "holdings_empty": {"ko": "보유 종목이 없습니다. 위에서 추가하세요.", "zh-TW": "尚無持股。請從上方新增。"},
    "total_buy": {"ko": "총 매수금액", "zh-TW": "總購買金額"},
    "total_eval": {"ko": "총 평가금액", "zh-TW": "總評估金額"},
    "total_pnl": {"ko": "평가 손익", "zh-TW": "評估損益"},
    "pnl_pct": {"ko": "수익률", "zh-TW": "報酬率"},
    "holdings_list": {"ko": "📋 보유 목록", "zh-TW": "📋 持股清單"},
    "delete_stock": {"ko": "🗑 종목 삭제", "zh-TW": "🗑 刪除個股"},
    "delete_target": {"ko": "삭제할 종목 선택", "zh-TW": "選擇要刪除的個股"},
    "btn_delete": {"ko": "삭제", "zh-TW": "刪除"},
    "delete_done": {"ko": "✅ 삭제 완료", "zh-TW": "✅ 已刪除"},

    # ════════════════════════════════
    # ⭐ 관심 종목 페이지
    # ════════════════════════════════
    "watchlist_title": {"ko": "⭐ 관심 종목", "zh-TW": "⭐ 自選股"},
    "watchlist_add": {"ko": "➕ 관심 종목 추가", "zh-TW": "➕ 新增自選股"},
    "tags_optional": {"ko": "태그 (쉼표 구분, 선택)", "zh-TW": "標籤 (以逗號分隔, 選填)"},
    "watchlist_empty": {
        "ko": "관심 종목이 없습니다. 위에서 추가하거나 종목 분석 화면에서 ⭐ 버튼으로 추가하세요.",
        "zh-TW": "尚無自選股。請從上方新增或在分析頁面按 ⭐ 按鈕。",
    },
    "watchlist_list": {"ko": "📋 관심 목록", "zh-TW": "📋 自選股清單"},
    "quick_analyze": {"ko": "🔬 빠른 분석", "zh-TW": "🔬 快速分析"},
    "select_to_analyze": {"ko": "분석할 종목 선택", "zh-TW": "選擇要分析的個股"},
    "goto_analyze": {"ko": "🚀 분석 페이지로 이동", "zh-TW": "🚀 前往分析頁面"},

    # ════════════════════════════════
    # 📜 분석 히스토리 페이지
    # ════════════════════════════════
    "history_title": {"ko": "📜 분석 히스토리", "zh-TW": "📜 分析歷史"},
    "history_empty": {
        "ko": "저장된 분석 히스토리가 없습니다.",
        "zh-TW": "尚無已儲存的分析歷史。",
    },
    "filter_stock": {"ko": "📌 종목 필터", "zh-TW": "📌 個股篩選"},
    "filter_all": {"ko": "(전체)", "zh-TW": "(全部)"},
    "filter_snapshot": {"ko": "🔄 스냅샷 종류", "zh-TW": "🔄 快照類型"},
    "snapshot_all": {"ko": "전체", "zh-TW": "全部"},
    "snapshot_manual": {"ko": "수동 (manual)", "zh-TW": "手動 (manual)"},
    "snapshot_scheduled": {"ko": "자동 (scheduled)", "zh-TW": "自動 (scheduled)"},
    "type_auto": {"ko": "🤖 자동", "zh-TW": "🤖 自動"},
    "type_manual": {"ko": "👤 수동", "zh-TW": "👤 手動"},
    "total_count": {"ko": "총 분석 횟수", "zh-TW": "總分析次數"},
    "stock_count": {"ko": "분석한 종목 수", "zh-TW": "已分析個股數"},
    "buy_count": {"ko": "매수 판단", "zh-TW": "買入判斷"},
    "sell_count": {"ko": "매도 판단", "zh-TW": "賣出判斷"},

    # ════════════════════════════════
    # 신규 페이지 (캘린더 / 히트맵)
    # ════════════════════════════════
    "nav_calendar": {"ko": "📅 공시·경제 캘린더", "zh-TW": "📅 公示·經濟日曆"},
    "nav_heatmap": {"ko": "🌡️ 시장 히트맵", "zh-TW": "🌡️ 市場熱力圖"},

    # ════════════════════════════════
    # 분석 히스토리 카테고리 (사이드바 sub-nav)
    # ════════════════════════════════
    "hist_cat_auto": {"ko": "💼 자동 · 보유 일일", "zh-TW": "💼 自動·持股日報"},
    "hist_cat_watch": {"ko": "⭐ 자동 · 관심 일일", "zh-TW": "⭐ 自動·自選日報"},
    "hist_cat_manual": {"ko": "👤 수동 · 일회성", "zh-TW": "👤 手動·一次性"},
    "hist_watch_caption": {
        "ko": "📌 매일 평일 자동 분석된 **관심 종목 스냅샷** — 매수 진입 후보의 일자별 변화 추적",
        "zh-TW": "📌 每個工作日自動分析的**自選股快照** — 追蹤買入候選的日別變化",
    },
    "hist_watch_empty": {
        "ko": "💡 아직 관심 종목 자동 스냅샷이 없습니다.\n\n⭐ **관심 종목** 페이지에서 종목을 등록하면 다음 스케줄부터 자동 분석됩니다.",
        "zh-TW": "💡 尚無自選股自動快照。\n\n⭐ 在**自選股**頁面登錄個股後,從下次排程開始自動分析。",
    },
    "hist_watch_records_title": {"ko": "📊 관심 자동 스냅샷 기록", "zh-TW": "📊 自選自動快照記錄"},

    # ════════════════════════════════
    # 분석 히스토리 본문 (탭 안내 / 빈 상태 / 통계)
    # ════════════════════════════════
    "hist_auto_caption": {
        "ko": "📌 매일 평일 자동 분석된 **보유 종목 스냅샷** — 같은 종목의 일자별 변화 추적이 핵심",
        "zh-TW": "📌 每個工作日自動分析的**持股快照** — 重點是追蹤同一個股的日別變化",
    },
    "hist_manual_caption": {
        "ko": "📌 🔬 종목 분석 페이지 또는 💼 보유 등록 시 1회성으로 저장된 깊은 분석 — raw_data 펼침이 핵심",
        "zh-TW": "📌 在🔬個股分析頁面或💼持股登錄時一次性儲存的深度分析 — 重點是展開 raw_data",
    },
    "hist_auto_empty": {
        "ko": "💡 아직 자동 스냅샷이 없습니다. 매일 평일 자동 분석 (GitHub Actions cron) 결과가 누적됩니다.\n\n💼 **보유 종목** 페이지에서 종목을 등록하면 다음 스케줄부터 자동 분석됩니다.",
        "zh-TW": "💡 尚無自動快照。每個工作日自動分析 (GitHub Actions cron) 結果會累積。\n\n💼 在**持股**頁面登錄個股後,從下次排程開始自動分析。",
    },
    "hist_manual_empty": {
        "ko": "💡 수동 분석 기록이 없습니다. **🔬 종목 분석** 페이지에서 분석하면 누적됩니다.",
        "zh-TW": "💡 尚無手動分析記錄。在**🔬個股分析**頁面分析後即可累積。",
    },
    "hist_metric_snapshots": {"ko": "📦 누적 스냅샷", "zh-TW": "📦 累積快照"},
    "hist_metric_stocks": {"ko": "📊 분석 종목 수", "zh-TW": "📊 分析個股數"},
    "hist_metric_days": {"ko": "📅 누적 일수", "zh-TW": "📅 累積日數"},
    "hist_metric_total": {"ko": "📦 총 분석", "zh-TW": "📦 總分析數"},
    "hist_metric_buy": {"ko": "🟢 매수", "zh-TW": "🟢 買入"},
    "hist_metric_sell": {"ko": "🔴 매도", "zh-TW": "🔴 賣出"},
    "hist_auto_records_title": {"ko": "📊 자동 스냅샷 기록", "zh-TW": "📊 自動快照記錄"},
    "hist_manual_records_title": {"ko": "📊 수동 분석 기록", "zh-TW": "📊 手動分析記錄"},
    "hist_auto_detail_title": {"ko": "— 일자별 추이", "zh-TW": "— 日別趨勢"},
    "hist_manual_detail_title": {"ko": "— 일회성 분석 상세", "zh-TW": "— 一次性分析詳情"},

    # ════════════════════════════════
    # 추천 종목 신규 (세션 카드 + 섹터 비교)
    # ════════════════════════════════
    "rec_session_progress": {"ko": "📅 오늘 세션별 자동 분석 진행", "zh-TW": "📅 今日各時段自動分析進度"},
    "rec_session_morning_desc": {"ko": "장 시작 전", "zh-TW": "開盤前"},
    "rec_session_intraday_desc": {"ko": "장 중", "zh-TW": "盤中"},
    "rec_session_evening_desc": {"ko": "NXT 마감 후", "zh-TW": "NXT 收盤後"},
    "rec_session_done": {"ko": "✅ 분석 완료", "zh-TW": "✅ 分析完成"},
    "rec_session_pending": {"ko": "⏸ 미실행 (대기 중)", "zh-TW": "⏸ 未執行 (待機中)"},
    "rec_sector_compare": {"ko": "🏢 섹터 · 관련주 비교", "zh-TW": "🏢 產業·相關股比較"},

    # ════════════════════════════════
    # 추천 카드 — 라벨 / 단위 / 메시지
    # ════════════════════════════════
    "rec_card_price": {"ko": "현재가", "zh-TW": "現價"},
    "rec_card_score": {"ko": "추천 점수", "zh-TW": "推薦分數"},
    "rec_card_marketcap": {"ko": "시가총액", "zh-TW": "市值"},
    "rec_card_foreign5d": {"ko": "외인 5일", "zh-TW": "外資5日"},
    "rec_card_inst5d": {"ko": "기관 5일", "zh-TW": "機構5日"},
    "rec_card_detail": {"ko": "🔬 상세 분석", "zh-TW": "🔬 詳細分析"},
    "rec_card_theme": {"ko": "📂 테마/섹터", "zh-TW": "📂 主題/產業"},
    "rec_card_reasons": {"ko": "💡 추천 이유", "zh-TW": "💡 推薦理由"},
    "rec_card_no_theme": {"ko": "섹터 정보 없음", "zh-TW": "無產業資訊"},
    "rec_card_no_reasons": {"ko": "특이 시그널 없음", "zh-TW": "無特殊訊號"},
    "rec_unit_won": {"ko": "원", "zh-TW": "元"},
    "rec_unit_eok": {"ko": "억", "zh-TW": "億"},
    "rec_unit_count": {"ko": "건", "zh-TW": "筆"},
    "rec_no_saved_for_date": {"ko": "저장된 추천 없음", "zh-TW": "無已儲存推薦"},
    "rec_session_all": {"ko": "전체", "zh-TW": "全部"},
    "rec_time_hours_min_later": {"ko": "⏳ {h}시간 {m}분 후", "zh-TW": "⏳ {h}小時{m}分後"},
    "rec_time_min_later": {"ko": "⏳ {m}분 후", "zh-TW": "⏳ {m}分後"},
    "rec_intro_no_recs": {
        "ko": "💡 아직 저장된 추천이 없습니다. 매일 평일 다음 시각에 자동 분석됩니다:\n\n- 🌅 **08:00 KST** — 장 시작 전 (morning)\n- 🌙 **21:00 KST** — NXT 마감 후 (evening)",
        "zh-TW": "💡 尚無已儲存的推薦。每個工作日將於以下時間自動分析:\n\n- 🌅 **08:00 KST** — 開盤前 (morning)\n- 🌙 **21:00 KST** — NXT 收盤後 (evening)",
    },
    "rec_analyzed_at_kst": {"ko": "🕐 분석 시각 (KST)", "zh-TW": "🕐 分析時間 (KST)"},
    "rec_7d_trend_title": {"ko": "📊 7일 추천 종목 추이", "zh-TW": "📊 7日推薦個股趨勢"},
    "rec_7d_trend_caption": {"ko": "최근 7일간 어떤 종목이 자주 추천됐는지 + 신규/탈락 종목", "zh-TW": "最近7日內哪些個股經常被推薦 + 新進/淘汰"},
    "rec_7d_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "rec_7d_col_appear": {"ko": "등장 횟수", "zh-TW": "出現次數"},
    "rec_7d_col_max_score": {"ko": "최고 점수", "zh-TW": "最高分"},
    "rec_7d_col_tier": {"ko": "Tier", "zh-TW": "階層"},
    "rec_7d_col_last": {"ko": "최근 등장", "zh-TW": "最近出現"},
    "rec_7d_appear_format": {"ko": "{n}/{total}일", "zh-TW": "{n}/{total}日"},
    "rec_7d_insufficient": {"ko": "7일치 데이터 부족", "zh-TW": "7日資料不足"},
    "rec_peer_unavailable": {"ko": "ℹ️ 동종업종 데이터를 가져올 수 없습니다.", "zh-TW": "ℹ️ 無法取得同產業資料。"},
    "rec_peer_top": {"ko": "📂 **{sector}** · 관련주 상위 {n}개", "zh-TW": "📂 **{sector}** · 相關股前 {n} 檔"},
    "rec_peer_col_compare": {"ko": "비교", "zh-TW": "比較"},
    "rec_peer_col_self": {"ko": "👈 본인", "zh-TW": "👈 本檔"},
    "rec_peer_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "rec_peer_col_price": {"ko": "현재가", "zh-TW": "現價"},
    "rec_peer_col_change": {"ko": "등락률", "zh-TW": "漲跌幅"},
    "rec_peer_sector_avg": {"ko": "📊 섹터 평균 등락률", "zh-TW": "📊 產業平均漲跌幅"},
    "rec_peer_self_vs_sector": {"ko": "본인", "zh-TW": "本檔"},
    "rec_peer_sector_diff": {"ko": "섹터 대비", "zh-TW": "與產業比"},
    "rec_session_label_morning": {"ko": "장 시작 전", "zh-TW": "開盤前"},
    "rec_session_label_intraday": {"ko": "장 중", "zh-TW": "盤中"},
    "rec_session_label_evening": {"ko": "장 마감 후", "zh-TW": "收盤後"},
    "rec_footer": {
        "ko": "⚡ DB 즉시 조회 모드 · 매일 평일 자동 분석 (GitHub Actions): 🌅 08:00 / ☀️ 14:00 / 🌙 21:00 KST",
        "zh-TW": "⚡ DB 即時查詢模式 · 每工作日自動分析 (GitHub Actions): 🌅 08:00 / ☀️ 14:00 / 🌙 21:00 KST",
    },

    # 강세 테마 + 단타/장기 관점 + 컴팩트 테이블
    "rec_hot_themes_title": {"ko": "🔥 오늘 강세 테마", "zh-TW": "🔥 今日強勢主題"},
    "rec_hot_themes_empty": {"ko": "테마 데이터 부족", "zh-TW": "主題資料不足"},
    "rec_hot_themes_stocks": {"ko": "종목", "zh-TW": "檔"},
    "rec_hot_themes_avg": {"ko": "평균", "zh-TW": "平均"},
    "rec_horizon_short": {"ko": "🚀 단타", "zh-TW": "🚀 短線"},
    "rec_horizon_long": {"ko": "🏔 장기", "zh-TW": "🏔 長線"},
    "rec_horizon_both": {"ko": "🚀🏔 단타+장기", "zh-TW": "🚀🏔 短線+長線"},
    "rec_horizon_neutral": {"ko": "⚖ 중립", "zh-TW": "⚖ 中立"},
    "rec_horizon_hint": {
        "ko": "단타: RSI/거래량/신고가/ADX 등 단기 모멘텀 시그널 / 장기: 정배열/MACD/외인 연속 등 추세 시그널",
        "zh-TW": "短線: RSI/成交量/新高/ADX等短期動能 / 長線: 均線排列/MACD/外資連續等趨勢訊號",
    },
    "rec_tbl_col_rank": {"ko": "순위", "zh-TW": "排名"},
    "rec_tbl_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "rec_tbl_col_tier": {"ko": "Tier", "zh-TW": "階層"},
    "rec_tbl_col_theme": {"ko": "테마", "zh-TW": "主題"},
    "rec_tbl_col_price": {"ko": "현재가", "zh-TW": "現價"},
    "rec_tbl_col_change": {"ko": "등락률", "zh-TW": "漲跌幅"},
    "rec_tbl_col_score": {"ko": "점수", "zh-TW": "分數"},
    "rec_tbl_col_horizon": {"ko": "관점", "zh-TW": "觀點"},
    "rec_tbl_col_foreign5d": {"ko": "외인 5일", "zh-TW": "外資5日"},
    "rec_tbl_col_inst5d": {"ko": "기관 5일", "zh-TW": "機構5日"},
    "rec_tbl_col_reason": {"ko": "핵심 이유", "zh-TW": "核心理由"},
    "rec_detail_select": {"ko": "🔍 종목 선택 (상세 펼침)", "zh-TW": "🔍 選擇個股 (展開詳細)"},
    "rec_detail_all_reasons": {"ko": "💡 추천 이유 (전체)", "zh-TW": "💡 推薦理由 (全部)"},
    "rec_detail_horizon_label": {"ko": "📊 관점", "zh-TW": "📊 觀點"},

    # ════════════════════════════════
    # 거시경제 헤더
    # ════════════════════════════════
    "macro_no_data": {"ko": "데이터 없음", "zh-TW": "無資料"},

    # ════════════════════════════════
    # 홈 / 대시보드 보강
    # ════════════════════════════════
    "home_link_holdings_hint": {
        "ko": "👉 [💼 보유 종목 페이지](/💼_보유_종목)에서 종목을 추가하면 여기서 종합 분석이 표시됩니다.",
        "zh-TW": "👉 在 [💼 持股頁面](/💼_보유_종목) 新增個股後,此處將顯示綜合分析。",
    },
    "home_card_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "home_card_col_eval": {"ko": "평가금액", "zh-TW": "評估金額"},
    "home_card_col_pnl_pct": {"ko": "수익률(%)", "zh-TW": "報酬率(%)"},
    "home_card_sector_prefix": {"ko": "🏢", "zh-TW": "🏢"},
    "home_card_supply": {"ko": "💹 수급", "zh-TW": "💹 籌碼"},
    "home_card_signal": {"ko": "📊 신호", "zh-TW": "📊 訊號"},

    # 보유자 액션 라벨
    "holder_action_stoploss": {
        "ko": "🔴 손절 검토 (손실 확대 + 추세 약화)",
        "zh-TW": "🔴 考慮停損 (虧損擴大 + 趨勢轉弱)",
    },
    "holder_action_takeprofit_all": {
        "ko": "💰 전량 익절 검토 (큰 수익 + 추세 둔화)",
        "zh-TW": "💰 考慮全部停利 (大幅獲利 + 趨勢趨緩)",
    },
    "holder_action_takeprofit_part": {
        "ko": "🎯 분할 익절 (50% 정리, 나머지 추세 추종)",
        "zh-TW": "🎯 分批停利 (整理50%,其餘跟隨趨勢)",
    },
    "holder_action_addbuy_strong": {
        "ko": "➕ 추가 매수 고려 (추세 강세 지속)",
        "zh-TW": "➕ 考慮加碼 (強勢趨勢持續)",
    },
    "holder_action_addbuy_oversold": {
        "ko": "🤔 분할 추가매수 신중 (과매도 반등 노림)",
        "zh-TW": "🤔 謹慎分批加碼 (押注超賣反彈)",
    },
    "holder_action_hold_trend": {
        "ko": "🟢 홀딩 (추세 유효)",
        "zh-TW": "🟢 續抱 (趨勢有效)",
    },
    "holder_action_hold_wait": {
        "ko": "⏸️ 홀딩 (추세 회복 대기)",
        "zh-TW": "⏸️ 續抱 (等待趨勢回升)",
    },
    "holder_action_partial_exit": {
        "ko": "⚠️ 일부 정리 검토 (추세 약화)",
        "zh-TW": "⚠️ 考慮部分出場 (趨勢轉弱)",
    },
    "holder_action_observe": {
        "ko": "➖ 관망 (방향성 불명확)",
        "zh-TW": "➖ 觀望 (方向不明)",
    },
    "holder_flow_reversal": {"ko": "🔵 수급 반전 신호", "zh-TW": "🔵 籌碼反轉訊號"},
    "holder_flow_outflow_warn": {"ko": "⚠️ 수급 이탈 주의", "zh-TW": "⚠️ 注意籌碼流出"},
    "holder_flow_align_bull": {"ko": "✅ 수급 동행", "zh-TW": "✅ 籌碼同步"},
    "holder_flow_align_bear": {"ko": "❌ 수급 약세", "zh-TW": "❌ 籌碼弱勢"},
    "flow_detail_format": {
        "ko": "외인 {f:+,}주 {f_arrow} · 기관 {i:+,}주 {i_arrow}",
        "zh-TW": "外資 {f:+,}股 {f_arrow} · 機構 {i:+,}股 {i_arrow}",
    },
    "supply_label": {"ko": "수급", "zh-TW": "籌碼"},
    "signal_label": {"ko": "신호", "zh-TW": "訊號"},

    # 분석 손익 라벨 prefix (alerts)
    "alert_pnl_prefix": {"ko": "손익", "zh-TW": "損益"},

    # ════════════════════════════════
    # 💼 보유 종목 보강
    # ════════════════════════════════
    "holdings_autofill_fail": {"ko": "자동 채우기 실패", "zh-TW": "自動填寫失敗"},
    "holdings_input_name_required": {"ko": "종목명을 입력하세요", "zh-TW": "請輸入股票名稱"},
    "holdings_register_done": {"ko": "등록 완료", "zh-TW": "註冊完成"},
    "holdings_register_fail": {"ko": "등록 실패", "zh-TW": "註冊失敗"},
    "holdings_auto_analyzing": {"ko": "자동 분석 중...", "zh-TW": "自動分析中..."},
    "holdings_history_saved": {"ko": "📥 분석 히스토리 저장 완료", "zh-TW": "📥 已儲存分析歷史"},
    "holdings_auto_analysis_fail": {
        "ko": "⚠️ 자동 분석 실패 (등록은 완료)",
        "zh-TW": "⚠️ 自動分析失敗 (註冊已完成)",
    },
    "holdings_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "holdings_col_sector": {"ko": "섹터", "zh-TW": "產業"},
    "holdings_col_theme": {"ko": "테마", "zh-TW": "主題"},
    "holdings_col_avg": {"ko": "평단가", "zh-TW": "平均成本"},
    "holdings_col_cur": {"ko": "현재가", "zh-TW": "現價"},
    "holdings_col_qty": {"ko": "수량", "zh-TW": "數量"},
    "holdings_col_buy_amt": {"ko": "매수금액", "zh-TW": "購買金額"},
    "holdings_col_eval_amt": {"ko": "평가금액", "zh-TW": "評估金額"},
    "holdings_col_pnl": {"ko": "손익", "zh-TW": "損益"},
    "holdings_col_pnl_pct": {"ko": "수익률", "zh-TW": "報酬率"},
    "holdings_col_buy_date": {"ko": "매수일", "zh-TW": "購買日期"},
    "holdings_col_note": {"ko": "메모", "zh-TW": "備註"},
    "holdings_source": {"ko": "출처", "zh-TW": "來源"},

    # ════════════════════════════════
    # ⭐ 관심 종목 보강
    # ════════════════════════════════
    "watchlist_added": {"ko": "추가됨", "zh-TW": "已新增"},
    "watchlist_add_fail": {"ko": "추가 실패", "zh-TW": "新增失敗"},
    "watchlist_table_view": {"ko": "📊 관심 목록 (표 보기)", "zh-TW": "📊 自選股清單 (表格檢視)"},
    "watchlist_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "watchlist_col_cur": {"ko": "현재가", "zh-TW": "現價"},
    "watchlist_col_prev": {"ko": "전일대비", "zh-TW": "與前日比"},
    "watchlist_col_tags": {"ko": "태그", "zh-TW": "標籤"},
    "watchlist_col_note": {"ko": "메모", "zh-TW": "備註"},
    "watchlist_col_added": {"ko": "추가일", "zh-TW": "新增日期"},

    # ════════════════════════════════
    # 📜 분석 히스토리 보강
    # ════════════════════════════════
    "history_db_client_fail": {"ko": "DB 클라이언트 로드 실패", "zh-TW": "資料庫客戶端載入失敗"},
    "hist_col_analyzed_at": {"ko": "분석시각 (KST)", "zh-TW": "分析時間 (KST)"},
    "hist_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "hist_col_price": {"ko": "현재가", "zh-TW": "現價"},
    "hist_col_rsi": {"ko": "RSI", "zh-TW": "RSI"},
    "hist_col_cloud": {"ko": "구름", "zh-TW": "雲層"},
    "hist_col_decision": {"ko": "판단", "zh-TW": "判斷"},
    "hist_col_future_1st": {"ko": "📅 1차 시점 (~9봉, 피크)", "zh-TW": "📅 第1時點 (~9棒, 高峰)"},
    "hist_col_future_2nd": {"ko": "📅 2차 시점 (~17봉, 조정)", "zh-TW": "📅 第2時點 (~17棒, 回調)"},
    "hist_col_future_3rd": {"ko": "📅 3차 시점 (~26봉, 재상승)", "zh-TW": "📅 第3時點 (~26棒, 再上漲)"},
    "hist_col_flow": {"ko": "💹 수급", "zh-TW": "💹 籌碼"},
    "hist_col_pattern_5d": {"ko": "🔬 +5봉 (패턴)", "zh-TW": "🔬 +5棒 (模式)"},
    "hist_col_pattern_10d": {"ko": "🔬 +10봉 (패턴)", "zh-TW": "🔬 +10棒 (模式)"},
    "hist_col_pattern_15d": {"ko": "🔬 +15봉 (패턴)", "zh-TW": "🔬 +15棒 (模式)"},
    "hist_col_pattern_20d": {"ko": "🔬 +20봉 (패턴)", "zh-TW": "🔬 +20棒 (模式)"},
    "hist_col_stop": {"ko": "🛡 손절", "zh-TW": "🛡 停損"},
    "hist_cloud_above": {"ko": "위 ↑", "zh-TW": "上方 ↑"},
    "hist_cloud_below": {"ko": "아래 ↓", "zh-TW": "下方 ↓"},
    "hist_cloud_inside": {"ko": "안 ↔", "zh-TW": "內部 ↔"},
    "hist_future_path_header": {
        "ko": "**📈 미래 추세 예측 (N파동 시나리오)**",
        "zh-TW": "**📈 未來趨勢預測 (N波情境)**",
    },
    "hist_future_peak": {"ko": "🔺 피크", "zh-TW": "🔺 高峰"},
    "hist_future_pullback": {"ko": "🔻 조정", "zh-TW": "🔻 回調"},
    "hist_future_no_data": {"ko": "ℹ️ 미래 경로 데이터 없음", "zh-TW": "ℹ️ 無未來路徑資料"},
    "hist_flow_header": {
        "ko": "**💹 외국인/기관 수급 (7일)**",
        "zh-TW": "**💹 外資/機構籌碼 (7日)**",
    },
    "hist_flow_summary": {"ko": "종합", "zh-TW": "綜合"},
    "hist_flow_no_data": {"ko": "ℹ️ 수급 데이터 없음", "zh-TW": "ℹ️ 無籌碼資料"},
    "hist_cycle_header": {
        "ko": "**⏰ 다음 시간 변곡점 (일목 시간론)**",
        "zh-TW": "**⏰ 下個時間轉折點 (一目時間論)**",
    },
    "hist_swing_header": {"ko": "**🔄 스윙 포인트**", "zh-TW": "**🔄 擺動點**"},
    "hist_pattern_header": {
        "ko": "**🔍 패턴 매칭 (과거 유사 패턴 기반 미래 예측)**",
        "zh-TW": "**🔍 模式比對 (基於過往相似模式的未來預測)**",
    },
    "hist_pattern_similar": {
        "ko": "유사 패턴 **{pc}개** (평균 상관계수 r={r})",
        "zh-TW": "相似模式 **{pc} 個** (平均相關係數 r={r})",
    },
    "hist_pattern_avg": {
        "ko": "20봉 후 평균: **{val:,.0f}원** ({pct:+.1f}%)",
        "zh-TW": "20根K棒後平均: **{val:,.0f} 元** ({pct:+.1f}%)",
    },
    "hist_pattern_lowhigh": {
        "ko": "  · 보수(low): {low:,.0f} · 낙관(high): {high:,.0f}",
        "zh-TW": "  · 保守(low): {low:,.0f} · 樂觀(high): {high:,.0f}",
    },
    "hist_pattern_matched_periods": {"ko": "  · 매칭 구간", "zh-TW": "  · 比對區間"},
    "hist_rawdata_note": {
        "ko": "💡 future_path / flow / cycles 데이터는 코드 업데이트 (2026-05-26) 이후 분석부터 raw_data에 저장됩니다.",
        "zh-TW": "💡 future_path / flow / cycles 資料自程式更新 (2026-05-26) 後的分析才會儲存於 raw_data。",
    },
    "hist_chart_loading": {"ko": "🔍 최신 일목균형표 차트 생성 중...", "zh-TW": "🔍 生成最新一目均衡表圖中..."},
    "hist_chart_fail": {"ko": "⚠️ 차트 실패", "zh-TW": "⚠️ 圖表生成失敗"},
    "hist_chart_mismatch_warn": {
        "ko": "⚠️ **차트는 오늘 기준** · **raw_data는 분석 시점({when}) 기준** — 미래 경로/사이클은 분석 당시 예측이라 현재 차트와 일치하지 않을 수 있음",
        "zh-TW": "⚠️ **圖表以今日為準** · **raw_data 以分析時點 ({when}) 為準** — 未來路徑/週期為當時預測,可能與現在圖表不符",
    },
    "hist_trend_col_time": {"ko": "시각", "zh-TW": "時間"},
    "hist_trend_col_price": {"ko": "현재가", "zh-TW": "現價"},
    "hist_trend_col_rsi": {"ko": "RSI", "zh-TW": "RSI"},
    "hist_trend_col_target_n": {"ko": "N목표", "zh-TW": "N目標"},
    "hist_trend_col_tenkan": {"ko": "전환선", "zh-TW": "轉換線"},
    "hist_trend_col_kijun": {"ko": "기준선", "zh-TW": "基準線"},
    "hist_tab_price_target": {"ko": "💰 가격 + 목표가", "zh-TW": "💰 價格 + 目標價"},
    "hist_tab_rsi": {"ko": "📊 RSI", "zh-TW": "📊 RSI"},
    "hist_tab_ichimoku5": {"ko": "🌥 일목 5선", "zh-TW": "🌥 一目5線"},
    "hist_rsi_caption": {"ko": "70+ 과매수 / 30- 과매도 / 50 중립", "zh-TW": "70+ 超買 / 30- 超賣 / 50 中立"},
    "hist_ichimoku5_pending": {"ko": "일목 데이터가 누적되면 표시", "zh-TW": "一目資料累積後顯示"},
    "hist_trend_need_more": {
        "ko": "💡 추이 차트는 같은 종목 자동 분석 2회 이상 누적되면 표시됩니다. 현재 {n}건.",
        "zh-TW": "💡 趨勢圖需同一個股自動分析累積2次以上才顯示。目前 {n} 筆。",
    },
    "hist_raw_daily_title": {"ko": "#### 🗂 일자별 누적 raw_data", "zh-TW": "#### 🗂 日別累積 raw_data"},
    "hist_raw_manual_title": {"ko": "#### 🗂 누적 분석 데이터 (DB raw_data)", "zh-TW": "#### 🗂 累積分析資料 (DB raw_data)"},
    "hist_candle_unit": {"ko": "봉", "zh-TW": "K棒"},
    "hist_won_suffix": {"ko": "원", "zh-TW": "元"},
    "hist_future_path_item": {
        "ko": "{role} · **{label}** ({cycle}봉 후) → **{price:,.0f}원** ({pct:+.1f}%)",
        "zh-TW": "{role} · **{label}** ({cycle}根K棒後) → **{price:,.0f} 元** ({pct:+.1f}%)",
    },
    "hist_cycle_item": {"ko": "  · +{cycle}봉 후", "zh-TW": "  · +{cycle}根K棒後"},
    "hist_swing_item": {
        "ko": "  A: {a:,.0f} · B: {b:,.0f} · C: {c:,.0f}",
        "zh-TW": "  A: {a:,.0f} · B: {b:,.0f} · C: {c:,.0f}",
    },

    # ════════════════════════════════
    # 🔬 종목 분석 보강
    # ════════════════════════════════
    "analyze_sector_compare": {"ko": "🏢 동종업종 비교", "zh-TW": "🏢 同產業比較"},
    "analyze_sector_loading": {"ko": "동종업종 종목 조회 중...", "zh-TW": "查詢同產業個股中..."},
    "analyze_sector_default_label": {"ko": "동종업종", "zh-TW": "同產業"},
    "analyze_sector_top": {"ko": "📂 **{label}** · 상위 {n}개 종목", "zh-TW": "📂 **{label}** · 前 {n} 檔個股"},
    "analyze_sector_self": {"ko": "👈 본인", "zh-TW": "👈 本檔"},
    "analyze_sector_col_compare": {"ko": "비교", "zh-TW": "比較"},
    "analyze_sector_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "analyze_sector_col_price": {"ko": "현재가", "zh-TW": "現價"},
    "analyze_sector_col_change": {"ko": "등락률", "zh-TW": "漲跌幅"},
    "analyze_sector_summary": {
        "ko": "📊 섹터 평균 등락률: <strong style='color:{color};'>{avg:+.2f}%</strong> · 본인 등락률: <strong>{own:+.2f}%</strong>",
        "zh-TW": "📊 產業平均漲跌幅: <strong style='color:{color};'>{avg:+.2f}%</strong> · 本檔漲跌幅: <strong>{own:+.2f}%</strong>",
    },
    "analyze_sector_unavailable": {"ko": "ℹ️ 동종업종 데이터를 가져올 수 없습니다.", "zh-TW": "ℹ️ 無法取得同產業資料。"},
    "analyze_db_save_warn": {"ko": "⚠️ DB 저장 실패", "zh-TW": "⚠️ DB 儲存失敗"},
    "analyze_ma_period": {"ko": "기간", "zh-TW": "期間"},
    "analyze_ma_value": {"ko": "값", "zh-TW": "數值"},
    "analyze_ma_5": {"ko": "5일선", "zh-TW": "5日線"},
    "analyze_ma_20": {"ko": "20일선", "zh-TW": "20日線"},
    "analyze_ma_60": {"ko": "60일선", "zh-TW": "60日線"},
    "analyze_ma_120": {"ko": "120일선", "zh-TW": "120日線"},
    "analyze_won_suffix": {"ko": "원", "zh-TW": "元"},
    "analyze_wave_body": {
        "ko": """
            - **A (시작 저점)**: {a_price:,.0f}원 ({a_date})
            - **B (고점)**: {b_price:,.0f}원 ({b_date})
            - **C (조정 저점)**: {c_price:,.0f}원 ({c_date})
            - **C 형성 여부**: {c_formed}

            **파동론 공식**:
            - V = B + (B − C) = {v:,.0f}
            - N = C + (B − A) = {n:,.0f}
            - E = B + (B − A) = {e:,.0f}
            """,
        "zh-TW": """
            - **A (起始低點)**: {a_price:,.0f} 元 ({a_date})
            - **B (高點)**: {b_price:,.0f} 元 ({b_date})
            - **C (回調低點)**: {c_price:,.0f} 元 ({c_date})
            - **C 是否形成**: {c_formed}

            **波浪論公式**:
            - V = B + (B − C) = {v:,.0f}
            - N = C + (B − A) = {n:,.0f}
            - E = B + (B − A) = {e:,.0f}
            """,
    },
    "analyze_wave_c_formed": {"ko": "✅ 형성", "zh-TW": "✅ 已形成"},
    "analyze_wave_c_not_formed": {"ko": "⚠️ 미형성 (신규 추세 진행 중)", "zh-TW": "⚠️ 未形成 (新趨勢進行中)"},

    # ════════════════════════════════
    # 🆚 종목 비교 (deprecated)
    # ════════════════════════════════
    "compare_title": {"ko": "🆚 종목 비교", "zh-TW": "🆚 個股比較"},
    "compare_moved_info": {
        "ko": "이 기능은 **🎯 추천 종목** 페이지 각 카드 내부의 **🏢 섹터 · 관련주 비교** expander로 통합되었습니다.",
        "zh-TW": "此功能已整合至 **🎯 推薦個股** 頁面各卡片內部的 **🏢 產業·相關股比較** 展開區。",
    },
    "compare_goto_recommend": {"ko": "🎯 추천 종목으로 이동", "zh-TW": "🎯 前往推薦個股"},

    # ════════════════════════════════
    # 📅 캘린더
    # ════════════════════════════════
    "calendar_title": {"ko": "📅 공시 · 경제 캘린더", "zh-TW": "📅 公示 · 經濟日曆"},
    "calendar_caption": {
        "ko": "보유/관심 종목 공시 (OpenDART) + 주요 거시 일정",
        "zh-TW": "持股/自選股公示 (OpenDART) + 主要總體經濟行事曆",
    },
    "calendar_start_date": {"ko": "시작일", "zh-TW": "起始日"},
    "calendar_end_date": {"ko": "종료일", "zh-TW": "結束日"},
    "calendar_include_macro": {"ko": "거시 일정 포함", "zh-TW": "包含總經行事曆"},
    "calendar_only_my": {"ko": "내 종목만 (보유+관심)", "zh-TW": "僅我的個股 (持股+自選)"},
    "calendar_disclosure_title": {"ko": "📰 종목 공시", "zh-TW": "📰 個股公示"},
    "calendar_need_register": {
        "ko": "💡 보유 또는 관심 종목을 먼저 등록하세요.",
        "zh-TW": "💡 請先登錄持股或自選股。",
    },
    "calendar_loading_n": {"ko": "{n}개 종목 공시 조회 중...", "zh-TW": "查詢 {n} 檔個股公示中..."},
    "calendar_no_disclosure": {"ko": "📭 해당 기간 공시 없음", "zh-TW": "📭 該期間無公示"},
    "calendar_disclosure_count": {"ko": "건", "zh-TW": "筆"},
    "calendar_filer": {"ko": "제출인", "zh-TW": "提交人"},
    "calendar_macro_title": {"ko": "🌍 주요 거시 일정 (참고)", "zh-TW": "🌍 主要總經行事曆 (參考)"},
    "calendar_macro_caption": {
        "ko": "정기 일정 안내 — 정확한 일정은 한국은행/연준 공식 발표 확인",
        "zh-TW": "定期行事曆指引 — 精確時間請參考韓國銀行/聯準會官方公告",
    },
    "calendar_macro_bok_when": {"ko": "매월 둘째주 목", "zh-TW": "每月第二週四"},
    "calendar_macro_bok_what": {"ko": "🏛 한국은행 금통위 (기준금리 결정)", "zh-TW": "🏛 韓國銀行金融貨幣委員會 (基準利率決議)"},
    "calendar_macro_fomc_when": {"ko": "매월 둘째주 목", "zh-TW": "每月第二週四"},
    "calendar_macro_fomc_what": {"ko": "🇺🇸 FOMC 회의 (3·6·9·12월 분기 중)", "zh-TW": "🇺🇸 FOMC 會議 (3·6·9·12月季度中)"},
    "calendar_macro_kosis_when": {"ko": "매월 1·15일", "zh-TW": "每月 1·15日"},
    "calendar_macro_kosis_what": {"ko": "📊 KOSIS 주요 경제지표 발표", "zh-TW": "📊 KOSIS 主要經濟指標公佈"},
    "calendar_macro_nfp_when": {"ko": "매주 금요일 21:30 KST", "zh-TW": "每週五 21:30 KST"},
    "calendar_macro_nfp_what": {"ko": "🇺🇸 미국 비농업고용지표 (월 첫 금)", "zh-TW": "🇺🇸 美國非農就業數據 (每月第一個週五)"},
    "calendar_macro_jobless_when": {"ko": "매주 목요일 21:30 KST", "zh-TW": "每週四 21:30 KST"},
    "calendar_macro_jobless_what": {"ko": "🇺🇸 신규 실업수당 청구건수", "zh-TW": "🇺🇸 美國初次申請失業救濟金人數"},
    "calendar_macro_cpi_when": {"ko": "매월 셋째주 목 21:30 KST", "zh-TW": "每月第三週四 21:30 KST"},
    "calendar_macro_cpi_what": {"ko": "🇺🇸 CPI 발표 (전월 데이터)", "zh-TW": "🇺🇸 CPI 公佈 (前月數據)"},
    "calendar_footer": {
        "ko": "ℹ️ OpenDART 공시는 보유/관심 종목 한정. 전체 공시는 [DART](https://dart.fss.or.kr/) 직접 검색.",
        "zh-TW": "ℹ️ OpenDART 公示僅限持股/自選股。全部公示請至 [DART](https://dart.fss.or.kr/) 直接搜尋。",
    },

    # ════════════════════════════════
    # 🌡️ 시장 히트맵
    # ════════════════════════════════
    "heatmap_title": {"ko": "🌡️ 시장 히트맵", "zh-TW": "🌡️ 市場熱力圖"},
    "heatmap_caption": {
        "ko": "시가총액 = 박스 크기 · 등락률 = 색상 (빨강↑/파랑↓)",
        "zh-TW": "市值 = 方塊大小 · 漲跌幅 = 顏色 (紅↑/藍↓)",
    },
    "heatmap_market": {"ko": "시장", "zh-TW": "市場"},
    "heatmap_market_all": {"ko": "전체", "zh-TW": "全部"},
    "heatmap_top_n": {"ko": "상위 N개", "zh-TW": "前 N 檔"},
    "heatmap_refresh": {"ko": "🔄 새로고침", "zh-TW": "🔄 重新整理"},
    "heatmap_loading": {"ko": "{market} 시총 상위 {n}개 조회 중... (최대 30초)", "zh-TW": "查詢 {market} 市值前 {n} 檔中... (最多30秒)"},
    "heatmap_no_data": {"ko": "데이터를 가져올 수 없습니다.", "zh-TW": "無法取得資料。"},
    "heatmap_squarify_missing": {
        "ko": "squarify 패키지가 필요합니다. requirements.txt에 추가하고 재배포하세요:\n```\nsquarify>=0.4\n```",
        "zh-TW": "需要 squarify 套件。請加入 requirements.txt 後重新部署:\n```\nsquarify>=0.4\n```",
    },
    "heatmap_chart_title": {
        "ko": "{market} 시가총액 상위 {n}개 — 박스 크기=시총, 색상=등락률",
        "zh-TW": "{market} 市值前 {n} 檔 — 方塊大小=市值, 顏色=漲跌幅",
    },
    "heatmap_table_title": {"ko": "📋 상세 표", "zh-TW": "📋 詳細表格"},
    "heatmap_col_stock": {"ko": "종목", "zh-TW": "個股"},
    "heatmap_col_marketcap": {"ko": "시가총액 (조)", "zh-TW": "市值 (兆)"},
    "heatmap_col_close": {"ko": "종가", "zh-TW": "收盤價"},
    "heatmap_col_change": {"ko": "등락률", "zh-TW": "漲跌幅"},
    "heatmap_metric_up": {"ko": "📈 상승", "zh-TW": "📈 上漲"},
    "heatmap_metric_down": {"ko": "📉 하락", "zh-TW": "📉 下跌"},
    "heatmap_metric_flat": {"ko": "➖ 보합", "zh-TW": "➖ 持平"},
    "heatmap_metric_avg": {"ko": "평균 등락률", "zh-TW": "平均漲跌幅"},
}


# ──────────────────────────────────────────
# API
# ──────────────────────────────────────────
# URL query param 별칭 (?lang=kr 또는 ?lang=tw)
_LANG_ALIASES = {
    "kr": "ko", "ko": "ko", "ko-KR": "ko", "ko_KR": "ko",
    "tw": "zh-TW", "zh-tw": "zh-TW", "zh-TW": "zh-TW", "zh_TW": "zh-TW",
    "zh-Hant": "zh-TW", "tc": "zh-TW",
}


def _lang_to_alias(lang: str) -> str:
    """내부 lang 코드 → URL alias (ko → kr, zh-TW → tw)."""
    return {"ko": "kr", "zh-TW": "tw"}.get(lang, lang)


def get_lang() -> str:
    """현재 선택된 언어. 우선순위: URL query → session_state → DEFAULT."""
    # URL query param 우선
    try:
        qp = st.query_params.get("lang")
        if qp:
            resolved = _LANG_ALIASES.get(qp) or _LANG_ALIASES.get(qp.lower())
            if resolved and resolved in SUPPORTED_LANGS:
                # session_state 동기화 (이후 변경 추적용)
                if st.session_state.get("lang") != resolved:
                    st.session_state["lang"] = resolved
                return resolved
    except Exception:
        pass
    return st.session_state.get("lang", DEFAULT_LANG)


def set_lang(lang: str) -> None:
    """언어 설정 (session_state 저장 + URL query 동기화)."""
    if lang not in SUPPORTED_LANGS:
        return
    st.session_state["lang"] = lang
    # URL query param 동기화
    try:
        st.query_params["lang"] = _lang_to_alias(lang)
    except Exception:
        pass


def t(key: str, **kwargs) -> str:
    """번역 텍스트 반환.

    Args:
        key: 번역 키
        **kwargs: format 인자 (예: t("hello", name="John"))
    """
    lang = get_lang()
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def language_selector(location: str = "sidebar") -> None:
    """언어 선택 UI."""
    current = get_lang()
    options = list(SUPPORTED_LANGS.keys())
    labels = [SUPPORTED_LANGS[l] for l in options]
    current_idx = options.index(current) if current in options else 0

    if location == "sidebar":
        with st.sidebar:
            selected_label = st.selectbox(
                "🌐 Language",
                labels,
                index=current_idx,
                key="lang_selector",
            )
    else:
        selected_label = st.selectbox(
            "🌐 Language",
            labels,
            index=current_idx,
            key="lang_selector_main",
        )

    selected_lang = options[labels.index(selected_label)]
    if selected_lang != current:
        set_lang(selected_lang)
        st.rerun()
