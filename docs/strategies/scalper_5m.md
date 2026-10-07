# Strategy Specification: 5-Minute Momentum Cross Scalper (`SCALPER_5M`)

## 1. Overview
The 5-Minute Scalper is an intraday momentum strategy tracking fast trend shifts on 5-minute bars, filtered by higher-timeframe 15-minute trend confirmation and session VWAP orientation.

- **Timeframe**: 5-minute closed bars.
- **Holding Period**: 5 to 40 minutes.
- **Execution Mode**: Intraday MIS only.

---

## 2. Core Mathematical Indicators
All indicators are computed server-side in `FeatureStore`:
1. **Exponential Moving Averages (EMA)**:
   - Fast EMA: 9 periods.
   - Slow EMA: 21 periods.
2. **Intraday VWAP**: Cumulative price-volume benchmark reset at `09:15:00 IST`.
3. **Average True Range (ATR 14)**: Wilder smoothing.
4. **15-Minute Higher-Timeframe Filter**:
   - 15m EMA 9 and EMA 21.
   - 15m VWAP reference.
5. **Volume Ratio**: Current 5m volume relative to 20-period volume SMA ($V_t / \text{SMA}(V, 20)$).

---

## 3. Entry & Exit Rules

### Long Entry Setup
1. **Session Window**: $\ge \text{09:20 IST}$ and $< \text{15:00 IST}$.
2. **Market Regime**: Classified as `TRENDING_BULLISH` by `RegimeDetector`.
3. **15m Higher-Timeframe Agreement**: Closed 15m bar must have $\text{Close}_{15m} \ge \text{VWAP}_{15m}$ and $\text{EMA9}_{15m} \ge \text{EMA21}_{15m}$.
4. **Trigger Condition**:
   - Bullish EMA Cross: $\text{EMA9}_{t-1} \le \text{EMA21}_{t-1}$ and $\text{EMA9}_t > \text{EMA21}_t$.
   - Price above VWAP: $\text{Close}_t > \text{VWAP}_t$.
   - Volume confirmation: $\text{VolRatio}_t \ge 1.10$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

### Symmetric Short Entry Setup
1. **Session Window**: $\ge \text{09:20 IST}$ and $< \text{15:00 IST}$.
2. **Market Regime**: Classified as `TRENDING_BEARISH`.
3. **15m Higher-Timeframe Agreement**: Closed 15m bar must have $\text{Close}_{15m} \le \text{VWAP}_{15m}$ and $\text{EMA9}_{15m} \le \text{EMA21}_{15m}$.
4. **Trigger Condition**:
   - Bearish EMA Cross: $\text{EMA9}_{t-1} \ge \text{EMA21}_{t-1}$ and $\text{EMA9}_t < \text{EMA21}_t$.
   - Price below VWAP: $\text{Close}_t < \text{VWAP}_t$.
   - Volume confirmation: $\text{VolRatio}_t \ge 1.10$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

---

## 4. Protective Stop, Target & Sizing

### Stop-Loss
- **Long Stop**: $\text{Entry} - \max(2.0, 1.0 \times \text{ATR})$.
- **Short Stop**: $\text{Entry} + \max(2.0, 1.0 \times \text{ATR})$.
- Sent immediately with entry order as a protective SL order.

### Profit Target
- **Long Target**: $\text{Entry} \times (1 + 0.0045)$ ($+0.45\%$).
- **Short Target**: $\text{Entry} \times (1 - 0.0045)$ ($-0.45\%$).

### Time & Session Stop
- **Time Stop**: 40 minutes max holding duration.
- **Session Cutoff**: 15:15 IST mandatory square-off.

---

## 5. Cost-Aware Statutory Gate
Evaluated by `IndianCostCalculator`:
$$\text{Expected Net Gain} = \text{Target Profit} - (\text{Statutory Taxes} + \text{Brokerage} + \text{Slippage})$$
Condition: $\text{Expected Net Gain} > 0$. Signal rejected if non-positive.

---

## 6. Audit & Discrepancy Findings
1. **Lookahead Check**: Resampling 1m bars to 15m bars must ensure that when evaluating at bar $t$ (e.g. 09:25 IST), the 15m buffer only contains completed 15m candles (e.g. 09:15-09:30 candle is only available at 09:30 IST).
2. **Quality Model**: Stays as `NO_MODEL` pass-through until walk-forward LightGBM is trained.
