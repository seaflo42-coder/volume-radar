# 거래량 레이더

KOSPI/KOSDAQ 거래량 이상 신호 관찰 웹 앱입니다.

- 직전 20거래일 평균 대비 거래량 3배 이상, 등락률 ±3% 이내
- 최근 5거래일 신호 TOP 10, 발견 후 5거래일 추적
- 5/10/20거래일 가격 변화, 종목 차트, CSV
- 출처: 네이버 금융 공개 목록·일봉. 휴장일: exchange_calendars XKRX
- 한국 시간 18시 이전은 직전 거래일 기준, 실시간 시세 아님
- 실제 거래대금·시총 제한 없음. 종가×거래량은 추정치
- 비용·세금·배당 미반영. 현재 상장 목록의 생존자 편향과 중복 신호 등 한계 존재
- 가격 변화는 매매전략 수익률이 아니며 매수·매도 추천이 아닙니다.

## 로컬 실행

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pipeline.build
python3 -m http.server 8000 --directory web
```

데이터 수집 실패 시 이전 정상 스냅샷을 유지하고 실패 상태를 표시합니다. 공개 데이터 제공처 구조와 접근 정책 변경으로 조회가 중단될 수 있습니다.

## 배포

GitHub Pages의 Source를 GitHub Actions로 설정한 뒤 Market snapshot and Pages 워크플로를 수동 실행합니다. 기본 배포는 검증된 저장 시세를 게시합니다. refresh_data를 선택하면 전체 시세를 먼저 재수집합니다. 예약 실행은 기본 비활성입니다. 표준 Ubuntu runner를 사용하며 배포 산출물은 1일 보관합니다.
