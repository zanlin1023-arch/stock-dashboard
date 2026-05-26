# 📊 Stock Dashboard

한국 주식(KOSPI/KOSDAQ) 일목균형표 + 백테스팅 종합 분석 대시보드. Streamlit 기반.

## 🎯 주요 기능

- **일목균형표 종합 분석** — 5선 + 구름대 + 삼역호전/역전 자동 감지
- **파동론 목표가** — V/N/E 자동 계산 (분할 익절 가이드)
- **시간론 변곡 예측** — 9/17/26봉 시간 사이클
- **기술적 시그널** — RSI, MACD, 볼린저, 골든/데드크로스
- **백테스팅** — 1년/2년 데이터 기반 가격대

## 🚀 빠른 시작 (로컬)

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. Secrets 설정

`.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사하고 값 입력:

```toml
app_password = "your-password"
OPENDART_API_KEY = "your-opendart-key"
```

OpenDART API 키는 https://opendart.fss.or.kr/ 에서 무료 발급.

### 3. 실행

```bash
streamlit run app.py
```

브라우저에서 http://localhost:8501 접속.

## ☁️ Streamlit Cloud 배포

1. 이 repo를 본인 GitHub로 fork
2. https://share.streamlit.io 에서 "New app"
3. Repository, Branch, Main file (`app.py`) 선택
4. **Advanced settings → Secrets**에 `app_password`와 `OPENDART_API_KEY` 입력
5. Deploy

## 📂 구조

```
stock-dashboard/
├── app.py                  # Streamlit 진입점
├── analyzer/               # 분석 모듈
│   ├── _utils.py           # 공통 유틸 + 종목 코드 변환
│   ├── technical.py        # 기술적 분석 (이평/RSI/MACD/볼린저/일목)
│   ├── chart_ichimoku.py   # 일목균형표 전용 차트 + 파동론
│   ├── chart_scenario.py   # 시나리오 차트 (매물대 + 백테)
│   ├── market_context.py   # 시장 컨텍스트 + 수급
│   ├── momentum.py         # 추세 지속력 + ATR
│   ├── fundamental.py      # 펀더멘털 분석
│   └── signal_score.py     # 진입 적합도 점수
├── pages/                  # Streamlit 멀티페이지 (향후 추가)
├── .streamlit/
│   └── secrets.toml        # gitignore — 절대 커밋 X
├── requirements.txt
└── .gitignore
```

## 📊 일목균형표 공식

| 선 | 공식 |
|---|---|
| 전환선 (Tenkan) | (9일 최고가 + 9일 최저가) / 2 |
| 기준선 (Kijun) | (26일 최고가 + 26일 최저가) / 2 |
| 선행스팬 A | (전환선 + 기준선) / 2, +26일 |
| 선행스팬 B | (52일 최고가 + 52일 최저가) / 2, +26일 |
| 후행스팬 | 종가, −26일 |

**파동론 목표가**:
- V = B + (B − C)  → 1차 익절
- N = C + (B − A)  → 표준 목표
- E = B + (B − A)  → 강세 목표

## 📚 데이터 소스

- [pykrx](https://github.com/sharebook-kr/pykrx) — 한국거래소 데이터
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader) — 종목 리스트, 지수
- [OpenDartReader](https://github.com/FinanceData/OpenDartReader) — DART 공시/재무제표
- 네이버 금융 — 실시간 시세, 컨센서스

## ⚠️ 면책 조항

이 대시보드는 **참고용 분석 도구**입니다. 투자 결정은 본인 책임이며, 본 도구의 분석 결과로 인한 손실에 대해 작성자는 책임지지 않습니다.

## 📄 라이선스

MIT License

## 🤝 기여

이슈 / PR 환영.
