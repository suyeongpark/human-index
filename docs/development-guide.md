# Human Index — 개발 가이드

> 코드 작성 규칙, 모듈 패턴, SQL 관리 방식

---

## 모듈 구조 규칙

### 대시보드 (`lib/`)

| 파일 | 역할 |
|------|------|
| `shared.py` | DB 연결, `run_query()`, UI 헬퍼 (`page_header`, `pagination_bar`, `paginated_dataframe`), 차트 헬퍼, 상수 |
| `community.py` | 커뮤니티 페이지 (개요, 랭킹, 급상승, 작성자, 게시글 목록) |
| `report.py` | 리포트 페이지 (개요, 랭킹, 급상승, 목록) |
| `news.py` | 뉴스 페이지 (개요, 랭킹, 급상승, 목록) |
| `overview.py` | 종합 페이지 (교차 분석, 종목 검색) |

### 크롤러 (`scripts/`)

| 파일 | 역할 |
|------|------|
| `db_config.py` | DB 접속 설정 (secrets.toml → 환경변수 → 기본값 순) |
| `crawler_config.py` | 크롤러 정적 설정 (커뮤니티 목록, HTTP 헤더, DATA_DIR 경로) |
| `data_loader.py` | CSV 데이터 로더 (별칭, 감성 키워드, 오매칭 방지, 투자의견 등급) |
| `daily_worker.py` | 커뮤니티 수집, 종목 추출, 통계 갱신 모드 실행 |
| `crawl_hankyung.py` | 한경 컨센서스 리포트 크롤러 (독립 실행) |
| `crawl_google_news.py` | Google News RSS 파서 (독립 실행) |
| `import_tickers.py` | KRX/ETF/US 종목 마스터 임포트 |

---

## 페이지 모듈 패턴

### 파일 구조

모든 페이지 모듈은 다음 구조를 따릅니다:

```python
"""모듈 설명"""

import streamlit as st
from lib.shared import (
    run_query, paginated_dataframe, period_tabs,
    page_header, pagination_bar,
    ...
)

# ─── SQL 쿼리 ──────────────────────────────────────────

SQL_KPI = """..."""
SQL_TREND = """
    SELECT {{date_sel}} as "날짜", ...
    GROUP BY {{date_grp}} ORDER BY 1
"""
SQL_LIST = """
    SELECT ... WHERE {where}
    LIMIT %s OFFSET %s
"""

# ─── 페이지 함수 ───────────────────────────────────────

def page_overview(start_date, end_date):
    page_header("타이틀", "캡션")
    ...
```

### 규칙

1. **SQL 쿼리는 상단 변수로 선언** — 함수 내 인라인 리터럴 금지
2. **변수 네이밍**: `SQL_` 접두사 + 대문자 스네이크 (예: `SQL_MENTION_RANKING`)
3. **동적 SQL 패턴**:
   - 기간 집계: `{{date_sel}}`, `{{date_grp}}` → `.replace()` 사용
   - 동적 WHERE: `{where}` → `.format(where=where)` 사용
   - 파라미터: `%s` 플레이스홀더 + params 튜플
4. **페이지 함수 시그니처**: `page_xxx(start_date, end_date)` 통일

---

## UI 컴포넌트 패턴

### 공통 UI 헬퍼 (`shared.py`)

| 함수 | 용도 | 사용 예 |
|------|------|---------|
| `page_header(title, caption)` | 페이지 타이틀 + 캡션 + 구분선 | 모든 페이지 상단 |
| `pagination_bar(page, total_pages, key, prefix)` | ⏮ ◀ 1/N ▶ ⏭ 네비게이션 | 목록 페이지 하단 |
| `paginated_dataframe(df, key)` | 25건 테이블 + 페이지네이션 | 랭킹 테이블 |
| `period_tabs(key, include_daily=False)` | 주간/월간/연간 pill 탭 | 기간 선택 (일간은 랭킹/대시보드에만) |

### 사용 규칙

- **새 페이지 추가 시**: 반드시 `page_header()`로 시작
- **페이지네이션**: 랭킹(집계) → `paginated_dataframe()`, 목록(raw) → 수동 `pagination_bar()`
- **인라인 HTML 금지**: CSS 클래스 사용 (`.page-caption`, `.pagination-info` 등)
- **스타일 변경**: `static/style.css`에서만 수정

---

## SQL 쿼리 규칙

### 중복 방지

```sql
INSERT INTO ... ON CONFLICT (source_url) WHERE source_url IS NOT NULL DO NOTHING
```

### 페이지네이션

- **랭킹(집계)**: 전체 조회 → `paginated_dataframe()`에서 UI 슬라이싱
- **목록(raw)**: DB 레벨 `LIMIT %s OFFSET %s` 적용

### 감성 점수 가중치

