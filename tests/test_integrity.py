from datetime import datetime, date
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from pipeline.provider import expected_date, sessions, KST, parse_history, NaverProvider
from pipeline.core import compute_signals, outcome_rows, summarize, signal_state
from pipeline.build import run, atomic_json


def frame():
    ix=sessions('2026-07-01','2026-10-08')
    d=pd.DataFrame({'open':100.,'high':104.,'low':96.,'close':100.,'volume':100.,'turnover':1_000.},index=ix)
    d.iloc[25,d.columns.get_loc('volume')]=400
    d.iloc[-2,d.columns.get_loc('volume')]=500
    return d


def test_signal_is_causal():
    original=frame()
    for pos in (25,len(original)-2):
        before=compute_signals(original.iloc[:pos+1]).iloc[-1]
        changed=original.copy();changed.iloc[pos+1:]=999999
        after=compute_signals(changed).iloc[pos]
        for col in ['baseline','volume_ratio','change_pct','signal']:
            assert before[col]==after[col]


def test_no_fill_missing_session():
    d=frame();d.iloc[24]=np.nan
    got=compute_signals(d)
    assert not got.iloc[25]['signal']
    assert pd.isna(got.iloc[25]['change_pct'])


def test_zero_baseline_and_short_history_cannot_signal():
    d=frame();d['volume']=0;d.iloc[25,d.columns.get_loc('volume')]=10000
    assert not compute_signals(d)['signal'].any()
    assert not compute_signals(frame().iloc[:20])['signal'].any()


@pytest.mark.parametrize('change',[3,-3])
def test_inclusive_price_threshold(change):
    d=frame();d.iloc[25,d.columns.get_loc('close')]=100+change
    assert compute_signals(d).iloc[25]['signal']


def test_outcomes_exclude_incomplete_and_missing():
    d=compute_signals(frame()); rows=outcome_rows(d)
    assert len(rows)==2
    assert rows[-1]['5'] is None
    d.iloc[30,d.columns.get_loc('close')]=np.nan
    assert summarize(outcome_rows(d))['5']['sample_size']==0


def test_positive_rate_is_strictly_positive():
    result=summarize([{'5':0.0},{'5':5.0},{'5':-2.0},{'5':None}])['5']
    assert result['sample_size']==3
    assert result['win_rate_pct']==33.3
    assert result['pending_or_missing']==1
    assert result['average_return_pct']==1.0


@pytest.mark.parametrize('stamp,expected',[
    ('2026-10-12T17:59:59+09:00','2026-10-08'),
    ('2026-10-12T18:00:00+09:00','2026-10-12'),
    ('2026-10-09T20:00:00+09:00','2026-10-08'),
    ('2026-10-11T23:00:00+09:00','2026-10-08'),
    ('2026-10-06T07:45:00+09:00','2026-10-02'),
])
def test_korea_holidays_and_cutoff(stamp,expected):
    assert str(expected_date(datetime.fromisoformat(stamp)))==expected


def raw(rows):
    return repr([['날짜','시가','고가','저가','종가','거래량','외국인소진율']]+rows)


def test_parser_drops_future_and_aligns_missing_sessions():
    d=parse_history(raw([['20261006',100,110,90,100,100,0],['20261008',100,110,90,100,100,0],['20261012',200,210,190,200,10000,0]]),date(2026,10,8))
    assert list(d.index.strftime('%Y%m%d'))==['20261006','20261007','20261008']
    assert pd.isna(d.loc['2026-10-07','close'])


@pytest.mark.parametrize('rows',[
    [['20261009',100,110,90,100,100,0]],
    [['20261008',100,90,80,100,100,0]],
    [['20261008',100,110,90,100,-1,0]],
    [['20261008',100,110,90,100,100,0]]*2,
])
def test_rejects_bad_provider_rows(rows):
    with pytest.raises(ValueError):parse_history(raw(rows),date(2026,10,9))


class FakeProvider:
    evidence=[]
    def __init__(self,d=None):self.d=frame() if d is None else d
    def universe(self):return {'005930':{'ticker':'005930','name':'테스트 전용 가상 종목','market':'KOSPI','stock_type':'ordinary'}},{'KOSPI':1,'KOSDAQ':0}
    def history(self,*args):return self.d.copy()


