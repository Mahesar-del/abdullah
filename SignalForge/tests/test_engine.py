import os
os.environ["SIGNALFORGE_OFFLINE"]="1"
from signalforge.data import synthetic_ohlcv
from signalforge.config import WEIGHTS
from signalforge.engine import score, features, walk_forward_backtest, signal_series, scenario

def test_score_direction_changes_with_weights():
    f={"trend":.9,"momentum":-.7,"stretch":0.,"liquidity":0.,"hurst":.5}
    assert score(f,{"trend":1,"momentum":0,"stretch":0,"liquidity":0})["direction"]=="LONG"
    assert score(f,{"trend":0,"momentum":1,"stretch":0,"liquidity":0})["direction"]=="SHORT"

def test_backtest_uses_next_bar_position():
    df=synthetic_ohlcv(300); raw=signal_series(df,WEIGHTS); b=walk_forward_backtest(df,WEIGHTS)
    assert b["position"].iloc[110] == raw.shift(1).fillna(0).iloc[110]

def test_scenario_probabilities_are_bounded():
    df=synthetic_ohlcv(400); e=float(df.close.iloc[-1]); s=scenario(df,e,e*.98,e*1.03)
    assert 0<=s["target_first"]<=1 and 0<=s["stop_first"]<=1
