"""Signal computation uses only information available at each signal close."""
from __future__ import annotations
import pandas as pd
import numpy as np


def compute_signals(frame, min_turnover=0, volume_multiple=3.0, max_move=3.0):
    d = frame.copy().sort_index()
    if d.index.duplicated().any():
        raise ValueError('중복 거래일')
    for c in ['open','high','low','close','volume','turnover']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['baseline'] = d['volume'].shift(1).rolling(20, min_periods=20).mean()
    d['median_turnover20'] = d['turnover'].shift(1).rolling(20, min_periods=20).median()
    d['volume_ratio'] = d['volume'] / d['baseline'].replace(0, np.nan)
    d['change_pct'] = d['close'].pct_change(fill_method=None) * 100
    d['close_position'] = (d['close']-d['low'])/(d['high']-d['low']).replace(0,np.nan)
    d['signal'] = ((d['volume_ratio'] >= volume_multiple) & (d['change_pct'].abs() <= max_move + 1e-9)
                   & (d['turnover'] >= min_turnover) & (d['close'] > 0) & (d['volume'] > 0))
    return d


def signal_state(d, signal_pos, current_pos):
    base, now = float(d.iloc[signal_pos]['close']), float(d.iloc[current_pos]['close'])
    days = current_pos - signal_pos
    performance = (now / base - 1) * 100 if base > 0 and np.isfinite(now) and now > 0 else None
    if performance is None:
        status = '시세 확인 필요'
    elif days == 0:
        status = '신규 발견'
    else:
        status = '발견일 종가 대비'
    return {'days':days,'since_signal_pct':round(performance,2) if performance is not None else None,'status':status}


def score_signal(row, retention_pct=0.0, days=0):
    return score_parts(row)['total']


def score_parts(row):
    ratio, change = float(row['volume_ratio']), abs(float(row['change_pct']))
    position = float(row.get('close_position',0.5))
    if not np.isfinite(position): position = 0.5
    volume=min(35,max(0,(ratio-3)*8+20)); change_score=max(0,25-change*7); close=max(0,min(15,position*15))
    return {'volume':round(volume,2),'close_change':round(change_score,2),'close_position':round(close,2),
            'total':round(volume+change_score+close,1)}


def outcome_rows(d, horizons=(5,10,20)):
    """Calendar-aligned frames only; no forward fill or not-yet-matured outcomes."""
    results = []
    for pos in np.flatnonzero(d['signal'].to_numpy()):
        row = {'signal_date':str(d.index[pos].date()),'signal_close':float(d.iloc[pos]['close'])}
        for h in horizons:
            value = d.iloc[pos+h]['close'] if pos+h < len(d) else np.nan
            row[str(h)] = round((float(value)/row['signal_close']-1)*100, 6) if pd.notna(value) and value > 0 else None
        results.append(row)
    return results


def summarize(rows, horizons=(5,10,20)):
    result = {}
    for h in horizons:
        values = np.array([r[str(h)] for r in rows if r.get(str(h)) is not None], dtype=float)
        result[str(h)] = {'sample_size':len(values), 'pending_or_missing':len(rows)-len(values),
                          'win_rate_pct':round(float(np.mean(values>0)*100),1) if len(values) else None,
                          'average_return_pct':round(float(values.mean()),2) if len(values) else None,
                          'median_return_pct':round(float(np.median(values)),2) if len(values) else None}
    return result


def forward_test(d, horizons=(5,10,20)):
    return summarize(outcome_rows(d,horizons),horizons)
