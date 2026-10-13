import numpy as np
import pandas as pd
import pytest
from pipeline.screening import classify, parse_kind, eligible, liquidity_pass, ranked_unique
from pipeline.core import compute_signals, score_parts
from pipeline.provider import NaverProvider
from pipeline.build import run
from tests.test_integrity import FakeProvider, NOW, frame

def test_type_requires_code_market_and_name_agreement():
    listed={'005930':{'name':'삼성전자','market':'KOSPI'},'0041L0':{'name':'하나35호스팩','market':'KOSDAQ'},
            '047040':{'name':'대우','market':'KOSPI'}}
    def type_of(code,name,market='KOSPI'):return classify({'ticker':code,'name':name,'market':market},listed)['stock_type']
    assert type_of('005930','삼성전자')=='ordinary'
    assert type_of('005935','삼성전자우')=='preferred'
    assert type_of('005935','다른회사우')=='unknown'
    assert type_of('047040','대우')=='ordinary'  # A common issuer name ending in 우 is not a preferred share.
    assert type_of('0041L0','하나35호스팩','KOSDAQ')=='spac'
    assert type_of('005930','이름이바뀜')=='unknown'
    assert type_of('005930','삼성전자','KOSDAQ')=='unknown'
    assert type_of('999990','평범한기업')=='unknown'

def test_kind_parser_preserves_alphanumeric_codes_and_rejects_duplicate():
    head='<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th></tr>'
    row='<tr><td>하나35호스팩</td><td>코스닥</td><td>0041L0</td><td>금융</td><td>합병</td></tr>'
    assert parse_kind(head+row+'</table>')['0041L0']['name']=='하나35호스팩'
    with pytest.raises(ValueError):parse_kind(head+row+row+'</table>')
    with pytest.raises(ValueError):parse_kind('<html>error</html>')

def test_classification_failure_is_closed_to_default_list(tmp_path):
    class Broken(NaverProvider):
        def get(self,*args,**kwargs):raise RuntimeError('test network error')
    p=Broken(tmp_path)
    info=p.classify_universe({'005930':{'ticker':'005930','name':'삼성전자','market':'KOSPI'}})
    assert info['005930']['stock_type']=='unknown'
    assert p.classification_status['state']=='error'

def liquid():
    return {'stock_type':'ordinary','turnover_estimate':3e9,'median_turnover20':1e9,
            'current_volume':1,'score_breakdown':{'total':50},'price_revision_detected':False}

def test_liquidity_thresholds_are_inclusive_and_require_both():
    assert eligible(liquid())
    for field in ('turnover_estimate','median_turnover20'):
        d=liquid();d[field]-=1;assert not eligible(d)
        for value in (None,np.nan,float('inf')):
            d[field]=value;assert not liquidity_pass(d)
    for kind in ('spac','preferred','other','unknown'):
        d=liquid();d['stock_type']=kind;assert not eligible(d)
    for field,value in [('price_revision_detected',True),('score_breakdown',None),('current_volume',0)]:
        d=liquid();d[field]=value;assert not eligible(d)

def test_median_excludes_signal_day_and_future_and_is_not_spike_average():
    d=frame();d['turnover']=1e9;d.iloc[3,d.columns.get_loc('turnover')]=100e9
    d.iloc[25,d.columns.get_loc('turnover')]=10e9
    first=compute_signals(d.iloc[:26]).iloc[-1]
    d.iloc[26:]=999999999999
    assert first['median_turnover20']==1e9
    assert compute_signals(d).iloc[25]['median_turnover20']==first['median_turnover20']
    d.iloc[24,d.columns.get_loc('turnover')]=np.nan
    assert pd.isna(compute_signals(d).iloc[25]['median_turnover20'])

def test_score_is_unchanged_at_cap_and_not_a_probability():
    row={'volume_ratio':4.875,'change_pct':0,'close_position':1}
    assert score_parts(row)=={'volume':35,'close_change':25,'close_position':15,'total':75}
    row['volume_ratio']=100
    assert score_parts(row)['total']==75

def test_default_filter_does_not_remove_historical_signals(tmp_path):
    d=frame();d['turnover']=1e9;d.loc[d['volume']>100,'turnover']=3e9
    first=run(FakeProvider(d),tmp_path,NOW)
    assert len(first['top10'])==1
    assert len(first['signals'])==2
    assert first['meta']['default_candidate_count']==1  # Do not pad to 10.
    before={ (r['ticker'],r['signal_date']):(r['first_seen_at'],r['score'],r['signal_close']) for r in first['signals'] }
    d['turnover']=1000
    second=run(FakeProvider(d),tmp_path,NOW)
    assert second['top10']==[] and len(second['legacy_top10'])==1
    assert second['backtest']==first['backtest']
    assert before=={(r['ticker'],r['signal_date']):(r['first_seen_at'],r['score'],r['signal_close']) for r in second['signals']}

def test_rank_deduplicates_after_eligibility_filter():
    rows=[dict(liquid(),ticker='000001',signal_date='2026-10-01',score=70),
          dict(liquid(),ticker='000001',signal_date='2026-10-02',score=60)]
    rows[0]['turnover_estimate']=1000
    result=ranked_unique(r for r in rows if eligible(r))
    assert len(result)==1 and result[0]['score']==60
