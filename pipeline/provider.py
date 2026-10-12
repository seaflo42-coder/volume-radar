"""Public Naver Finance adapter. No credential, fabricated fallback, or intraday data."""
from __future__ import annotations
import ast
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import exchange_calendars as xc
import pandas as pd
import requests

KST = ZoneInfo('Asia/Seoul')
CAL = xc.get_calendar('XKRX')
SOURCE = '네이버 금융 공개 일봉 / 시장 종목 목록'


def sessions(start, end):
    return CAL.sessions_in_range(str(start)[:10], str(end)[:10]).tz_localize(None)


def expected_date(now):
    local = now.astimezone(KST)
    cutoff = local.date() if local.hour >= 18 else local.date() - timedelta(days=1)
    return CAL.date_to_session(str(cutoff), direction='previous').date()


def parse_history(text, cutoff):
    try:
        rows = ast.literal_eval(text.strip())
        if rows[0][:6] != ['날짜', '시가', '고가', '저가', '종가', '거래량']:
            raise ValueError('일봉 스키마 변경')
        frame = pd.DataFrame([r[:6] for r in rows[1:]], columns=['date','open','high','low','close','volume'])
        frame.index = pd.to_datetime(frame.pop('date'), format='%Y%m%d', errors='raise')
        if frame.index.duplicated().any():
            raise ValueError('일봉 날짜 중복')
        frame = frame.sort_index().loc[:str(cutoff)]
        for c in frame.columns:
            frame[c] = pd.to_numeric(frame[c], errors='raise')
        if frame.empty or (frame < 0).any().any() or frame.isna().any().any():
            raise ValueError('비어 있거나 잘못된 일봉')
        active = frame['volume'] > 0
        if ((frame.loc[active, 'high'] < frame.loc[active, ['open','close','low']].max(axis=1)) |
            (frame.loc[active, 'low'] > frame.loc[active, ['open','close','high']].min(axis=1))).any():
            raise ValueError('OHLC 범위 오류')
        if not frame.index.isin(sessions(frame.index[0].date(), cutoff)).all():
            raise ValueError('거래일 캘린더와 일봉 불일치')
        # Calendar alignment prevents a missing quote being mistaken for a later session.
        frame = frame.reindex(sessions(frame.index[0].date(), cutoff))
        frame['turnover'] = frame['close'] * frame['volume']
        return frame
    except (ValueError, TypeError, IndexError, SyntaxError) as e:
        raise ValueError(f'일봉 응답 검증 실패: {e}') from e


class NaverProvider:
    def __init__(self, cache: Path, delay=0.35):
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'VolumeRadar/2.0 personal-research', 'Referer':'https://finance.naver.com/'})
        self.last_request = 0.0
        self.evidence = []

    def get(self, url, params=None, cache_key=None):
        path = self.cache / cache_key if cache_key else None
        if path and path.exists():
            cached = path.read_text(encoding='utf-8')
            self.evidence.append({'url':requests.Request('GET',url,params=params).prepare().url, 'sha256':hashlib.sha256(cached.encode()).hexdigest(), 'retrieved_at':datetime.fromtimestamp(path.stat().st_mtime,KST).isoformat(), 'from_cache':True})
            return cached
        error = None
        for attempt in range(3):
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.get(url, params=params, timeout=(8, 25))
                response.raise_for_status()
                result = response.text
                if path:
                    path.write_text(result, encoding='utf-8')
                self.evidence.append({'url':response.url, 'sha256':hashlib.sha256(result.encode()).hexdigest(), 'retrieved_at':datetime.now(KST).isoformat()})
                return result
            except requests.RequestException as exc:
                error = exc
                time.sleep(1 + attempt)
        raise RuntimeError(f'공개 시세 요청 실패: {type(error).__name__}') from error

    def universe(self):
        stocks = {}
        counts = {}
        for market, minimum in [('KOSPI', 700), ('KOSDAQ', 1200)]:
            raw_rows = {}
            total = None
            # The provider sorts a live market-value list. Reconcile repeated passes
            # instead of silently dropping a stock that crossed a page boundary.
            for attempt in range(3):
                page = 1
                while True:
                    payload = json.loads(self.get(f'https://m.stock.naver.com/api/stocks/marketValue/{market}', {'page':page,'pageSize':100}))
                    if total is None:
                        total = payload['totalCount']
                    if total != payload['totalCount']:
                        raise ValueError('수집 중 시장 목록 크기 변경; 다시 실행하세요.')
                    rows = payload['stocks']
                    if not rows:
                        raise ValueError('시장 목록 페이지 누락')
                    for row in rows:
                        raw_rows[row['itemCode']] = row
                    if page * 100 >= total:
                        break
                    page += 1
                    if page > 100:
                        raise ValueError('시장 목록 페이지 제한 초과')
                if len(raw_rows) == total:
                    break
            if len(raw_rows) != total:
                raise ValueError(f'{market} 목록 완전성 확인 실패: {len(raw_rows)}/{total}')
            for code, row in raw_rows.items():
                if row['stockEndType'] == 'stock' and re.fullmatch(r'[0-9A-Z]{6}', code):
                    if code in stocks:
                        raise ValueError('시장 간 종목 중복')
                    stocks[code] = {'ticker':code,'name':row['stockName'],'market':market}
            counts[market] = sum(v['market'] == market for v in stocks.values())
            if counts[market] < minimum:
                raise ValueError(f'{market} 종목 목록 불완전')
        return stocks, counts

    def history(self, ticker, start, end):
        key = f'{ticker}_{start}_{end}.txt'
        raw = self.get('https://api.finance.naver.com/siseJson.naver',
                       {'symbol':ticker,'requestType':'1','startTime':str(start).replace('-',''),
                        'endTime':str(end).replace('-',''),'timeframe':'day'}, key)
        try:
            return parse_history(raw, end)
        except ValueError:
            (self.cache / key).unlink(missing_ok=True)
            raise
