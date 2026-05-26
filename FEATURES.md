# 📋 Stock Dashboard 전체 기능 문서

마지막 업데이트: 2026-05-26

## 🎯 개요

KOSPI/KOSDAQ 한국 주식 종합 분석 대시보드. 일목균형표 + 백테스팅 + 추천 시스템 + 자동화.

- **앱 URL**: https://stock-dashboard-ujim.streamlit.app
- **GitHub**: https://github.com/zanlin1023-arch/stock-dashboard
- **로컬**: `E:\stock-dashboard` (`py -m streamlit run app.py`)

---

## 📑 페이지 구성

### 🏠 홈 / 종목 분석 (`app.py`)
**용도**: 개별 종목 종합 분석 (일목 + 기술적 + 펀더)

**기능**:
- 종목명/코드 입력 → 일목균형표 + 시그널 분석
- 일목 5선(전환/기준/선행A·B/후행) + 구름대
- 파동론 N/E/V 목표가 자동 계산
- 시간론 9/17/26봉 변곡 예측
- 백테스팅 가격대 (분할 매수/익절선)
- 차트 PNG 자동 생성
- DB 저장 옵션 (분석 히스토리 누적)
- 관심 종목 1클릭 추가

### 🎯 추천 종목 (`pages/4_🎯_추천_종목.py`) ⭐
**용도**: 날짜별 추천 종목 조회 + 시계열 추이

**핵심 가치**: DB 우선 조회 → **즉시 응답** (1초). 매일 16:30 KST 자동 계산.

**구조**:
- 📅 **날짜 선택** (최근 30일)
- ⏰ **세션 필터** (morning/intraday/evening 또는 전체)
- 🚀 **지금 분석 실행** (실시간 호출, 30초~6분)
- 🔍 **7일 추이 분석** (자주 등장 종목 + 신규/탈락)

**세션별 의미**:
- 🌅 **morning** — 장 시작 전 추천 (전일 외인+기관 동반 매수 우선)
- ☀️ **intraday** — 장 중 추천 (실시간 거래대금/거래량 폭증)
- 🌙 **evening** — 장 마감 후 추천 (오늘 종가 + 일목 시그널 변화)

**자동 디폴트 세션** (한국 시각 기준):
- < 09:00 → morning
- 09:00 ~ 15:30 → intraday
- 15:30 ~ → evening

**점수 산정**:
| 항목 | 점수 |
|---|---|
| 외인+기관 동반 매수 | +30 |
| 외인 매수 전환 | +20 |
| 외인 5일 누적 매수 | +10 |
| 기관 5일 누적 매수 | +10 |
| 외인 연속 매수 5일+ | +15 |
| 외인 매도 전환 | -20 |
| 외인+기관 동반 매도 | -30 |
| + 모멘텀 시그널 | 50% 가중 |

**Tier 자동 분류**:
- 🏛 대형주: 시총 5조원+
- 🏢 중형주: 5천억~5조
- 🏠 소형주: 1천억~5천억

**자동 제외**: ETF/ETN/우선주/스팩, 보유 종목 (관심 종목은 옵션)

### 💼 보유 종목 (`pages/1_💼_보유_종목.py`)
**용도**: 실보유 종목 관리 + 손익 추적

**기능**:
- 종목명/코드 + 평단가 + 수량 + 매수일 등록
- 🔮 **자동 채우기** (Claude API) — 종목명만 입력하면 메모 자동
- 매수일 모름 옵션 (디폴트: 오늘)
- 실시간 현재가 + 손익률 계산
- 포트폴리오 총괄 (총 매수액/평가액/손익)
- 종목 삭제

### ⭐ 관심 종목 (`pages/2_⭐_관심_종목.py`)
**용도**: 관심 종목 관리 + 태그 분류

**기능**:
- 종목명 + 메모 + 태그 등록
- 🔮 **자동 채우기** (Claude API) — 메모/태그 자동 생성
- 실시간 시세 + 등락률 표시
- 🚀 분석 페이지 1클릭 이동
- 종목 삭제

### 📜 분석 히스토리 (`pages/3_📜_분석_히스토리.py`)
**용도**: 누적 분석 결과 시계열 조회

**필터**:
- 종목 (전체/특정)
- 스냅샷 종류 (전체/수동/자동)

**기능**:
- 통계 카드 (총 분석 횟수, 매수/매도 판단 수)
- 일별 누적 테이블 (분석시각/타입/판단/RSI/구름위치)
- 종목 선택 시 **가격/RSI 추이 라인차트**

---

## 🗄 DB 스키마 (Supabase PostgreSQL, Seoul region)