NOW=datetime(2026,10,12,17,tzinfo=KST)


def test_snapshot_persists_signal_and_is_repeatable(tmp_path):
    first=run(FakeProvider(),tmp_path,NOW)
    assert len(first['legacy_top10'])==1
    assert first['top10']==[]  # Low-liquidity signals remain in history but not the default list.
    assert first['meta']['market_date']=='2026-10-08'
    assert len(first['signals'])==2
    d=frame();d['volume']=100
    second=run(FakeProvider(d),tmp_path,NOW)
    assert len(second['signals'])==2
    assert len(second['tracking'])==1
    assert second['signals'][0]['first_seen_at']==first['signals'][0]['first_seen_at']
    assert second['backtest']['5']['sample_size']==1


def test_collection_failure_preserves_last_good_snapshot(tmp_path):
    run(FakeProvider(),tmp_path,NOW)
    before=(tmp_path/'latest.json').read_bytes()
    d=frame();d.iloc[-1]=np.nan
    with pytest.raises(RuntimeError):run(FakeProvider(d),tmp_path,NOW)
    assert (tmp_path/'latest.json').read_bytes()==before
    assert json.loads((tmp_path/'status.json').read_text())['state']=='error'


def test_invalid_json_cannot_destroy_existing_snapshot(tmp_path):
    path=tmp_path/'latest.json';atomic_json(path,{'ok':True})
    with pytest.raises(ValueError):atomic_json(path,{'bad':float('nan')})
    assert json.loads(path.read_text())=={'ok':True}


def test_finalized_outcome_survives_rolling_history_window(tmp_path):
    first=run(FakeProvider(),tmp_path,NOW)
    old=first['signals'][0]
    assert old['20']==0
    # A subsequent window begins after this old outcome; preserve the measured value.
    d=frame().iloc[50:].copy()
    second=run(FakeProvider(d),tmp_path,NOW)
    saved=next(r for r in second['signals'] if r['signal_date']==old['signal_date'])
    assert saved['20']==0


def test_zero_current_price_is_not_ranked(tmp_path):
    d=frame();d.iloc[-1,d.columns.get_loc('close')]=0
    result=run(FakeProvider(d),tmp_path,NOW)
    assert result['top10']==[]
    assert result['tracking'][0]['status']=='시세 확인 필요'
    assert result['tracking'][0]['since_signal_pct'] is None


def test_missing_horizon_does_not_shift_to_next_quote():
    d=compute_signals(frame())
    d.iloc[30,d.columns.get_loc('close')]=np.nan
    d.iloc[31,d.columns.get_loc('close')]=999
    assert outcome_rows(d)[0]['5'] is None


def test_revised_base_is_not_mixed_with_new_prices(tmp_path):
    first=run(FakeProvider(),tmp_path,NOW)
    d=frame();d[['open','high','low','close']]/=2
    second=run(FakeProvider(d),tmp_path,NOW)
    assert second['top10']==[]
    assert second['tracking'][0]['status']=='가격 기준 변경'
    assert second['tracking'][0]['since_signal_pct'] is None
    assert second['meta']['price_revision_count']==2
    assert second['signals'][0]['20']==first['signals'][0]['20']


def test_universe_reconciles_live_reordering_and_keeps_alphanumeric(tmp_path):
    class ListProvider(NaverProvider):
        def __init__(self):super().__init__(tmp_path);self.pass_no={'KOSPI':0,'KOSDAQ':0}
        def get(self,url,params):
            market=url.split('/')[-1];page=params['page'];size=800 if market=='KOSPI' else 1300
            if page==1:self.pass_no[market]+=1
            prefix=0 if market=='KOSPI' else 10000
            rows=[{'itemCode':f'{prefix+i:06d}','stockName':f'테스트{i}','stockEndType':'stock'} for i in range(size)]
            rows[0]['itemCode']='0009K0' if market=='KOSDAQ' else '0126Z0'
            if self.pass_no[market]==1 and page==2:rows[100]=rows[99]
            return json.dumps({'totalCount':size,'stocks':rows[(page-1)*100:page*100]})
    provider=ListProvider();universe,counts=provider.universe()
    assert len(universe)==2100
    assert '0009K0' in universe and '0126Z0' in universe
    assert provider.pass_no=={'KOSPI':2,'KOSDAQ':2}
