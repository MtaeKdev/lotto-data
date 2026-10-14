# lotto-data

로또 6/45 추첨 결과를 JSON으로 모아 두는 저장소입니다. Lotto app(Android)이 이 파일만 읽습니다.

- `data/latest.json`: 최신 회차 1건
- `data/lotto-all.json`: 1회차부터 전체 (회차 내림차순)

GitHub Actions(`.github/workflows/collect.yml`)가 매주 토요일 21:10·21:40, 일요일 09:10(KST)에 새 회차만 수집합니다.

당첨 정보 출처: 동행복권 공개 추첨 결과. 이 저장소와 앱은 동행복권과 관련 없는 비공식 프로젝트이며, 정확한 당첨 여부는 판매점 또는 동행복권에서 확인하세요.
