#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
링커리어 '필독 취업자료' 게시판 제목 아카이빙 수집기
- 전체 페이지를 긁어 말머리(카테고리)로 4개 탭 분류: 맞춤 활동 / 맞춤 채용 / 뉴스 / 대학 꿀팁
- 최근 N일(기본 14일)만 보관
- 등록일을 절대 날짜로 정규화 (당일 'HH:MM' -> 오늘 날짜, 과거 'YYYY.MM.DD')
- 결과를 docs/data.json 으로 저장 (대시보드가 읽음)

GitHub Actions(또는 로컬)에서 실행. 외부 네트워크가 열린 환경이어야 함.
"""

import json
import re
import sys
import time
import datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

# ----------------------- 설정 -----------------------
BASE = "https://community.linkareer.com/job-materials"
DAYS = 30                 # 최근 며칠치 보관
MIN_VIEWS = 300           # 이 조회수 미만인 글은 제외 (0으로 두면 전부 수집)
MAX_PAGES = 25            # 페이지네이션 안전 상한
STOP_AFTER_OLD = 2        # 연속으로 N페이지 전부 cutoff 이전이면 중단
REQUEST_DELAY = 0.8       # 페이지 간 대기(초) - 서버 부담 최소화
KST = dt.timezone(dt.timedelta(hours=9))

# 보관할 카테고리(말머리) -> 탭 키
CATEGORIES = {
    "맞춤 활동": "activity",
    "맞춤 채용": "recruit",
    "뉴스": "news",
    "대학 꿀팁": "tip",
}

OUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ----------------------- HTML 파서 -----------------------
class RowParser(HTMLParser):
    """
    게시판 테이블의 <tr>을 파싱.
    각 행은 번호 | 말머리 | 제목(a href) | 글쓴이 | 등록일 | 조회 | 추천 | 스크랩 구조.
    셀 텍스트를 순서대로 모으고, 제목 셀에서 a의 href를 함께 캡처한다.
    """

    def __init__(self):
        super().__init__()
        self.rows = []
        self._in_tr = False
        self._cells = []          # 현재 행의 셀 텍스트 리스트
        self._cur_text = []       # 현재 셀 누적 텍스트
        self._in_td = False
        self._cur_href = None     # 현재 행에서 처음 만난 job-materials 링크
        self._in_a = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._in_tr = True
            self._cells = []
            self._cur_href = None
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._cur_text = []
        elif tag == "a" and self._in_td:
            self._in_a = True
            href = dict(attrs).get("href", "")
            # 글 상세 링크만 캡처 (/job-materials/숫자)
            if self._cur_href is None and re.search(r"/job-materials/\d+", href):
                self._cur_href = href

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_a = False
        elif tag == "td" and self._in_td:
            self._in_td = False
            self._cells.append("".join(self._cur_text).strip())
        elif tag == "tr" and self._in_tr:
            self._in_tr = False
            if self._cells:
                self.rows.append((self._cells[:], self._cur_href))

    def handle_data(self, data):
        if self._in_td:
            self._cur_text.append(data)


# ----------------------- 유틸 -----------------------
def fetch(page):
    url = f"{BASE}?page={page}"
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def normalize_date(raw, today):
    """
    등록일 문자열을 date 객체로 변환.
    - 'YYYY.MM.DD'  -> 그 날짜
    - 'HH:MM'       -> 오늘(today)
    - 그 외/빈값     -> None
    """
    raw = (raw or "").strip()
    m = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", raw)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    if re.match(r"^\d{1,2}:\d{2}$", raw):
        return today
    return None


def extract_post_id(href):
    if not href:
        return None
    m = re.search(r"/job-materials/(\d+)", href)
    return int(m.group(1)) if m else None


def clean_title(cells):
    """
    제목 셀 추정: 말머리(카테고리) 바로 다음 셀.
    셀 텍스트에서 'icon-has-image', 꼬리의 댓글수 '(12)' 등 잡음 제거.
    """
    # 말머리 셀 인덱스 찾기
    for i, c in enumerate(cells):
        if c.strip() in CATEGORIES:
            if i + 1 < len(cells):
                t = cells[i + 1]
                t = t.replace("icon-has-image", " ")
                t = re.sub(r"\s+", " ", t).strip()
                # 맨 끝의 '(숫자)' 댓글 카운트 제거
                t = re.sub(r"\s*\(\d+\)\s*$", "", t).strip()
                return t
    return None


def to_int(s):
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else 0


# ----------------------- 메인 수집 -----------------------
def collect():
    today = dt.datetime.now(KST).date()
    cutoff = today - dt.timedelta(days=DAYS - 1)  # today 포함 14일

    seen_ids = set()
    items = []
    consecutive_old_pages = 0

    for page in range(1, MAX_PAGES + 1):
        try:
            html = fetch(page)
        except (URLError, HTTPError) as e:
            print(f"[warn] page {page} fetch 실패: {e}", file=sys.stderr)
            break

        parser = RowParser()
        parser.feed(html)

        page_has_fresh = False
        page_row_count = 0

        for cells, href in parser.rows:
            # 말머리(카테고리)가 보관 대상인지
            cat = next((c.strip() for c in cells if c.strip() in CATEGORIES), None)
            if not cat:
                continue

            # 공지 행 제외: 번호 셀이 '공지'면 스킵
            num_cell = cells[0].strip() if cells else ""
            if num_cell == "공지" or "공지" in num_cell:
                continue

            post_id = extract_post_id(href)
            if post_id is None or post_id in seen_ids:
                continue

            title = clean_title(cells)
            if not title:
                continue

            # 등록일 셀: 날짜/시간 패턴을 가진 셀을 탐색 (인덱스도 기억)
            date_raw = None
            date_idx = -1
            for i, c in enumerate(cells):
                cs = c.strip()
                if re.match(r"^\d{4}\.\d{1,2}\.\d{1,2}$", cs) or re.match(r"^\d{1,2}:\d{2}$", cs):
                    date_raw = cs
                    date_idx = i
                    break
            d = normalize_date(date_raw, today)
            if d is None:
                continue

            page_row_count += 1

            if d < cutoff:
                continue  # 오래된 글은 버림

            # 조회/추천: 반드시 '날짜 셀 이후'의 순수 숫자 셀만 사용.
            # (날짜 앞의 글 번호 8423 등이 조회수로 잘못 잡히는 것을 방지)
            nums = [to_int(c) for c in cells[date_idx + 1:] if re.match(r"^[\d,]+$", c.strip())]
            views = nums[0] if len(nums) >= 1 else 0
            likes = nums[1] if len(nums) >= 2 else 0

            # 최소 조회수 필터 (당일 글은 조회수가 아직 안 쌓였어도 통과시킴)
            if MIN_VIEWS > 0 and views < MIN_VIEWS and d != today:
                continue

            page_has_fresh = True
            seen_ids.add(post_id)

            items.append({
                "id": post_id,
                "category": cat,
                "tab": CATEGORIES[cat],
                "title": title,
                "url": f"https://community.linkareer.com/job-materials/{post_id}",
                "date": d.isoformat(),
                "date_raw": date_raw,
                "views": views,
                "likes": likes,
            })

        print(f"[info] page {page}: rows={page_row_count}, 수집 누적={len(items)}", file=sys.stderr)

        # 이 페이지에 cutoff 이내 글이 하나도 없으면 old 카운트 증가
        if page_row_count > 0 and not page_has_fresh:
            consecutive_old_pages += 1
            if consecutive_old_pages >= STOP_AFTER_OLD:
                print(f"[info] 연속 {STOP_AFTER_OLD}페이지 cutoff 초과 → 중단", file=sys.stderr)
                break
        else:
            consecutive_old_pages = 0

        if page < MAX_PAGES:
            time.sleep(REQUEST_DELAY)

    # 최신순(ID 내림차순 = 등록 최신순) 정렬
    items.sort(key=lambda x: x["id"], reverse=True)

    # 탭별 분류
    tabs = {v: [] for v in CATEGORIES.values()}
    for it in items:
        tabs[it["tab"]].append(it)

    result = {
        "generated_at": dt.datetime.now(KST).isoformat(),
        "generated_date": today.isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "days": DAYS,
        "total": len(items),
        "tab_labels": {
            "activity": "맞춤 활동",
            "recruit": "맞춤 채용",
            "news": "뉴스",
            "tip": "대학 꿀팁",
        },
        "tab_order": ["activity", "recruit", "news", "tip"],
        "counts": {k: len(v) for k, v in tabs.items()},
        "tabs": tabs,
    }
    return result


def main():
    result = collect()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 수집 결과가 비정상적으로 0이면, 기존 데이터를 덮어쓰지 않도록 방어
    if result["total"] == 0 and OUT_PATH.exists():
        print("[error] 수집 0건 → 기존 data.json 유지 (덮어쓰기 안 함)", file=sys.stderr)
        sys.exit(1)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[done] 총 {result['total']}건 저장 → {OUT_PATH}")
    print(f"       탭별: {result['counts']}")


if __name__ == "__main__":
    main()
