"""동행복권 로또 6/45 추첨 결과를 data/*.json으로 수집한다.

- 표준 라이브러리만 사용 (GitHub Actions에서 설치 없이 실행).
- 한 번 요청하면 요청 회차 주변 최대 10회차가 함께 온다. 이미 가진 최신 회차부터
  요청해 그 주변 회차의 값(일요일 확정 당첨금 등)을 갱신하고, 새 회차가 없을 때까지 이어서 받는다.
- 중간에 실패하면 그때까지 받은 데이터를 저장한 뒤 실패 코드로 끝난다.
"""
import datetime
import json
import os
import pathlib
import sys
import time
import urllib.request

URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do?srchDir=center&srchLtEpsd={}"
REPO = os.environ.get("GITHUB_REPOSITORY", "MtaeKdev/lotto-data")
UA = f"lotto-data-collector/1.0 (+https://github.com/{REPO})"
ALL = pathlib.Path("data/lotto-all.json")
LATEST = pathlib.Path("data/latest.json")
KST = datetime.timezone(datetime.timedelta(hours=9))
SCHEMA_VERSION = 1
DELAY_SEC = float(os.environ.get("COLLECT_DELAY_SEC", "1.5"))  # 서버 부담 최소화
RETRIES = 3


def fetch_window(rnd):
    """rnd 주변 회차들을 {회차: 원본 항목}으로 돌려준다. 추첨 전 회차는 제외."""
    req = urllib.request.Request(URL.format(rnd), headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                items = (json.load(r).get("data") or {}).get("list") or []
            return {int(i["ltEpsd"]): i for i in items if i.get("tm1WnNo")}
        except Exception as e:  # 네트워크·형식 오류 모두 재시도
            if attempt == RETRIES:
                raise
            print(f"retry {attempt} for round {rnd}: {e}", file=sys.stderr)
            time.sleep(5 * attempt)


def convert(item):
    """원본 항목 → 앱 계약 JSON. 형식이 이상하면 ValueError."""
    rnd = int(item["ltEpsd"])
    ymd = str(item["ltRflYmd"])
    numbers = sorted(int(item[f"tm{k}WnNo"]) for k in range(1, 7))
    bonus = int(item["bnsWnNo"])
    if len(set(numbers)) != 6 or not all(1 <= n <= 45 for n in numbers + [bonus]) or bonus in numbers:
        raise ValueError(f"round {rnd}: invalid numbers {numbers} + {bonus}")

    prizes = []
    for n in range(1, 6):
        winners = int(item.get(f"rnk{n}WnNope") or 0)
        amount = int(item.get(f"rnk{n}WnAmt") or 0)
        total = int(item.get(f"rnk{n}SumWnAmt") or 0)
        if winners == 0:
            total = 0  # 1등 없음(이월) 회차는 원본에 이월 금액이 들어 있다
        elif total == 0:
            total = winners * amount  # 초기 회차는 원본에 총액이 비어 있다
        prizes.append({"rank": n, "winners": winners, "amount": amount, "total": total})

    d = {
        "round": rnd,
        "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
        "numbers": numbers,
        "bonus": bonus,
        "totalSales": int(item.get("wholEpsdSumNtslAmt") or 0),
        "prizes": prizes,
    }
    # winType0은 모든 회차에서 0이라 판단에 쓸 수 없다.
    # 자동+수동+반자동 합이 1등 인원과 같을 때만 구매 방식 데이터가 있는 것으로 본다.
    auto, manual, semi = (int(item.get(f"winType{k}") or 0) for k in (1, 2, 3))
    if prizes[0]["winners"] > 0 and auto + manual + semi == prizes[0]["winners"]:
        d["firstWinType"] = {"auto": auto, "manual": manual, "semiAuto": semi}
    return d


def save(draws):
    ordered = sorted(draws.values(), key=lambda d: d["round"], reverse=True)
    db = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": datetime.datetime.now(KST).isoformat(timespec="seconds"),
        "latestRound": ordered[0]["round"],
        "draws": ordered,
    }
    ALL.parent.mkdir(exist_ok=True)
    ALL.write_text(json.dumps(db, ensure_ascii=False, separators=(",", ":")), "utf-8")
    LATEST.write_text(json.dumps({**db, "draws": ordered[:1]}, ensure_ascii=False), "utf-8")


def main():
    draws = {}
    if ALL.exists():
        draws = {d["round"]: d for d in json.loads(ALL.read_text("utf-8"))["draws"]}
    added = updated = 0
    rnd = max(draws, default=1)
    try:
        while True:
            window = fetch_window(rnd)
            for r, item in sorted(window.items()):
                d = convert(item)
                if r not in draws:
                    added += 1
                elif draws[r] != d:
                    updated += 1
                else:
                    continue
                draws[r] = d
            nxt = max(draws, default=0) + 1
            # 응답은 요청 회차 뒤로 4회차 이상을 담는다. 그보다 적으면 최신 회차까지 받은 것이다.
            # (주간 실행은 요청 1회로 끝난다. Actions에서는 연속 요청이 끊기므로 요청 수를 최소로.)
            if nxt <= rnd or not window or max(window) < rnd + 4:
                break
            rnd = nxt
            time.sleep(DELAY_SEC)
    finally:
        if added or updated:
            save(draws)
        print(f"added {added}, updated {updated}, latest {max(draws, default=0)}")

    # 빠진 회차가 있으면 실패로 표시해 메일 알림을 받는다
    missing = [r for r in range(1, max(draws, default=0) + 1) if r not in draws]
    if missing:
        sys.exit(f"missing rounds: {missing[:20]}")


if __name__ == "__main__":
    main()
