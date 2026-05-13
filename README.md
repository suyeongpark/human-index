# 📊 Human Index

> 커뮤니티 언급량 기반 주식 투자 시그널 분석 플랫폼

[![Streamlit](https://img.shields.io/badge/Streamlit-Live-FF4B4B?logo=streamlit)](https://human-index-fbsfdag8sk7hcpfedhrm9h.streamlit.app/)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/suyeongpark/human-index/crawl-google-news.yml?label=뉴스%20크롤러&logo=github)](https://github.com/suyeongpark/human-index/actions)

**대중 의견(커뮤니티)**과 **전문가 의견(증권사 리포트/뉴스)**을 교차 분석하여, 시장의 관심이 집중되는 종목을 조기에 포착합니다.

## 핵심 기능

| 기능 | 설명 |
|------|------|
| 🔍 **종목 언급량 랭킹** | 커뮤니티에서 많이 언급되는 종목을 실시간 추적 |
| 🚀 **급상승 감지** | 전주 대비 언급량이 급등한 종목 자동 탐지 |
| 📰 **전문가 리포트 분석** | 증권사 리포트 + 뉴스 기사 기반 감성 분석 |
| ⚖️ **교차 분석** | 대중 vs 전문가 감성 괴리 분석 — 시장 온도 차이 포착 |

## 아키텍처

```
Local Mac Mini / Actions      Supabase              Streamlit Cloud
┌──────────────────┐       ┌──────────────┐       ┌──────────────────┐
│ 커뮤니티 크롤러    │       │              │       │                  │
│ (MLBPark, 클리앙,  ├──────→│  PostgreSQL  │←──────┤  대시보드 (app.py) │
│  에펨코리아)       │INSERT │              │SELECT │                  │
│                  │       │              │       │  human-index.     │
│ 한경 리포트 크롤러  ├──────→│              │       │  streamlit.app   │
│ Google News 크롤러 ├──────→│              │       │                  │
└──────────────────┘       └──────────────┘       └──────────────────┘
```

## 데이터 소스

| 소스 | 유형 | 수집 주기 |
|------|------|----------|
| MLBPark 불펜 (주식 카테고리) | 커뮤니티 | 30분 |
| 클리앙 투자게시판 | 커뮤니티 | 30분 |
| 에펨코리아 국내주식 / 해외주식 | 커뮤니티 | 30분 |
| 한경 컨센서스 | 증권사 리포트 | 평일 1회 |
| Google News RSS | 뉴스 기사 | 6시간 |

## 기술 스택

- **Frontend**: [Streamlit](https://streamlit.io/) → Streamlit Cloud 배포
- **Database**: PostgreSQL → [Supabase](https://supabase.com/) 클라우드
- **Crawling**: Python (requests, BeautifulSoup, RSS XML)
- **Scheduling**: macOS launchd (커뮤니티) + GitHub Actions (리포트/뉴스)
- **Language**: Python 3.11

## 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# DB 접속 정보 설정
# 1) .streamlit/secrets.toml에 [database] 섹션 작성
# 2) 또는 DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD 환경변수 설정

# 대시보드 실행
streamlit run app.py
```

## 프로젝트 구조

```
├── app.py                    # Streamlit 앱 진입점
├── lib/                      # 대시보드 페이지 모듈
│   ├── shared.py             # 공통: DB, 페이지네이션, 네비게이션
│   ├── community.py          # 📢 커뮤니티 (대중 의견) 페이지
│   ├── report.py             # 🔬 리포트 페이지
│   ├── news.py               # 📰 뉴스 페이지
│   └── overview.py           # 📊 종합/종목 검색 페이지
├── scripts/                  # 크롤러
│   ├── data_loader.py        # CSV 데이터 로더
│   ├── daily_worker.py       # 커뮤니티 통합 파이프라인
│   ├── crawl_hankyung.py     # 한경 리포트 크롤러
│   ├── crawl_google_news.py  # Google News RSS 크롤러
│   └── import_tickers.py     # 종목 마스터 임포트
├── tests/                    # pytest 테스트
├── .github/workflows/        # GitHub Actions 자동화
└── docs/                     # 문서 (스키마, 배포 가이드)
```

## 문서

- [프로젝트 구조](docs/project-structure.md) — 상세 모듈 설명
- [DB 스키마](docs/db-schema.md) — 테이블 설계
- [배포 가이드](docs/deploy-guide.md) — 클라우드 배포 & 운영

## License

MIT
