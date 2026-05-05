# Human Index

커뮤니티 언급량 기반 주식 투자 시그널 분석 플랫폼.
**대중 의견(커뮤니티)**과 **전문가 의견(증권사 리포트/뉴스 기사)**을 교차 분석하여 투자 시그널을 제공한다.

## 핵심 흐름

1. **수집** → GitHub Actions + 로컬 launchd가 커뮤니티/리포트/뉴스 **제목**을 주기적으로 크롤링
2. **분석** → 제목에서 종목 추출 + 긍정/부정/중립 감성 판정
3. **시각화** → Streamlit 대시보드에서 언급량 랭킹, 급상승 감지, 채널별 교차 분석

## 기술 스택

| 구분 | 기술 |
|------|------|
| 대시보드 | Python + Streamlit → Streamlit Cloud |
| DB | PostgreSQL → Supabase |
| 크롤링 | Python (requests + BeautifulSoup + RSS) |
| 스케줄링 | GitHub Actions + macOS launchd |

## 데이터 소스

| 소스 | 유형 | 실행 환경 | 주기 |
|------|------|----------|------|
| MLBPark 불펜 / 클리앙 투자 | 커뮤니티 | GitHub Actions | 1시간 |
| 에펨코리아 국내주식 / 해외주식 | 커뮤니티 | 로컬 launchd | 30분 |
| 한경 컨센서스 | 증권사 리포트 | GitHub Actions | 평일 1회 |
| Google News RSS | 뉴스 기사 | GitHub Actions | 6시간 |

---

## 📚 문서 가이드

상세 내용은 `docs/` 디렉토리의 개별 문서를 참조하세요.

| 문서 | 내용 | 참조 시점 |
|------|------|-----------|
| [project-structure.md](docs/project-structure.md) | 디렉토리 구조, 모듈 구성, 페이지 목록, 데이터 파이프라인, DB 테이블 | 프로젝트 전체 구조 파악 |
| [development-guide.md](docs/development-guide.md) | 코딩 패턴 (SQL 변수 관리, UI 헬퍼, 네비게이션), 크롤러 추가 방법 | 코드 작성 전 |
| [design-guide.md](docs/design-guide.md) | 색상 체계, 타이포그래피, CSS 컴포넌트, 스타일 추가 규칙 | UI 수정 전 |
| [deploy-guide.md](docs/deploy-guide.md) | GitHub Actions, Streamlit Cloud, Supabase 설정, 트러블슈팅 | 배포/운영 |
| [db-schema.md](docs/db-schema.md) | 전체 DB 스키마 상세 (테이블, 컬럼, 제약조건) | DB 변경 전 |
