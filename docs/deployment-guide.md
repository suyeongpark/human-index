# Human Index - 클라우드 배포 가이드

> 로컬 환경에서 Supabase + Streamlit Community Cloud로 이전하여 어디서든 접속 가능한 대시보드를 구축하는 가이드

## 전체 아키텍처

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────────┐
│   Mac (로컬)     │         │  Supabase (무료) │         │ Streamlit Cloud(무료)│
│                 │  INSERT  │                 │  SELECT  │                     │
│ daily_worker.py ├────────→│  PostgreSQL DB  │←────────┤  app.py 대시보드     │
│ crawl_hankyung  │         │  (500MB 무료)    │         │                     │
│                 │         │                 │         │  https://xxx.        │
│ launchd 스케줄   │         │  항상 켜져있음    │         │  streamlit.app      │
└─────────────────┘         └─────────────────┘         └─────────────────────┘
    매일 09:00/18:30              클라우드 DB                어디서든 접속 가능
```

---

## 체크리스트

- [ ] **Phase 1**: Supabase 프로젝트 생성 & DB 설정
- [ ] **Phase 2**: 로컬 DB → Supabase 데이터 마이그레이션
- [ ] **Phase 3**: 코드 수정 (DB 접속 정보 분리)
- [ ] **Phase 4**: 크롤러 동작 확인 (Supabase 대상)
- [ ] **Phase 5**: Streamlit Cloud 배포
- [ ] **Phase 6**: 최종 검증 & 로컬 정리

---

## Phase 1: Supabase 프로젝트 생성

### 1-1. 가입 및 프로젝트 생성

1. [supabase.com](https://supabase.com) 접속 → GitHub 계정으로 가입
2. **New Project** 클릭
   - Organization: 본인 계정
   - Project name: `human-index`
   - Database Password: **안전한 비밀번호 설정** (메모해둘 것)
   - Region: **South Korea (Seoul)** — 한국 리전이 없으면 Northeast Asia (Tokyo)
3. 프로젝트 생성 완료까지 약 1~2분 대기

### 1-2. DB 접속 정보 확인

1. Supabase 대시보드 → **Settings** → **Database**
2. **Connection string** 섹션에서 확인:
   - Host: `db.xxxxxxxxxxxx.supabase.co`
   - Port: `5432`
   - Database: `postgres`
   - User: `postgres`
   - Password: 프로젝트 생성 시 설정한 비밀번호

> [!IMPORTANT]
> 이 정보를 메모해두세요. Phase 3에서 사용합니다.

### 1-3. 테이블 생성

Supabase 대시보드 → **SQL Editor** 에서 `docs/init-db.sql` 내용을 실행합니다.

또는 로컬 터미널에서:

```bash
psql "postgresql://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres" \
  -f docs/init-db.sql
```

---

## Phase 2: 데이터 마이그레이션

### 2-1. 로컬 DB 덤프

```bash
# 로컬 PostgreSQL 데이터를 SQL 파일로 내보내기
pg_dump -h localhost -U $(whoami) -d human_index \
  --data-only --inserts \
  -t communities \
  -t tickers \
  -t posts \
  -t post_mentions \
  -t mention_daily_stats \
  -t mention_trend_alerts \
  -t expert_sources \
  -t expert_articles \
  -t expert_article_mentions \
  > data_dump.sql
```

### 2-2. Supabase에 데이터 복원

```bash
psql "postgresql://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres" \
  -f data_dump.sql
```

### 2-3. 데이터 검증

```bash
# 로컬 건수 확인
psql -d human_index -c "SELECT 'posts' as t, COUNT(*) FROM posts UNION ALL SELECT 'tickers', COUNT(*) FROM tickers UNION ALL SELECT 'expert_articles', COUNT(*) FROM expert_articles;"

# Supabase 건수 확인 (동일해야 함)
psql "postgresql://postgres:<PASSWORD>@db.<PROJECT_REF>.supabase.co:5432/postgres" \
  -c "SELECT 'posts' as t, COUNT(*) FROM posts UNION ALL SELECT 'tickers', COUNT(*) FROM tickers UNION ALL SELECT 'expert_articles', COUNT(*) FROM expert_articles;"
```

---

## Phase 3: 코드 수정

### 3-1. 환경변수 기반 DB 접속으로 변경

`lib/shared.py`의 DB_CONFIG를 환경변수에서 읽도록 수정:

```python
import os

