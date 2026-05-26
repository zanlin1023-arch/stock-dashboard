# 🛠 Stock Dashboard 트러블슈팅 노트

Streamlit Cloud 배포 중 발생한 문제와 해결 기록. 같은 패턴 재발 시 참고용.

---

## ✅ 검증된 동작 환경

### `requirements.txt` (절대 건드리지 말 것)
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

### `runtime.txt`
```
python-3.11.9
```

### `.python-version`
```
3.11
```

### `packages.txt` (한글 폰트)
```
fonts-nanum
fonts-nanum-coding
fontconfig
```

---

## 🚨 발생한 문제 5가지 + 해결책

### 1. Python 3.14 강제 사용 → `pkg_resources` ImportError

**증상**:
```
ModuleNotFoundError: No module named 'pkg_resources'
File "/home/adminuser/venv/lib/python3.14/site-packages/pykrx/__init__.py"
```

**원인**:
- Streamlit Cloud 기본 Python = 3.14
- Python 3.12+부터 `pkg_resources` 자동 설치 안 됨
- `pykrx`가 `import pkg_resources` 사용

**해결**:
- ✅ Streamlit Cloud Settings → **Python version: 3.11** 강제 선택
- ✅ 또는 앱 삭제 후 재생성 시 Advanced settings에서 Python 3.11
- ⚠️ `runtime.txt` / `.python-version` 만으로는 적용 안 될 때 있음 (GUI 설정이 우선)

---

### 2. Python 3.11에서도 `pkg_resources` 누락

**증상**: 위 #1과 같지만 Python 3.11 환경에서.

**원인**:
- Streamlit Cloud 일부 venv는 minimal install로 `setuptools` 빠져있음

**최종 해결**:
- ✅ **`pykrx` 자체를 의존성에서 제거**
- ✅ OHLCV 조회를 `FinanceDataReader (FDR)`로 마이그레이션
- ⚠️ pykrx 사용처는 try/except로 우아하게 graceful degradation
  - `technical.py:fetch_ohlcv` — FDR 우선, pykrx 폴백
  - `market_context.py`, `fundamental.py` — pykrx import를 try/except로 감쌈

---

### 3. `data.krx.co.kr` 접근 차단

**증상**:
```
ValueError: Failed to load data from http://data.krx.co.kr/...
fdr.StockListing("KRX")
```

**원인**:
- Streamlit Cloud(AWS 미국 IP)에서 한국 KRX 사이트 접근 차단

**해결**:
- ✅ 종목 리스트 2,878개를 **CSV 캐시로 GitHub에 저장**
  - 위치: `analyzer/data/krx_listing.csv` (85KB)
- ✅ `_utils.py:resolve_ticker` → 캐시 우선 읽기
- ✅ 로컬에서는 `fdr.StockListing("KRX")` 실시간 호출 (fallback)
- 📝 캐시 갱신은 로컬에서 주기적으로 (예: 분기마다)

---

### 4. 차트 한글 깨짐 (□ 사각형)

**증상**: 차트 안의 한글이 다 `□`로 표시

**원인**: Linux 서버에 한글 폰트 (Malgun Gothic 등) 없음

**해결**:
- ✅ `packages.txt`에 **`fonts-nanum`** 추가 (apt 패키지)
- ✅ `chart_ichimoku.py` / `chart_scenario.py` 폰트 우선순위:
  ```python
  candidates = ["NanumGothic", ..., "Malgun Gothic", "Noto Sans CJK KR"]
  ```
- ✅ 시스템 폰트 cache 강제 rebuild 폴백 추가
- ✅ 직접 ttf 로드 폴백: `/usr/share/fonts/truetype/nanum/NanumGothic.ttf`

---

### 5. **"Error installing requirements"** — 진짜 원인은 packages.txt

**증상**: 빌드 화면에 그냥 "Error installing requirements" 빨간 페이지.

**진짜 원인** (로그 보고 확정):
```
Package fonts-nanum-coding is not available
E: Package 'fonts-nanum-coding' has no installation candidate
[xx:xx:xx] ❗️ installer returned a non-zero exit code
```

→ **`packages.txt`의 `fonts-nanum-coding` 패키지가 Debian trixie에 없음**.
- Streamlit Cloud는 Debian trixie 사용
- 한글 폰트 패키지 일부는 bullseye에만 있고 trixie엔 없음
- apt 실패 시 빌드 전체가 "Error installing requirements"로 표시 (헷갈리는 메시지!)

**해결**:
- ✅ `packages.txt`에서 `fonts-nanum-coding` 제거
- ✅ `fonts-nanum` + `fontconfig`만 유지 (이것만으로 한글 충분)

**❌ 절대 하지 말 것**:
| 추가했던 것 | 왜 문제 |
|---|---|
| `fonts-nanum-coding` (packages.txt) | Debian trixie에서 미지원 |
| `setuptools>=68` | Streamlit Cloud는 자체 setuptools 사용 — pin 충돌 가능 |
| `wheel` 명시 | 자동 제공, 명시하면 버전 충돌 가능 |
| `pip>=24` | Streamlit Cloud는 자체 pip — manifest로 pin하면 fail |
| 버전 strict pin (`streamlit>=1.30`) | 일부 환경에서 dep solver 충돌 |

