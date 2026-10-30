# Strategy update — closed-trend-reclaim-v1

Yeh paper research strategy hai. Is update se profitability ya institutional-grade execution establish nahi hoti.

## Entry ka wazeh contract

- Sirf XAUUSD, US30 aur SPX500; GC=F aur ^DJI inputs canonical assets mein normalize hote hain.
- M15, H1 aur H4 ki completed broker candles par strict Close > EMA50 > EMA200 ya inverse chain zaroori hai.
- M15 entries sirf 07:00–11:00 aur 13:00–17:00 UTC ke half-open windows mein.
- Entry timeframe ki last completed candle par trend ke saath EMA20 pullback reclaim ya pehle se maujood last-five-bar swing ki liquidity sweep/reclaim chahiye.
- SL structural invalidation ke bahar aur TP kam az kam 2R ho. Known SMC target agar 2R se kam ho to setup reject hota hai; target ko pass karwane ke liye stretch nahi karte.
- Actual fresh broker Bid/Ask se reference entry aur spread capture hota hai. Proxy futures ya estimated two-pip spread entry authorize nahi karte.
- Unified weighted confluence, news veto aur risk gates mazeed requirements hain. 75 score win probability nahi hai.
- Ek completed setup candle se dobara trade generate nahi hota, chahe pichla signal close ho gaya ho.

## Exit aur reporting

Original risk aur BE state persist hoti hain. Completed M1 OHLC ki ambiguous bar mein existing stop ko priority milti hai; naya BE pehle ke low/high par retroactively apply nahi hota. M1 execution monitoring hai, naya strategy timeframe nahi.

Paper entry broker quote ka reference hai; broker-confirmed order fill nahi. Exit slippage aur commission abhi modeled hain. Gaps protected stop par bhi loss de sakte hain aur woh loss record hota hai. Legacy incomplete history ko PARTIAL label milta hai; missing old R-results invent nahi hote.

## Validation ki mojooda surat

`scripts/audit_institutional_strategy.py` asal broker history availability aur separately labeled structural-candidate benchmark report karta hai. Benchmark live unified/news/risk engine ka complete replay nahi hai. Synthetic unit-test candles sirf code behavior test karti hain, performance evidence nahi.

Pehli bounded MT5 history request ne `(-6, 'Terminal: Authorization failed')` diya; yeh initial report alag preserve hai. Restart aur bounded retry se teeno assets ki raw history mili. Preliminary structural benchmark mein Gold ke 7, US30 ke 0 aur SPX500 ke 1 reference trades thay. Iske baad clock audit ne actual UTC19:34 ke muqable mein broker ki M15latest open21:30UTC detect ki. Is +2-hour anomaly ki wajah se pehle benchmarks ki session timing validation ke liye reliable nahi aur unke quantitative results invalidated hain. Future candles ko silently discard ya andazay se timezone shift nahi karte. Live setup/exit gates future-dated feed ko reject karte hain. Verified UTC mapping, measured costs aur full unified out-of-sample validation abhi baqi hai; eligible_for_live=false hai.

Purana daily-to-intraday synthetic audit experimental hai; usay zero-lookahead verified ya live strategy performance nahi maana ja sakta.

## Reproducible checks

`python manage.py test engines.test_unified_strategy engines.test_risk_strategy engines.test_institutional_setup signals.tests signals.test_exit_integrity signals.test_strategy_pipeline accounts.test_strategy_execution`

`python -m unittest scripts.test_audit_institutional_strategy`

`python scripts/audit_institutional_strategy.py --bars 6000 --timeout 15`

Live authorization ka existing research gate enabled rehta hai. Current strategy ke liye verified out-of-sample evidence aur required paper history abhi available nahi.
