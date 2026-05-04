# Human Index

커뮤니티 언급량 기반 주식 투자 시그널 분석 플랫폼.
**대중 의견(커뮤니티)**과 **전문가 의견(증권사 리포트/뉴스 기사)**을 교차 분석하여 투자 시그널을 제공한다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| 대시보드 | Python + Streamlit → Streamlit Cloud 배포 |
| DB | PostgreSQL → Supabase 클라우드 |
| 크롤링 | Python (requests + BeautifulSoup + RSS XML) |
| 스케줄링 | **GitHub Actions** (주력) + macOS launchd (백업) |

## 시나리오

1. **데이터 수집**: GitHub Actions로 정해진 주기마다 커뮤니티/증권사 리포트/뉴스 기사를 크롤링하여 게시글 **제목**만 추출한다 (언급량 분석이 목적이므로 본문은 보지 않음). 날짜, 커뮤니티, 제목, 작성자, source_url을 DB에 저장한다.
2. **종목 추출 & 감성 분석**: DB에 저장된 데이터를 기반으로 제목에서 종목(ticker)을 추출하고, 제목 키워드로 긍정/부정/중립 감성을 판정하여 DB에 저장한다.
3. **트렌드 분석**: 전주 대비 언급량 급상승 종목을 감지하고, 대중 vs 전문가 감성 괴리를 분석한다.

## 데이터 소스

| 소스 | 유형 | 크롤러 | 주기 |
|------|------|--------|------|
| MLBPark 불펜 (주식 카테고리) | 커뮤니티 | `daily_worker.py` | 1시간 |
| 클리앙 투자게시판 | 커뮤니티 | `daily_worker.py` | 1시간 |
| 에펨코리아 주식게시판 | 커뮤니티 | `daily_worker.py` | 1시간 |
| 한경 컨센서스 | 증권사 리포트 | `crawl_hankyung.py` | 평일 1회 |
| Google News RSS | 뉴스 기사 | `crawl_google_news.py` | 6시간 |

## 중복 방지

- 모든 게시글/기사는 `source_url` 기준 `ON CONFLICT DO NOTHING`으로 중복 삽입 방지
- 커뮤니티 크롤러는 2연속 중복 페이지 감지 시 자동 종료

---

# 코드 작성 가이드

## 모듈 구조

### 대시보드 (`lib/`)

| 파일 | 역할 |
|------|------|
| `shared.py` | DB 연결, `run_query()`, `navigate_to()`, `paginated_dataframe()`, 상수 |
| `community.py` | 커뮤니티 페이지 5개 (개요, 랭킹, 급상승, 작성자, 게시글 목록) |
| `expert.py` | 전문가 페이지 3개 (개요, 리포트 랭킹, 리포트 목록) |
| `combined.py` | 종합 페이지 2개 (교차 분석, 종목 검색) |

- 공통 기능은 반드시 `shared.py`에 함수로 분리한다
- 각 페이지 함수는 `page_xxx(start_date, end_date)` 시그니처를 따른다
- UI 테이블은 `paginated_dataframe(df, key)` 헬퍼를 사용하여 25건 단위 페이지네이션 적용

### 크롤러 (`scripts/`)

| 파일 | 역할 |
|------|------|
| `db_config.py` | DB 접속 설정 (secrets.toml → 환경변수 → 기본값 순으로 참조) |
| `daily_worker.py` | 커뮤니티 크롤링 통합 파이프라인 + 종목 추출 + 감성 분석 |
| `crawl_hankyung.py` | 한경 컨센서스 리포트 크롤러 (독립 실행) |
| `crawl_google_news.py` | Google News RSS 파서 (독립 실행) |

- 새 커뮤니티 소스 추가 시: `daily_worker.py`의 `COMMUNITIES` 배열에 설정, `PARSERS` dict에 파서 함수 등록
- 새 전문가 소스 추가 시: 별도 크롤러 파일 생성 → GitHub Actions 워크플로우 추가
- LOG_DIR은 상대경로(`os.path.dirname(__file__)` 기반)로 설정하여 로컬/CI 호환

### GitHub Actions (`.github/workflows/`)

- 각 크롤러마다 별도 워크플로우 파일
- DB 접속 정보는 **Repository secrets**로 관리 (`${{ secrets.DB_NAME }}` 등)
- `workflow_dispatch` 트리거를 반드시 포함하여 수동 실행 가능하게

## 규칙

- DB 쿼리에서 중복 방지는 `ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING` 패턴 사용
- 목록(raw 데이터) 테이블은 DB 레벨 `LIMIT/OFFSET` 페이지네이션 적용
- 랭킹(집계 데이터) 테이블은 전체 조회 후 UI 슬라이싱 (`paginated_dataframe()`)
- 크롤러 로그는 `logs/` 디렉토리에 파일 + stdout 이중 출력
- `.streamlit/secrets.toml`과 `docs/.env`는 git에 커밋하지 않는다 (보안)
