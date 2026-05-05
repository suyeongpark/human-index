# Human Index — 디자인 가이드

> CSS 설계, 색상 체계, UI 컴포넌트 스타일링 규칙

---

## 스타일 관리

### 파일 구조

```
static/
└── style.css          # 전역 CSS (유일한 스타일 파일)
```

- **모든 스타일은 `static/style.css` 한 파일에서 관리**
- `app.py`에서 `Path.read_text()`로 읽어 `<style>` 태그에 주입
- 페이지 모듈에서 인라인 스타일 사용 금지 → CSS 클래스 사용

### CSS 로딩 방식

```python
# app.py
from pathlib import Path
_css = (Path(__file__).parent / "static" / "style.css").read_text()
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)
```

---

## 색상 체계

### 기본 색상

| 용도 | 색상 | HEX |
|------|------|-----|
| 긍정 / Buy | 🔵 파란색 | `#4A90D9` |
| 부정 / Sell | 🔴 빨간색 | `#E74C3C` |
| 중립 / Hold | ⚪ 회색 | `#95A5A6` |
| 전체 | 다크 | `#2C3E50` |

### 텍스트 색상

| 용도 | HEX |
|------|-----|
| 페이지 타이틀 | `#1a1a2e` |
| 서브 헤더 | `#1e293b` |
| 캡션 / 보조 텍스트 | `#64748b` |
| 페이지네이션 현재 페이지 | `#1e293b` (bold) |
| 구분선 | `#e2e8f0` |

### 사이드바 색상

| 용도 | 값 |
|------|-----|
| 배경 | `linear-gradient(180deg, #0a0e1a → #111827 → #0d1117)` |
| 텍스트 (미선택) | `#94a3b8` |
| 텍스트 (선택) | `#93c5fd` |
| 로고 텍스트 | `#e2e8f0` |
| 섹션 헤더 | `#e2e8f0` |
| 선택 배경 | `linear-gradient(135deg, rgba(74,144,217,0.15), rgba(124,58,237,0.1))` |
| 호버 배경 | `rgba(74,144,217,0.08)` |

---

## UI 컴포넌트

### 메트릭 카드

```css
/* 다크 그라데이션 카드, 호버 시 살짝 위로 */
background: linear-gradient(135deg, #1a1a2e, #16213e);
border-radius: 14px;
border: 1px solid rgba(74, 144, 217, 0.2);
```

- 라벨: `#a0a0cc`, 0.85rem
- 값: `#ffffff`, 2rem, bold 700
- 호버: `translateY(-2px)` + 그림자 강화

### 페이지 헤더

| 요소 | 클래스 | 스타일 |
|------|--------|--------|
| 캡션 | `.page-caption` | `#64748b`, 0.9rem |
| 구분선 | `.page-divider` | `#e2e8f0`, 1px |

```python
# 사용법 (shared.py)
page_header("🔬 리포트 대시보드", "증권사 리포트 분석")
```

### 기간 선택 탭 (pill)

```css
/* 비선택 */
background: #f1f5f9;
border-radius: 10px;
color: #64748b;

/* 선택 */
background: #1a1a2e;
color: #ffffff;
font-weight: 600;
```

- 라디오 원형 인디케이터 숨김 (`display: none`)
- 0.2s ease 전환 애니메이션

### 페이지네이션

| 요소 | 클래스 | 스타일 |
|------|--------|--------|
| 정보 | `.pagination-info` | 중앙 정렬, 0.8rem, `#64748b` |
| 버튼 | `button[kind="secondary"]` | 원형 36px, `#e2e8f0` 테두리 |
| 버튼 호버 | - | `#4A90D9` 테두리 + 그림자 |

### 채널 카드 제목

```css
.channel-card-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #334155;
}
```

- 종합 대시보드의 채널별 TOP 10 차트 상단에 사용

---

## 타이포그래피

### 폰트

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
font-family: 'Inter', -apple-system, sans-serif;
```

### 크기 계층

| 용도 | 크기 | 굵기 |
|------|------|------|
| 메트릭 값 | 2rem | 700 |
| 페이지 타이틀 (h1) | Streamlit 기본 | 700 |
| 서브헤더 (h2/h3) | Streamlit 기본 | 600 |
| 채널 카드 제목 | 1.05rem | 600 |
| 사이드바 섹션 헤더 | 1rem | 600 |
| 사이드바 메뉴 | 0.92rem | 400/500 |
| 페이지 캡션 | 0.9rem | 400 |
| 메트릭 라벨 | 0.85rem | 500 |
| 기간 탭 텍스트 | 0.82rem | 500 |
| 페이지네이션 | 0.8rem | 400 |
| 로고 서브텍스트 | 0.7rem | 400 |
| 사이드바 푸터 | 0.65rem | 400 |

---

## 새 스타일 추가 규칙

1. **`static/style.css`에서만 스타일 정의** — 페이지 모듈에서 `style="..."` 금지
2. **새 UI 패턴 필요 시**: `shared.py`에 헬퍼 함수 추가 + `style.css`에 CSS 클래스 추가
3. **Streamlit 위젯 커스터마이징**: `[data-testid="..."]` 셀렉터 사용
4. **색상 변경 시**: 상단 색상 체계 표 참조, 일관성 유지
5. **전환 효과**: `transition: all 0.2s ease` 통일
