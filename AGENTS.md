# Human Index — Codex Context

## 프로젝트 요약

Human Index는 커뮤니티 언급량 기반 주식 투자 시그널 분석 플랫폼이다.
커뮤니티 게시글, 증권사 리포트, 뉴스 기사 제목에서 종목과 감성을 추출해 Streamlit 대시보드로 보여준다.

## 현재 운영 구조

```text
macOS launchd
- mlbpark-crawler      30분마다 수집만
- clien-crawler        30분마다 수집만
- fmkorea-crawler      30분마다 수집만, max_pages=10
- analyzer             15분마다 미분석 posts 종목/감성 추출
- stats-updater        매일 00:10 오늘/어제 mention_daily_stats 갱신

GitHub Actions
- crawl-hankyung       평일 18:30 KST
- crawl-google-news    6시간마다

Streamlit Cloud
- app.py + lib/*.py 대시보드
```

커뮤니티 크롤러는 `daily_worker.py --community <name> --crawl-only`로 수집만 수행한다.
분석과 통계 갱신은 `--analyze-only`, `--stats-only` launchd 작업이 별도 주기로 처리한다.

## 주요 명령

```bash
# 대시보드
streamlit run app.py

# 테스트
pytest -q

# 커뮤니티 수집만
python scripts/daily_worker.py --community mlbpark --crawl-only
python scripts/daily_worker.py --community clien --crawl-only
python scripts/daily_worker.py --community fmkorea --crawl-only

# 후처리
python scripts/daily_worker.py --analyze-only
python scripts/daily_worker.py --stats-only
python scripts/daily_worker.py --postprocess-only

# 전문가/뉴스
python scripts/crawl_hankyung.py
python scripts/crawl_google_news.py
```

## 코드 구조

| 경로 | 역할 |
|------|------|
| `app.py` | Streamlit 진입점, 사이드바, 페이지 라우팅 |
| `lib/shared.py` | DB 연결, 쿼리 실행, 공통 UI/차트 헬퍼 |
| `lib/community.py` | 커뮤니티 페이지 |
| `lib/report.py` | 증권사 리포트 페이지 |
| `lib/news.py` | 뉴스 페이지 |
| `lib/overview.py` | 종합 대시보드와 종목 검색 |
| `scripts/daily_worker.py` | 커뮤니티 수집/분석/통계 모드 실행 |
| `scripts/crawler_config.py` | 커뮤니티 설정, HTTP 헤더, FM코리아 옵션 |
| `scripts/data_loader.py` | 별칭/감성/오매칭 CSV 로더 |
| `scripts/crawl_hankyung.py` | 한경 컨센서스 크롤러 |
| `scripts/crawl_google_news.py` | Google News RSS 크롤러 |
| `launchd/*.plist` | 로컬 Mac Mini launchd 작업 템플릿 |
| `tests/` | pytest 테스트 |

## 개발 규칙

- 파일 검색은 `rg`/`rg --files`를 우선 사용한다.
- 수동 코드 수정은 `apply_patch`로 한다.
- DB/네트워크가 필요한 확인은 가능하면 read-only 쿼리로 먼저 본다.
- `.streamlit/secrets.toml`, 쿠키, DB 비밀번호는 커밋하지 않는다.
- 기존 사용자 변경을 되돌리지 않는다.
- 테스트 변경 후에는 `pytest -q`를 실행한다.
- launchd plist 변경 후에는 `plutil -lint launchd/*.plist`를 실행한다.

## 문서 참조

| 문서 | 내용 |
|------|------|
| `docs/project-structure.md` | 전체 아키텍처, 디렉토리, 데이터 흐름 |
| `docs/development-guide.md` | 코드 작성 패턴, 크롤러/후처리 모드 |
| `docs/deploy-guide.md` | Streamlit/GitHub Actions/launchd 운영 |
| `docs/db-schema.md` | DB 스키마 |
| `docs/design-guide.md` | Streamlit UI/CSS 디자인 규칙 |
