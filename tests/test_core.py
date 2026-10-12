import pandas as pd
from pipeline.core import compute_signals, signal_state, forward_test

def fixture():
    dates=pd.bdate_range('2026-01-01',periods=55)
    d=pd.DataFrame({'open':[100]*55,'high':[102]*55,'low':[98]*55,'close':[100]*55,'volume':[100]*55,'turnover':[11_000_000_000]*55},index=dates)
    d.iloc[30,d.columns.get_loc('volume')]=400
    return d

def test_prior_20_only():
    d=compute_signals(fixture())
    assert d.iloc[30]['volume_ratio']==4
    assert d.iloc[30]['signal']
    assert d.iloc[0:20]['signal'].sum()==0

def test_forward_and_status():
    d=compute_signals(fixture())
    assert signal_state(d,30,35)['status']=='가격 유지'
    assert forward_test(d)['5']['sample_size']==1

def test_excludes_incomplete_outcome():
    d=fixture(); d.iloc[-1,d.columns.get_loc('volume')]=500
    result=forward_test(compute_signals(d))
    assert result['5']['sample_size']==1
