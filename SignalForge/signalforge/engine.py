from __future__ import annotations
import numpy as np
import pandas as pd
from .config import LONG_THRESHOLD, SHORT_THRESHOLD, COST_BPS

def atr(df: pd.DataFrame, n: int = 14) -> float:
    tr = pd.concat([(df.high-df.low), (df.high-df.close.shift()).abs(), (df.low-df.close.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1/n, adjust=False).mean().iloc[-1])

def hurst(close: pd.Series) -> float:
    x = np.asarray(close.dropna())[-300:]
    if len(x) < 40: return .5
    lags = np.arange(2, min(40, len(x)//2)); tau = [np.std(x[l:]-x[:-l]) for l in lags]
    return float(np.clip(np.polyfit(np.log(lags), np.log(np.maximum(tau, 1e-12)), 1)[0], .1, .9))

def features(df: pd.DataFrame) -> dict:
    close = df.close; ret = close.pct_change(); vol = ret.ewm(span=20, adjust=False).std().iloc[-1]
    ema20, ema100 = close.ewm(span=20,adjust=False).mean().iloc[-1], close.ewm(span=100,adjust=False).mean().iloc[-1]
    trend = np.tanh((ema20/ema100-1)/max(vol,1e-8))
    momentum = np.tanh(ret.rolling(min(60,len(ret)), min_periods=10).sum().iloc[-1]/max(vol*np.sqrt(60),1e-8))
    z = (close.iloc[-1]-close.rolling(40).mean().iloc[-1])/max(close.rolling(40).std().iloc[-1],1e-8)
    stretch = -np.tanh(z/2)
    # pressure proxy: positively rewarded when recent returns are stable and directional.
    rsq = float(np.corrcoef(np.arange(30), close.tail(30))[0,1]**2) if len(close)>=30 else 0
    liquidity = float(np.tanh(ret.tail(20).mean()/max(vol,1e-8))*rsq)
    return {"trend":float(trend),"momentum":float(momentum),"stretch":float(stretch),"liquidity":liquidity,"volatility":float(vol),"atr":atr(df),"hurst":hurst(close),"zscore":float(z),"r_squared":rsq}

def score(feature: dict, weights: dict) -> dict:
    h = feature["hurst"]; adjusted = weights.copy()
    if h > .55: adjusted["trend"] *= 1.2; adjusted["momentum"] *= 1.2
    elif h < .45: adjusted["stretch"] *= 1.35
    total = sum(adjusted.values()); adjusted = {k:v/total for k,v in adjusted.items()}
    contrib = {k: adjusted[k]*feature[k] for k in adjusted}
    composite = float(np.clip(sum(contrib.values()), -1, 1))
    direction = "LONG" if composite > LONG_THRESHOLD else "SHORT" if composite < SHORT_THRESHOLD else "FLAT"
    return {"score":composite,"direction":direction,"contributions":contrib,"effective_weights":adjusted}

def signal_series(df: pd.DataFrame, weights: dict) -> pd.Series:
    out=[]
    for i in range(len(df)):
        if i < 110: out.append(0); continue
        s=score(features(df.iloc[:i+1]),weights)["score"]; out.append(1 if s>LONG_THRESHOLD else -1 if s<SHORT_THRESHOLD else 0)
    return pd.Series(out,index=df.index)

def walk_forward_backtest(df: pd.DataFrame, weights: dict) -> dict:
    raw = signal_series(df,weights)
    position = raw.shift(1).fillna(0) # REQUIRED: signal at close t, enter next bar
    ret = df.close.pct_change().fillna(0) * position - (position.diff().abs().fillna(0)*COST_BPS/10000)
    split=int(len(df)*.7); oos=ret.iloc[split:]; trades=int(position.diff().abs().sum()/2)
    sharpe=float(np.sqrt(252*24)*oos.mean()/max(oos.std(),1e-12)); tstat=float(oos.mean()/max(oos.std()/np.sqrt(len(oos)),1e-12))
    equity=(1+oos).cumprod(); dd=float((equity/equity.cummax()-1).min()); hit=float((oos[oos!=0]>0).mean()) if (oos!=0).any() else 0.
    rng=np.random.default_rng(99); observed=abs(oos.mean()); perms=[]
    for _ in range(120): perms.append(abs(np.roll(position.iloc[split:].to_numpy(),int(rng.integers(1,max(2,len(oos)-1)))) @ df.close.pct_change().iloc[split:].fillna(0).to_numpy()/max(len(oos),1)))
    p=float((np.array(perms)>=observed).mean())
    verdict="supported" if sharpe>.5 and p<.10 and trades>=20 else "weak" if trades>=10 else "none"
    return {"status":"ok","verdict":verdict,"oos_sharpe":sharpe,"t_stat":tstat,"max_drawdown":dd,"hit_rate":hit,"trade_count":trades,"permutation_p_value":p,"equity":equity,"buy_hold":(1+df.close.pct_change().iloc[split:].fillna(0)).cumprod(),"position":position}

def scenario(df: pd.DataFrame, entry: float, stop: float, target: float, horizon: int = 24) -> dict:
    returns=df.close.pct_change().dropna().tail(500).to_numpy(); rng=np.random.default_rng(42)
    paths=np.exp(np.cumsum(rng.choice(returns,size=(1500,horizon),replace=True),axis=1))*entry
    finals=paths[:,-1]; target_first=((paths>=target).any(1)&~(paths<=stop).any(1)).mean(); stop_first=((paths<=stop).any(1)&~(paths>=target).any(1)).mean()
    return {"status":"ok","bear_5":float(np.quantile(finals,.05)),"base_median":float(np.median(finals)),"bull_95":float(np.quantile(finals,.95)),"probability_up":float((finals>entry).mean()),"one_sigma_move":float(np.std(finals-entry)),"target_first":float(target_first),"stop_first":float(stop_first),"paths":paths[:100]}
