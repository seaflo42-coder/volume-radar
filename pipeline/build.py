"""Run `python -m pipeline.build`; failed collection never replaces a good snapshot."""
from __future__ import annotations
import argparse
import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
import uuid
import numpy as np
import pandas as pd
from pipeline.provider import NaverProvider, KST, expected_date, sessions, SOURCE
from pipeline.core import compute_signals, score_signal, signal_state, outcome_rows, summarize

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'web' / 'data'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def read_json(path, default):
    if not path.exists(): return default
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def number(value):
    return round(float(value), 4) if pd.notna(value) and np.isfinite(value) else None


def build(provider, now, data_dir=DATA):
    end = expected_date(now)
    start = end - timedelta(days=240)
    old = read_json(data_dir/'latest.json', {})
    old_ledger = old.get('signals', [])
    universe, counts = provider.universe()
    logging.info('시장 목록 %s / 기준일 %s', counts, end)
    errors, frames, details, new_rows = [], {}, {}, []
    for index, (ticker, info) in enumerate(sorted(universe.items())):
        try:
            d = compute_signals(provider.history(ticker, start, end))
            # Reject stale or missing terminal quote; do not relabel an earlier day as current.
            if d.index[-1].date() != end or pd.isna(d.iloc[-1]['close']):
                raise ValueError('기준 거래일 시세 누락')
            frames[ticker] = d
            for row in outcome_rows(d):
                pos = d.index.get_loc(pd.Timestamp(row['signal_date']))
                at = d.iloc[pos]
                new_rows.append({**info, **row, 'volume_ratio':number(at['volume_ratio']),
                                 'signal_change_pct':number(at['change_pct']),
                                 'turnover_estimate':number(at['turnover']), 'score':score_signal(at),
                                 'first_seen_at':now.isoformat(), 'origin':'reconstructed'})
        except Exception as exc:
            errors.append({'ticker':ticker,'reason':str(exc)[:180]})
        if (index+1) % 100 == 0:
            logging.info('%s/%s 종목 처리 / 오류 %s', index+1,len(universe),len(errors))
    if len(frames)/len(universe) < .98:
        raise RuntimeError(f'데이터 품질 기준 미달: {len(frames)}/{len(universe)} 성공. 이전 정상 데이터 보존.')
    # Persist discovered signals independently from whether they still meet today's rule.
    ledger = {(r['ticker'],r['signal_date']):r for r in old_ledger}
    for row in new_rows:
        key = row['ticker'],row['signal_date']
        if key not in ledger:
            if row['signal_date'] == str(end): row['origin'] = 'observed'
            ledger[key] = row
    tracking = []
    for key, row in ledger.items():
        ticker, signal_date = key
        d = frames.get(ticker)
        days = len(sessions(signal_date, end))-1
        row['days'] = days
        row['last_close'] = None
        row['since_signal_pct'] = None
        row['status'] = '시세 확인 필요'
        row['price_date'] = str(end)
        signal_stamp = pd.Timestamp(signal_date)
        source_base = d.loc[signal_stamp, 'close'] if d is not None and signal_stamp in d.index else None
        revised = source_base is not None and pd.notna(source_base) and not np.isclose(float(source_base),row['signal_close'],rtol=0,atol=.01)
        row['price_revision_detected'] = bool(revised)
        if revised:
            # Never divide a revised/split-adjusted future price by an incompatible saved base.
            row['status'] = '가격 기준 변경'
            if 0 <= days <= 5: tracking.append(row)
            continue
        for h in (5,10,20):
            row.setdefault(str(h), None)
            if d is not None and days >= h:
                target = sessions(signal_date,end)[h]
                value = d.loc[target,'close'] if target in d.index else np.nan
                if pd.notna(value) and value > 0:
                    row[str(h)] = round((float(value)/row['signal_close']-1)*100,6)
        if d is not None:
            close = number(d.iloc[-1]['close'])
            row['last_close'] = close if close and close > 0 else None
            value = (close/row['signal_close']-1)*100 if close and close>0 else None
            row['since_signal_pct'] = round(value,2) if value is not None else None
            row['status'] = ('시세 확인 필요' if value is None else '신규 발견' if days==0 else
                             '가격 이탈' if value < -2 else '가격 유지' if value>=0 else '주의 관찰')
            if 0 <= days <= 5:
                details[ticker] = [{ 'date':str(idx.date()), **{c:number(r[c]) for c in ['open','high','low','close','volume','baseline']}}
                                   for idx,r in d.tail(65).iterrows()]
        if 0 <= days <= 5: tracking.append(row)
    recent = sorted([r for r in tracking if r['days'] < 5 and r['last_close'] is not None],
                    key=lambda r:(r['score'],r['signal_date'],r['ticker']), reverse=True)
    unique = {}
    for r in recent:
        # One stock in TOP 10; highest signal-day score across the five-session window.
        if r['ticker'] not in unique: unique[r['ticker']] = r
    top = list(unique.values())[:10]
    ledger_rows = sorted(ledger.values(),key=lambda r:(r['signal_date'],r['ticker']))
    complete = datetime.now(KST)
    source_times = [r['retrieved_at'] for r in provider.evidence if r.get('retrieved_at')]
    next_dates = sessions(end + timedelta(days=1), end+timedelta(days=35))
    next_due = str(next_dates[0].date())+'T18:00:00+09:00'
    payload = {'meta':{
        'schema_version':2, 'snapshot_id':uuid.uuid4().hex, 'verified':True,
        'market_date':str(end), 'expected_market_date':str(end), 'generated_at':complete.isoformat(),
        'started_at':now.isoformat(), 'oldest_source_retrieval':min(source_times) if source_times else None,
        'newest_source_retrieval':max(source_times) if source_times else None, 'next_update_due':next_due, 'timezone':'Asia/Seoul',
        'data_source':SOURCE, 'source_url':'https://finance.naver.com/',
        'universe_size':len(universe), 'universe_by_market':counts, 'scanned_size':len(frames),
        'eligible_history_size':sum(int(d['baseline'].notna().any()) for d in frames.values()),
        'errors':errors, 'coverage_pct':round(len(frames)/len(universe)*100,2),
        'universe_as_of':now.date().isoformat(), 'signal_count':len(unique),
        'today_signal_count':sum(r['signal_date']==str(end) for r in ledger_rows),
        'price_revision_count':sum(bool(r.get('price_revision_detected')) for r in ledger_rows),
        'tracking_stock_count':len({r['ticker'] for r in tracking}),
        'history_start':str(start), 'history_end':str(end),
        'rules':{'volume_multiple':3,'baseline_sessions':20,'max_abs_change_pct':3,'lookback_sessions':5,'min_turnover':0},
        'turnover_method':'종가 × 거래량 추정치. 실제 거래대금 필터 미적용.',
        'price_policy':'18시 KST 이전에는 직전 거래일 일봉만 사용. 휴장일은 XKRX 캘린더로 확인.',
        'backtest_method':'수집 시점 상장 종목의 전체 신호. 신호일 종가 대비 5·10·20거래일 종가 변화. 거래비용·세금·배당 미반영. 상장폐지 종목 누락에 따른 생존자 편향, 중복 신호 및 제공처 수정주가 영향 존재. 전략 수익률 아님.',
    }, 'top10':top, 'tracking':sorted(tracking,key=lambda r:(r['signal_date'],r['score']),reverse=True),
       'signals':ledger_rows, 'backtest':summarize(ledger_rows), 'charts':details,
       'daily_history':[{'market_date':s, 'count':sum(r['signal_date']==s for r in ledger_rows)} for s in sorted({r['signal_date'] for r in ledger_rows})]}
    # The UI reads one atomic snapshot, so rankings, charts, and outcomes cannot be mixed.
    atomic_json(data_dir/'latest.json',payload)
    atomic_json(data_dir/'status.json',{'state':'ok','attempted_at':complete.isoformat(),'market_date':str(end),'snapshot_id':payload['meta']['snapshot_id']})
    atomic_json(data_dir/'provenance.json',{'source':SOURCE,'requests':provider.evidence,'errors':errors})
    logging.info('완료: %s / TOP %s / 추적 신호 %s / 전체 과거 신호 %s / 누락 %s',end,len(top),len(tracking),len(ledger_rows),len(errors))
    return payload


def run(provider=None, data_dir=DATA, now=None):
    now = now or datetime.now(KST)
    try:
        return build(provider or NaverProvider(ROOT/'.cache'/'naver'), now, data_dir)
    except Exception as exc:
        atomic_json(data_dir/'status.json',{'state':'error','attempted_at':datetime.now(KST).isoformat(),
                                            'message':str(exc)[:400]})
        logging.exception('수집 실패; latest.json 보존')
        raise


if __name__ == '__main__':
    import fcntl
    lock_path = ROOT/'.cache'/'build.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('이미 수집 중입니다. 기존 수집이 끝난 뒤 다시 실행하세요.')
        run()
