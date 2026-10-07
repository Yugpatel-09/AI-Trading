# Strategy Specification: 10-Minute Opening Range Breakout (`SCALPER_10M_ORB`)

## 1. Overview
The 10-Minute Opening Range Breakout (ORB) strategy capitalizes on the expansion of early institutional liquidity by establishing the high and low of the opening 20 minutes (`09:15` to `09:35 IST`) and taking breakout trades supported by volume and broader market index participation.

- **Timeframe**: 10-minute closed bars.
- **Holding Period**: 10 to 90 minutes.
- **Execution Mode**: Intraday MIS only.

---

## 2. Core Mathematical Indicators
All indicators are computed server-side in `FeatureStore`:
1. **Opening Range**:
   - $\text{ORB High} = \max(\text{High}_{09:15}, \text{High}_{09:25})$.
   - $\text{ORB Low} = \min(\text{Low}_{09:15}, \text{Low}_{09:25})$.
2. **Intraday VWAP**: Cumulative price-volume benchmark reset at `09:15:00 IST`.
3. **Average True Range (ATR 14)**: Wilder smoothing.
4. **Volume Ratio**: Ratio of 10m breakout volume to 20-period 10m volume SMA ($V_t / \text{SMA}(V, 20)$).
5. **Index Alignment**: Directional agreement with the benchmark index (e.g., NIFTY 50 index candles).

---

## 3. Entry & Exit Rules

### Long Breakout Entry Setup
1. **Session Window**: $\ge \text{09:35 IST}$ (after opening range is finalized) and $< \text{14:00 IST}$.
2. **Market Regime**: `TRENDING_BULLISH` by `RegimeDetector`.
3. **Index Agreement**: If index direction is provided, $\text{Index Direction} \ge 0$.
4. **Trigger Condition**:
   - Clean Breakout: $\text{Close}_t > \text{ORB High}$ and $\text{High}_t > \text{ORB High} \times 1.001$.
   - Price Above VWAP: $\text{Close}_t > \text{VWAP}_t$.
   - Volume Confirmation: $\text{VolRatio}_t \ge 1.25$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

### Symmetric Short Breakdown Setup
1. **Session Window**: $\ge \text{09:35 IST}$ and $< \text{14:00 IST}$.
2. **Market Regime**: `TRENDING_BEARISH`.
3. **Index Agreement**: If index direction is provided, $\text{Index Direction} \le 0$.
4. **Trigger Condition**:
   - Clean Breakdown: $\text{Close}_t < \text{ORB Low}$ and $\text{Low}_t < \text{ORB Low} \times 0.999$.
   - Price Below VWAP: $\text{Close}_t < \text{VWAP}_t$.
   - Volume Confirmation: $\text{VolRatio}_t \ge 1.25$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

---

## 4. Protective Stop, Target & Sizing

### Stop-Loss
- **Long Stop**: $\text{Entry} - \max(3.0, 1.1 \times \text{ATR})$.
- **Short Stop**: $\text{Entry} + \max(3.0, 1.1 \times \text{ATR})$.
- Submitted with entry order.

### Profit Target
- **Long Target**: $\text{Entry} \times (1 + 0.0075)$ ($+0.75\%$).
- **Short Target**: $\text{Entry} \times (1 - 0.0075)$ ($-0.75\%$).

### Time & Session Stop
- **Time Stop**: 75 minutes maximum holding time.
- **Session Cutoff**: 15:15 IST mandatory square-off.

---

## 5. Cost-Aware Statutory Gate
Evaluated by `IndianCostCalculator`:
$$\text{Expected Net Gain} = \text{Target Profit} - (\text{Statutory Taxes} + \text{Brokerage} + \text{Slippage})$$
Condition: $\text{Expected Net Gain} > 0$.

---

## 6. Audit & Discrepancy Findings
1. **Timing Bug Identified**: `scalper_10m_orb.py` line 59 currently checks `c_time.minute < 30`. Since the opening range comprises `09:15 - 09:35 IST`, checking `< 30` allows a premature trigger on the `09:25 - 09:35` bar before the bar has closed and the opening range is fully set. **Correction needed**: The check must be `c_time.minute < 35` (or strictly require at least 2 closed 10m bars post-09:15, i.e. 09:35 IST earliest entry).
2. **Buffer Availability**: If `context.opening_range_high` is not yet populated by `FeatureStore`, the strategy cleanly returns `None` without crashing.