```python
SCORE_WEIGHT_POSITIVE = 2.0   # 긍정
SCORE_WEIGHT_NEGATIVE = 0.5   # 부정
SCORE_WEIGHT_NEUTRAL  = 1.0   # 중립
```

---

## 크롤러 규칙

### 새 커뮤니티 소스 추가

1. `crawler_config.py`의 `COMMUNITIES` 배열에 설정 추가
2. `daily_worker.py`의 `PARSERS` dict에 파서 함수 등록
3. 필요하면 `launchd/`에 커뮤니티 전용 `--crawl-only` plist 추가

### `daily_worker.py` 실행 모드

| 옵션 | 동작 | 사용처 |
|------|------|--------|
| 없음 | 수집 + 분석 + 통계 갱신 전체 실행 | 수동 점검 |
| `--community <name> --crawl-only` | 특정 커뮤니티 수집만 실행 | 커뮤니티별 launchd |
| `--analyze-only` | 미분석 게시글 종목/감성 추출 | analyzer launchd |
| `--stats-only` | 오늘/어제 일별 통계 갱신 | stats updater launchd |
| `--postprocess-only` | 분석 + 통계 갱신 | 수동 후처리 |

커뮤니티별 launchd는 수집만 수행해야 합니다. 분석/통계까지 같이 수행하면 커뮤니티별 작업이 늘어날수록 후처리가 중복 실행됩니다.

### FM코리아 운영 규칙

- FM코리아는 로컬 launchd에서만 실행합니다.
- `crawler_config.py`의 FM코리아 `max_pages`는 기본 `1`입니다.
- FM코리아 launchd는 5분 주기로 얕게 수집합니다. 밀린 글 복구가 필요하면 수동 백필로 페이지 수를 늘려 실행합니다.
- 차단/레이트리밋 응답(`status=430`)이 반복되면 주기보다 먼저 `max_pages`, 요청 딜레이, 중복 launchd 실행 여부를 확인합니다.
- `FMKOREA_COOKIE`, `FMKOREA_USER_AGENT`가 필요하면 launchd 환경변수로만 관리하고 커밋하지 않습니다.

### 종목 별칭 추가

1. 1:1 매핑: `scripts/data/aliases.csv`에 `alias,symbol` 행 추가
2. 1:N 매핑 (커뮤니티 합성어): `scripts/data/multi_aliases.csv`에 추가
3. 오매칭 방지: `scripts/data/skip_names.csv`에 추가

### 감성 키워드 추가

- 커뮤니티/뉴스: `scripts/data/sentiment_words.csv`에 `word,sentiment` 행 추가
- 전문가 투자의견: `scripts/data/opinion_grades.csv`에 `grade,sentiment` 행 추가

> 종목 매칭은 제목과 키워드 모두 `upper()`로 변환하여 대소문자 무시 매칭합니다.

### CSV 데이터 파일 구조

| 파일 | 헤더 | 용도 |
|------|------|------|
| `aliases.csv` | alias, symbol | 종목 별칭 (1:1) |
| `multi_aliases.csv` | alias, symbols | 복수 종목 별칭 (1:N, 쉼표구분) |
| `skip_names.csv` | name | 오매칭 방지 |
| `sentiment_words.csv` | word, sentiment | 감성 키워드 (positive/negative) |
| `opinion_grades.csv` | grade, sentiment | 투자의견 등급 (1/0/-1) |

### 새 전문가 소스 추가

1. 별도 크롤러 파일 생성 (`scripts/crawl_xxx.py`)
2. GitHub Actions 워크플로우 추가 (`.github/workflows/crawl-xxx.yml`)
3. `workflow_dispatch` 트리거 포함 (수동 실행 가능)

### 로그

- `logs/` 디렉토리에 파일 + stdout 이중 출력
- `LOG_DIR`은 `os.path.dirname(__file__)` 기반 상대 경로 (로컬/CI 호환)
- launchd 템플릿 변경 시 `plutil -lint launchd/*.plist`로 검증

---

## 네비게이션 패턴

### 페이지 간 이동

```python
from lib.shared import navigate_to

# 랭킹 → 게시글 목록 (종목 필터 전달)
navigate_to("📋 게시글 목록", filter_symbol="005930")

# 랭킹 → 종목 검색 (종목명 전달)
navigate_to("🔍 종목 검색", ticker_symbol="삼성전자")
```

### session_state 관리

- 페이지 상태: `st.session_state.page`
- 페이지네이션: `st.session_state.{key}_page` (예: `posts_page`, `rpt_page`, `news_page`)
- 네비게이션 데이터: `nav_ticker_symbol`, `nav_search_keyword`, `nav_filter_symbol`
- radio 동기화: `_pending_nav` 플래그

---

## 보안

- `.streamlit/secrets.toml` — git 제외
- `docs/.env` — git 제외
- DB 접속 정보 — GitHub **Repository secrets** 사용