DB_CONFIG = {
    "dbname": os.environ.get("DB_NAME", "human_index"),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", ""),
    "password": os.environ.get("DB_PASSWORD", ""),
}
```

> [!TIP]
> 로컬에서는 환경변수가 없으면 기존 값(localhost)을 사용하므로 호환성이 유지됩니다.

### 3-2. Streamlit secrets 설정 파일 생성

```bash
mkdir -p .streamlit
```

`.streamlit/secrets.toml` (로컬 테스트용, **git에 커밋하지 않음**):

```toml
[database]
DB_NAME = "postgres"
DB_HOST = "db.xxxxxxxxxxxx.supabase.co"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "your-password-here"
```

### 3-3. .gitignore에 secrets 추가

```
.streamlit/secrets.toml
```

### 3-4. requirements.txt 생성

```
streamlit
psycopg2-binary
pandas
```

---

## Phase 4: 크롤러 동작 확인

### 4-1. 크롤러 스크립트의 DB 접속도 환경변수화

각 스크립트(`scripts/daily_worker.py`, `scripts/crawl_hankyung.py` 등)의 DB 접속 부분을 동일하게 환경변수로 수정합니다.

### 4-2. 환경변수 설정 (로컬 Mac)

`~/.zshrc`에 추가:

```bash
export DB_NAME="postgres"
export DB_HOST="db.xxxxxxxxxxxx.supabase.co"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="your-password-here"
```

```bash
source ~/.zshrc
```

### 4-3. 테스트 실행

```bash
# 크롤러 테스트 (소량)
python scripts/daily_worker.py

# 대시보드 테스트 (Supabase 연결 확인)
streamlit run app.py
```

### 4-4. launchd plist 업데이트

plist 파일에 환경변수를 추가하거나, 스크립트 내부에서 `.env` 파일을 읽도록 수정합니다.

---

## Phase 5: Streamlit Cloud 배포

### 5-1. GitHub 리포지토리 push

```bash
git push origin main
```

### 5-2. Streamlit Cloud 앱 생성

1. [share.streamlit.io](https://share.streamlit.io) 접속 → GitHub 로그인
2. **New app** 클릭
3. 설정:
   - Repository: `Suyeongpark/human-index`
   - Branch: `main`
   - Main file path: `app.py`
4. **Advanced settings** → **Secrets** 에 DB 접속 정보 입력:

```toml
[database]
DB_NAME = "postgres"
DB_HOST = "db.xxxxxxxxxxxx.supabase.co"
DB_PORT = 5432
DB_USER = "postgres"
DB_PASSWORD = "your-password-here"
```

5. **Deploy** 클릭

### 5-3. 배포 확인

- URL: `https://human-index.streamlit.app` (또는 자동 생성된 URL)
- 모든 페이지 정상 동작 확인
- 모바일에서도 접속 확인

---

## Phase 6: 최종 검증 & 정리

### 6-1. 전체 플로우 테스트

```
1. Mac에서 크롤러 실행 → Supabase에 데이터 적재 확인
2. Streamlit Cloud 대시보드에서 새 데이터 반영 확인
3. 모바일/다른 PC에서 접속 확인
```

### 6-2. 로컬 DB 유지 여부 결정

| 선택 | 설명 |
|------|------|
| 유지 | 백업 용도로 로컬 DB도 계속 운영 |
| 제거 | Supabase만 사용, 로컬 PostgreSQL 중단 |

> [!TIP]
> 초기에는 로컬 DB를 백업으로 유지하는 것을 권장합니다.

---

## 무료 사용량 한도

| 서비스 | 무료 한도 | 현재 예상 사용량 |
|--------|----------|----------------|
| **Supabase** | DB 500MB, API 무제한 | ~50MB (충분) |
| **Streamlit Cloud** | 앱 1개, 1GB RAM | 충분 |

> [!WARNING]
> Supabase 무료 플랜은 7일 미접속 시 DB가 일시정지될 수 있습니다.
> 매일 크롤러가 접속하므로 정지될 일은 없지만, 크롤러가 중단되면 주의가 필요합니다.

---

## 향후 확장

배포 완료 후 추가 가능한 작업:

- [ ] 새 커뮤니티 크롤러 추가 (디시인사이드, 네이버 종토방 등)
- [ ] 새 전문가 소스 추가 (네이버 증권 리서치 등)
- [ ] 커스텀 도메인 연결 (Streamlit Cloud 유료 플랜)
- [ ] Supabase Edge Functions로 크롤러 서버리스 전환 (Mac 의존 제거)
