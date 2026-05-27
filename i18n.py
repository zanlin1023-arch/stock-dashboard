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
        "ko": "💡 아직 저장된 추천이 없습니다. 매일 평일 다음 시각에 자동 분석됩니다:\n\n- 🌅 **08:00 KST** — 장 시작 전 (morning)\n- ☀️ **14:00 KST** — 장 중 (intraday)\n- 🌙 **21:00 KST** — NXT 마감 후 (evening)",
        "zh-TW": "💡 尚無已儲存的推薦。每個工作日將於以下時間自動分析:\n\n- 🌅 **08:00 KST** — 開盤前 (morning)\n- ☀️ **14:00 KST** — 盤中 (intraday)\n- 🌙 **21:00 KST** — NXT 收盤後 (evening)",
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

    # ════════════════════════════════
    # 거시경제 헤더
    # ════════════════════════════════
    "macro_no_data": {"ko": "데이터 없음", "zh-TW": "無資料"},
}


# ──────────────────────────────────────────
# API
# ──────────────────────────────────────────
def get_lang() -> str:
    """현재 선택된 언어 (session_state에서 가져옴)."""
    return st.session_state.get("lang", DEFAULT_LANG)


def set_lang(lang: str) -> None:
    """언어 설정 (session_state에 저장)."""
    if lang in SUPPORTED_LANGS:
        st.session_state["lang"] = lang


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