### 1. `holdings` (9 cols)
보유 종목 — `stock_code`, `avg_price`, `quantity`, `purchase_date`, ...

### 2. `watchlist` (6 cols)
관심 종목 — `stock_code` UNIQUE, `tags[]`, `note`, ...

### 3. `analysis_history` (20 cols)
분석 히스토리 — `snapshot_type` ('manual'/'scheduled') 구분
- 기본 지표 (price, rsi_14, macd)
- 일목 (tenkan, kijun, senkou_a/b, cloud_position)
- 의사결정 (stance, action, target_v/n/e, stop_loss)
- `raw_data` JSONB (전체 백업)

### 4. `recommendations` (15 cols) ⭐ NEW
일별 추천 종목 누적
- `recommended_date` (인덱스)
- `session` ('morning'/'intraday'/'evening')
- `tier` ('large'/'mid'/'small')
- `rank_in_tier`
- 종목 정보 + 점수 + 수급 + 시그널 JSONB
- UNIQUE(date, session, tier, code) — 중복 방지

---

## 🤖 자동화 시스템 (GitHub Actions)

### `daily_snapshot.yml` — 매일 18:00 KST
**대상**: 보유 종목 + 관심 종목 전체

**동작**:
- 각 종목 OHLCV + 일목 + 의사결정 분석
- `analysis_history` 테이블 INSERT (`snapshot_type='scheduled'`)
- 1.5초 간격 (API 폭주 방지)

**용도**: 매일 같은 시각 종목 추적 → 시그널 변화 자동 감지

### `daily_recommend.yml` — 매일 16:30 KST ⭐ NEW
**대상**: 시장 전체 (KOSPI+KOSDAQ에서 동적 수집)

**동작**:
- recommend.recommend() 한 번 실행 (top_n=5, 약 6분)
- 보유 종목 자동 제외
- `recommendations` 테이블 INSERT (session='evening')

**용도**: 매일 추천 결과 누적 → 페이지 진입 시 즉시 표시 (1초)

### `test_build.yml` — push 시 자동
**대상**: requirements.txt 변경 시

**동작**:
- Ubuntu 22.04 + Python 3.11 (Streamlit Cloud 동일 환경)
- 패키지 하나씩 설치 → 어떤 게 fail인지 자동 검출
- 실패 시 GitHub에 알림

---

## 🌐 i18n (다국어) — 한국어 / 繁體中文 ⭐ NEW

### 구조
- `i18n.py` — 번역 사전 (200+ 키), `t()` 함수, `language_selector()` UI
- `common.py` — 사이드바 통합

### 지원 범위 (점진적 확장 가능)
- ✅ 사이드바 메뉴 (홈/추천/보유/관심/히스토리)
- ✅ 상단 네비 버튼 (홈/뒤로/추천/보유/관심)
- ✅ 인증 화면 (비밀번호 입력)
- ✅ 각 페이지 타이틀
- ✅ 홈 페이지 부제목
- ⚠️ 폼 라벨, 메시지, 분석 결과 (한국어 유지, 추후 확장)

### 사용 방법
사이드바 상단의 **🌐 Language** 드롭다운에서 선택:
- 한국어 (기본)
- 繁體中文

선택 즉시 화면 갱신 (session_state 저장).

---

## 🤖 Claude API 활용 (`analyzer/enrich.py`)

종목명만 입력하면 자동으로 메모 + 태그 + 업종 채워줌.

**Fallback 체인**:
1. **Claude (Anthropic)** — `claude-haiku-4-5` ($0.0002~$0.0005/호출)
2. **네이버 금융 스크래핑** — 업종/테마 (무료)
3. **FDR 캐시** — 시장 정보만 (오프라인)

**호출 예시**:
- 삼성전기 → "PCB·반도체 패키징·자동차 부품 제조" + [PCB, 반도체 패키징, 자동차 전장, HDI기판, 고주파 통신]
- 오이솔루션 → "광통신 및 데이터센터 네트워크 장비 제조" + [광통신장비, 데이터센터, 5G/6G 인프라, ...]

---

## 🔐 Secrets (3곳 동기화 필요)

### 1. 로컬 `.streamlit/secrets.toml` (gitignore)
```toml
app_password = "..."
OPENDART_API_KEY = "..."
SUPABASE_URL = "https://....supabase.co"
SUPABASE_KEY = "sb_publishable_..."
ANTHROPIC_API_KEY = "sk-ant-..."
```

### 2. Streamlit Cloud Settings → Secrets
위와 동일 (TOML 형식)