**디버깅 교훈**:
- "Error installing requirements" = requirements.txt 문제가 아닐 수 있음
- **packages.txt 의 apt 설치 실패**도 같은 메시지로 표시됨!
- 항상 로그 확인 필수 (Streamlit Cloud → 앱 페이지 → 우하단 Manage app)

---

## 🔁 빌드 실패 시 디버깅 순서

### Step 1: 마지막 성공 시점 확인
```bash
git log --oneline -20
# 잘 됐던 commit hash 기억
```

### Step 2: requirements.txt diff
```bash
git diff <last-working-commit>..HEAD -- requirements.txt
```
→ 그 사이 추가/제거된 패키지가 범인일 가능성

### Step 3: 로그 확인 (가능하면)
- Streamlit Cloud → 앱 → ⋮ → Settings → Logs
- 또는 앱 페이지 우하단 햄버거 아이콘
- 빨간 `ERROR:` 줄 찾기

### Step 4: 패키지 단계적 제거
1. 의심 패키지 1개 제거 → push → 5분 대기 → 확인
2. 빌드 통과하면 그게 범인
3. 통과 안 하면 다음 패키지

### Step 5: 최후의 수단 — Delete + Create
- 앱 완전 삭제 후 새로 만들기
- Python 3.11 명시 선택
- Secrets 다시 입력

---

## 📌 핵심 교훈

1. **시스템 기본 패키지 명시 금지**: setuptools, wheel, pip는 Streamlit Cloud가 알아서 함
2. **버전 명시 최소화**: 패키지명만 적고 의존성 해결사가 선택하게
3. **검증된 환경 보존**: 잘 되는 commit 발견하면 그 requirements.txt를 절대 변경 X
4. **변경 시 1개씩**: requirements 수정은 한 번에 하나만 추가/제거
5. **시간외 거래/외부 사이트는 캐시**: KRX 같은 한국 전용 사이트는 미국 IP 차단 가능 → CSV 캐시

---

## 🌐 외부 의존성 / 데이터 소스

| 소스 | 환경 | 안정성 | 대안 |
|---|---|---|---|
| **pykrx** | ❌ Streamlit Cloud | 비호환 (pkg_resources) | FDR |
| **FDR** | ✅ 양쪽 | 좋음 | 네이버 스크래핑 |
| **OpenDART** | ✅ 양쪽 | 좋음 | — |
| **네이버 금융** | ✅ 양쪽 | 좋음 | — |
| **`data.krx.co.kr`** | ❌ Streamlit Cloud | 미국 IP 차단 | CSV 캐시 |
| **Supabase** | ✅ 양쪽 | 좋음 | — |
| **Anthropic API** | ✅ 양쪽 | 좋음 | 네이버 fallback |

---

## 🔐 Secrets 필수 키

### Streamlit Cloud Settings → Secrets
```toml
app_password = "..."
OPENDART_API_KEY = "..."
SUPABASE_URL = "https://....supabase.co"
SUPABASE_KEY = "sb_publishable_..."
ANTHROPIC_API_KEY = "sk-ant-..."  # optional (자동 채우기용)
```

### GitHub Actions Secrets (매일 자동 스냅샷)
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `OPENDART_API_KEY`

### 로컬 (`.streamlit/secrets.toml` — gitignore 보호)
- 위 모두 포함

---

## 📊 시스템 아키텍처 요약

```
┌──────────────────────────────────────────────────┐
│  사용자 (브라우저)                                │
└────────────┬─────────────────────────────────────┘
             │
             │  https://stock-dashboard-ujim.streamlit.app
             │  http://localhost:8501 (로컬)
             ▼
┌──────────────────────────────────────────────────┐
│  Streamlit Cloud (Public Repo, 무료)              │
│  ├─ app.py (홈 / 종목 분석)                       │
│  ├─ pages/1_💼_보유_종목.py                       │
│  ├─ pages/2_⭐_관심_종목.py                       │
│  ├─ pages/3_📜_분석_히스토리.py                   │
│  └─ analyzer/ (분석 모듈)                         │
└────────────┬─────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────┐
│  데이터 소스                                       │
│  ├─ FDR (시세, OHLCV)                            │
│  ├─ OpenDART (재무제표/공시)                      │
│  ├─ 네이버 금융 (실시간 시세, 컨센서스, 수급)      │
│  ├─ Anthropic Claude (종목 자동 enrich)          │
│  └─ Supabase PostgreSQL (보유/관심/히스토리)      │
└──────────────────────────────────────────────────┘
             ▲
             │
┌──────────────────────────────────────────────────┐
│  GitHub Actions (매일 18:00 KST 자동 스냅샷)      │
│  └─ scripts/daily_snapshot.py → Supabase         │
└──────────────────────────────────────────────────┘
```

---

## 🔗 관련 링크

- 배포 앱: https://stock-dashboard-ujim.streamlit.app
- GitHub repo: https://github.com/zanlin1023-arch/stock-dashboard
- Streamlit Cloud 콘솔: https://share.streamlit.io
- Supabase 콘솔: https://supabase.com/dashboard
- GitHub Actions: https://github.com/zanlin1023-arch/stock-dashboard/actions

---

_최종 업데이트: 2026-05-26 (commit `dc6bea1` — requirements 복원)_
