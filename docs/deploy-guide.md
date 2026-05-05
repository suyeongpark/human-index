# Human Index — 배포 가이드

> Supabase + Streamlit Cloud + GitHub Actions로 24/7 무중단 시스템 구축

---

## 배포 서비스

| 서비스 | 용도 | URL / 설정 |
|--------|------|-----------|
| **Streamlit Cloud** | 대시보드 | [human-index.streamlit.app](https://human-index-fbsfdag8sk7hcpfedhrm9h.streamlit.app/) |
| **Supabase** | PostgreSQL DB | 서울 리전, Session Pooler 사용 |
| **GitHub Actions** | 크롤러 자동화 | Repository secrets로 DB 접속 |

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
| `.github/workflows/crawl-community.yml` | `0 * * * *` | 매 정시 |
| `.github/workflows/crawl-hankyung.yml` | `30 9 * * 1-5` | 평일 18:30 |
| `.github/workflows/crawl-google-news.yml` | `0 0,6,12,18 * * *` | 09/15/21/03시 |

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

> 에펨코리아는 GitHub Actions IP(미국 데이터센터)를 차단하여 **로컬에서만 크롤링 가능**합니다.

### plist 파일

```
~/Library/LaunchAgents/
└── com.humanindex.fmkorea-crawler.plist   # 에펨코리아 (30분, 필수)
```

### 관리 명령어

```bash
# 등록
launchctl load ~/Library/LaunchAgents/com.humanindex.fmkorea-crawler.plist

# 해제
launchctl unload ~/Library/LaunchAgents/com.humanindex.fmkorea-crawler.plist

# 상태 확인
launchctl list | grep humanindex

# 로그 확인
tail -f ~/Dev/Suyeongpark/human-index/logs/fmkorea_launchd.log
```

### 시스템 잠자기 비활성화

launchd가 안정적으로 동작하려면 시스템 잠자기를 꺼야 합니다:
```bash
sudo pmset -c sleep 0
```

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
| **GitHub Actions** | 2,000분/월 | ~780분 |
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