### 3. GitHub Actions Secrets
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `OPENDART_API_KEY`
- (선택) `ANTHROPIC_API_KEY`

---

## 📊 시스템 아키텍처

```
┌──────────────────────────────────────────────────┐
│  사용자 (브라우저)                                │
│  🌐 https://stock-dashboard-ujim.streamlit.app   │
│  🌐 http://localhost:8501 (로컬)                 │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  Streamlit App (5 pages)                          │
│  ├ 🏠 홈 / 종목 분석                              │
│  ├ 🎯 추천 종목 (DB 우선 조회)                    │
│  ├ 💼 보유 종목                                   │
│  ├ ⭐ 관심 종목                                   │
│  └ 📜 분석 히스토리                               │
└────────────┬─────────────────────────────────────┘
             │
   ┌─────────┴───────────┐
   ▼                     ▼
┌─────────┐         ┌─────────────────────┐
│ Cache   │         │ Supabase PostgreSQL │
│ 시세    │         │ - holdings          │
│         │         │ - watchlist         │
└────┬────┘         │ - analysis_history  │
     │              │ - recommendations   │
     ▼              └──────────▲──────────┘
┌──────────────┐               │
│ 데이터 소스   │               │
│ - FDR        │     ┌─────────┴──────────┐
│ - 네이버     │     │ GitHub Actions     │
│ - OpenDART   │     │ - daily_snapshot   │
│ - Claude API │────▶│   (18:00 KST)      │
└──────────────┘     │ - daily_recommend  │
                     │   (16:30 KST)      │
                     │ - test_build       │
                     │   (push 시)        │
                     └────────────────────┘
```

---

## ⚙️ 의존성 (`requirements.txt`)

검증된 동작 환경 (절대 변경 X):
```
streamlit
pandas
numpy
matplotlib
mplfinance
finance-datareader
opendartreader
python-dotenv
requests
beautifulsoup4
lxml
supabase
```

### 환경 설정
- `runtime.txt` → `python-3.11.9`
- `.python-version` → `3.11`
- `packages.txt` → `fonts-nanum`, `fontconfig`

### ❌ 절대 추가 X
- `setuptools`, `wheel`, `pip` (Streamlit Cloud 자체 사용)
- `fonts-nanum-coding` (Debian trixie 미지원)

상세 트러블슈팅: [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

---

## 🚀 로드맵 (TODO)

### 다음 단계 (우선순위 순)

1. **메인 대시보드** — 보유/관심/시그널 요약 통합 뷰
2. **i18n 전체 확장** — 분석 결과/시그널 메시지까지 다국어
3. **추천 최적화** — 6분 → 1분 (병렬 처리)
4. **시그널 변화 알림** — 매일 스냅샷 후 큰 변화 감지 → Slack/이메일
5. **NXT 데이터 통합** — 외국인 한투 계좌 불가 → 대안 모색
6. **백테스팅 강화** — 추천 후 실제 수익률 추적

### 검토 중

- 추가 데이터 소스 (KIS API 외 대안)
- 모바일 최적화
- 알림 시스템 (Slack/이메일)
- 다중 사용자 지원 (현재는 비밀번호 1개)

---

## 📝 변경 이력 (최근)

| 날짜 | 내용 |
|---|---|
| 2026-05-26 | 📅 날짜별 추천 시스템 + 🌐 i18n (한/번체) |
| 2026-05-26 | 🔮 Claude API 자동 enrich |
| 2026-05-26 | 🎯 추천 종목 페이지 (3 탭 시간대 분리) |
| 2026-05-26 | 📜 분석 히스토리 자동 누적 (daily_snapshot cron) |
| 2026-05-26 | 💼 보유 / ⭐ 관심 종목 페이지 + DB CRUD |
| 2026-05-26 | 🏗 멀티페이지 구조 + 네비게이션 |
| 2026-05-26 | 🐛 Streamlit Cloud 빌드 5가지 이슈 해결 (TROUBLESHOOTING.md) |
| 2026-05-26 | 🌐 Supabase PostgreSQL 통합 (Seoul) |
| 2026-05-26 | 📊 기본 일목균형표 + 백테 분석 |

---

## 🔗 관련 문서

- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 빌드 실패 해결 가이드
- [`README.md`](README.md) — 프로젝트 소개 + 시작 가이드
- [`db/schema.sql`](db/schema.sql) — DB 스키마 정의
- [`requirements.txt`](requirements.txt) — Python 의존성
- [`packages.txt`](packages.txt) — apt 시스템 패키지
- [`runtime.txt`](runtime.txt) — Python 버전 지정

---

_생성: 2026-05-26 | 작성: 자동화 도구 협업_
