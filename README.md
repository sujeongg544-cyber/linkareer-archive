# 링커리어 필독 취업자료 아카이브

링커리어 커뮤니티 [필독 취업자료 게시판](https://community.linkareer.com/job-materials)의
글 제목을 매일 자동 수집해 **맞춤 활동 / 맞춤 채용 / 뉴스 / 대학 꿀팁** 4개 탭으로
모아보는 팀 공유용 대시보드.

- **수집 범위**: 최근 14일치
- **업데이트**: 매일 오전 7시 (KST) 자동
- **각 글**: 제목 + 원문 링크 + 등록일 + 조회/추천 수

---

## 세팅 (처음 한 번만)

### 1. 레포 만들고 파일 올리기
이 폴더 전체를 새 GitHub 레포에 올립니다. (private 레포도 Pages 공유 가능)

```
linkareer-archive/
├── .github/workflows/collect.yml   # 매일 07:00 자동 수집 + 배포
├── scripts/collect.py              # 수집 스크립트
├── docs/
│   ├── index.html                  # 대시보드
│   └── data.json                   # 수집 결과 (자동 갱신)
└── README.md
```

### 2. GitHub Pages 켜기
레포 **Settings → Pages**에서:
- **Source**: `GitHub Actions` 선택

### 3. Actions 권한 확인
레포 **Settings → Actions → General → Workflow permissions**에서:
- **Read and write permissions** 선택 (수집 결과를 커밋해야 함)

### 4. 첫 실행
**Actions 탭 → "링커리어 게시판 수집" → Run workflow** 버튼으로 수동 실행.
1~2분 뒤 Pages URL(`https://<아이디>.github.io/<레포명>/`)에 대시보드가 뜹니다.
이 URL을 팀에 공유하면 끝.

이후엔 매일 오전 7시에 알아서 갱신됩니다.

---

## 동작 방식

- `collect.py`가 게시판을 페이지 순서대로 긁으며 각 글의 **말머리(카테고리)로 직접 분류**합니다.
  (topicId 필터에 의존하지 않아 더 안정적)
- 등록일을 절대 날짜로 변환해 **최근 14일** 글만 남기고, 14일을 벗어나면 자동으로 수집을 멈춥니다.
- 공지 글과 보관 대상 외 카테고리(전체·칼럼 등)는 제외합니다.
- 결과를 `docs/data.json`에 저장하고, 대시보드가 이 파일을 읽어 렌더합니다.
- 수집 결과가 0건이면 기존 데이터를 덮어쓰지 않습니다(사이트 구조 변경 등 사고 방지).

## 설정 바꾸기 (`scripts/collect.py` 상단)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DAYS` | `14` | 보관할 일수 |
| `MAX_PAGES` | `15` | 한 번에 훑을 최대 페이지 수 |
| `CATEGORIES` | 4개 | 수집할 카테고리(말머리). 여기에 `"칼럼": "column"` 식으로 추가 가능 |

업데이트 시각을 바꾸려면 `.github/workflows/collect.yml`의 cron을 수정하세요.
(현재 `0 22 * * *` = UTC 22:00 = KST 07:00)

---

## 마케팅 어드민에 넣고 싶을 때

Pages URL을 어드민 사이드바에 iframe으로 끼우면 됩니다. (오공고 대시보드와 동일 방식)

```html
<iframe src="https://<아이디>.github.io/<레포명>/" style="width:100%;height:100%;border:0;"></iframe>
```
