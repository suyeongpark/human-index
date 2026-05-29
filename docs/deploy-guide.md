# Human Index — 배포 가이드

> Supabase + Streamlit Cloud + GitHub Actions로 24/7 무중단 시스템 구축

---

## 배포 서비스

| 서비스 | 용도 | URL / 설정 |
|--------|------|-----------|
| **Streamlit Cloud** | 대시보드 | [human-index.streamlit.app](https://human-index-fbsfdag8sk7hcpfedhrm9h.streamlit.app/) |
| **Supabase** | PostgreSQL DB | 서울 리전, Session Pooler 사용 |
| **GitHub Actions** | 리포트/뉴스 크롤러 | Repository secrets로 DB 접속 |
| **macOS launchd** | 커뮤니티 크롤러 | 로컬 Mac Mini에서 30분마다 실행 |

---

## GitHub Actions 설정

### Repository Secrets

Settings → Secrets and variables → Actions → **Repository secrets**:

| Secret | 설명 |
|--------|------|
| `DB_NAME` | Supabase 데이터베이스 이름 (`postgres`) |
| `DB_HOST` | Supabase Session Pooler 호스트 |
| `DB_PORT` | 포트 (`5432`) |
| `DB_USER` | 유저명 (`postgres.{project_ref}` 형태) |
| `DB_PASSWORD` | Supabase DB 비밀번호 |

### 워크플로우 파일

| 파일 | cron (UTC) | 한국시간 |
|------|-----------|---------|
| `.github/workflows/crawl-hankyung.yml` | `30 9 * * 1-5` | 평일 18:30 |
| `.github/workflows/crawl-google-news.yml` | `0 0,6,12,18 * * *` | 09/15/21/03시 |

> 커뮤니티 크롤러는 GitHub Actions 워크플로를 사용하지 않고, cron 지연(수십분~수시간) 문제와 에펨코리아 IP 차단 이슈를 피하기 위해 **로컬 launchd로 실행**합니다.

### 수동 실행

Actions 탭 → 워크플로우 선택 → **Run workflow** 버튼

---

## Streamlit Cloud 설정

### Secrets

Streamlit Cloud → Manage app → Settings → Secrets:

```toml
[database]
DB_NAME = "postgres"
DB_HOST = "aws-1-ap-northeast-2.pooler.supabase.com"
DB_PORT = 5432
DB_USER = "postgres.{project_ref}"
DB_PASSWORD = "your-password"
```

### 자동 배포

- `main` 브랜치 push 시 **자동 재배포**
- `requirements.txt` 변경 시 패키지 재설치 (3~5분 소요)
- 코드만 변경 시 1~2분 소요

---

## 로컬 크롤링 (macOS launchd)

> 커뮤니티 크롤러는 로컬 Mac Mini에서 실행합니다.
> - GitHub Actions cron은 무료 플랜에서 수십분~수시간 지연이 발생하여 정확한 주기 실행이 불가
> - 에펨코리아는 GitHub Actions IP(미국 데이터센터)를 차단하여 로컬에서만 크롤링 가능

### plist 파일

```
~/Library/LaunchAgents/
├── com.humanindex.mlbpark-crawler.plist    # MLBPark 수집만 (30분)
├── com.humanindex.clien-crawler.plist      # 클리앙 수집만 (30분)
├── com.humanindex.fmkorea-crawler.plist    # 에펨코리아 수집만 (30분)
├── com.humanindex.analyzer.plist           # 미분석 게시글 종목 추출 (15분)
└── com.humanindex.stats-updater.plist      # 오늘/어제 통계 갱신 (매일 00:10)
```

### 관리 명령어

```bash
# 등록 (예시)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.humanindex.mlbpark-crawler.plist

# 해제 (예시)
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.humanindex.mlbpark-crawler.plist

# 상태 확인
launchctl list | grep humanindex

# 로그 확인
tail -f ~/Dev/Suyeongpark/human-index/logs/fmkorea_launchd_err.log
```

커뮤니티별 launchd는 `daily_worker.py --community <name> --crawl-only`로 수집만 수행합니다.
후처리는 `--analyze-only`, `--stats-only` 작업이 별도 주기로 실행합니다.

### 시스템 잠자기 비활성화

launchd가 안정적으로 동작하려면 시스템 잠자기를 꺼야 합니다:
```bash
sudo pmset -c sleep 0
```

### 에펨코리아 요청 안정화

커뮤니티 크롤러는 `requests.Session()`으로 쿠키/연결을 유지하고, 요청마다 브라우저형 헤더와 `Referer`를 설정합니다. 필요하면 launchd 환경변수에 아래 값을 추가할 수 있습니다.

| 환경변수 | 설명 |
|----------|------|
| `FMKOREA_COOKIE` | 브라우저에서 로그인/방문 후 확인한 쿠키 문자열 |
| `FMKOREA_USER_AGENT` | 쿠키를 가져온 브라우저의 User-Agent |

쿠키는 계정 정보와 연결될 수 있으므로 저장소에 커밋하지 말고, 로컬 launchd 환경변수나 비밀 설정으로만 관리합니다.

> GitHub Actions와 로컬 launchd가 동시에 돌아도 `source_url` 기준 `ON CONFLICT DO NOTHING`으로 중복 데이터가 발생하지 않습니다.

---

## DB 접속 우선순위

### 스크립트 (`scripts/db_config.py`)

1. `.streamlit/secrets.toml` (로컬 개발)
2. 환경변수 (`DB_HOST` 등) (GitHub Actions, launchd)
3. 기본값 (`localhost`) (폴백)

### 대시보드 (`lib/shared.py`)

1. Streamlit secrets (`st.secrets["database"]`) (Streamlit Cloud)
2. 환경변수 (로컬 개발)
3. 기본값 (`localhost`)

---

## 무료 사용량

| 서비스 | 무료 한도 | 월 예상 사용량 |
|--------|----------|-------------|
| **GitHub Actions** | 2,000분/월 | ~120분 (리포트+뉴스만) |
| **Supabase** | DB 500MB, API 무제한 | ~50MB |
| **Streamlit Cloud** | 앱 1개, 1GB RAM | 충분 |

> **주의**: Supabase 무료 플랜은 7일 미접속 시 DB 일시정지 가능. 크롤러가 상시 접속하므로 정지될 일 없음.

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| GitHub Actions 크롤러 실패 | DB 접속 정보 오류 | Repository secrets 확인 (특히 `DB_USER` 형식) |
| 에펨코리아 0건 수집 | GitHub Actions IP 차단 | 로컬 launchd로만 실행 (필수) |
| Streamlit Cloud 에러 | 패키지 호환성 | `requirements.txt` 확인, `.python-version` = 3.11 |
| 로컬 launchd 미실행 | Mac 잠자기 모드 | `sudo pmset -c sleep 0` |
| 데이터 중복 | - | `source_url` 유니크 제약으로 자동 방지 |
| cron 지연 (±20분) | GitHub Actions 특성 | 정상 동작, 정확한 타이밍 불필요 |
