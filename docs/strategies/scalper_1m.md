# Strategy Specification: 1-Minute VWAP Pullback Scalper (`SCALPER_1M`)

## 1. Overview
The 1-Minute Scalper is a high-velocity momentum and mean-reversion pull-in strategy designed for liquid NSE instruments. It identifies short-term exhaustion pullbacks to the institutional intraday Volume-Weighted Average Price (VWAP) within an established higher-timeframe trend.

- **Timeframe**: 1-minute closed bars.
- **Holding Period**: 1 to 10 minutes.
- **Execution Mode**: Intraday MIS only.

---

## 2. Core Mathematical Indicators
All indicators are computed server-side in `FeatureStore` without client-side divergence:
1. **Intraday VWAP**: Cumulative price-volume ratio reset daily at `09:15:00 IST`:
   $$\text{VWAP}_t = \frac{\sum_{i=1}^t P_i \cdot V_i}{\sum_{i=1}^t V_i}$$
2. **Average True Range (ATR 14)**: Wilder-smoothed volatility metric.
3. **5-Minute Higher-Timeframe Filter**:
   - 5m Exponential Moving Average (EMA 9 and EMA 21).
   - 5m VWAP reference.
4. **Volume Ratio**: Ratio of current 1m bar volume to the 20-period volume moving average ($V_t / \text{SMA}(V, 20)$).

---

## 3. Entry & Exit Rules

### Long Entry Setup
1. **Session Window**: Current bar timestamp $\ge \text{09:20 IST}$ and $< \text{15:00 IST}$.
2. **Market Regime**: `RegimeDetector` must classify the 1m history as `TRENDING_BULLISH`.
3. **5m Higher-Timeframe Agreement**: Closed 5m bar must have $\text{Close}_{5m} \ge \text{VWAP}_{5m}$ and $\text{EMA9}_{5m} \ge \text{EMA21}_{5m}$.
4. **Trigger Condition**:
   - Prior bar low penetrated or touched VWAP: $\text{Low}_{t-1} \le \text{VWAP}_t$.
   - Current bar closes firmly back above VWAP: $\text{Close}_t > \text{VWAP}_t$.
   - Volume surge confirmation: $\text{VolRatio}_t \ge 1.20$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

### Symmetric Short Entry Setup
1. **Session Window**: $\ge \text{09:20 IST}$ and $< \text{15:00 IST}$.
2. **Market Regime**: Must classify history as `TRENDING_BEARISH`.
3. **5m Higher-Timeframe Agreement**: Closed 5m bar must have $\text{Close}_{5m} \le \text{VWAP}_{5m}$ and $\text{EMA9}_{5m} \le \text{EMA21}_{5m}$.
4. **Trigger Condition**:
   - Prior bar high penetrated or touched VWAP: $\text{High}_{t-1} \ge \text{VWAP}_t$.
   - Current bar closes firmly back below VWAP: $\text{Close}_t < \text{VWAP}_t$.
   - Volume surge confirmation: $\text{VolRatio}_t \ge 1.20$.
5. **Entry Price**: Current bar close ($\text{Close}_t$).

---

## 4. Protective Stop, Target & Sizing

### Stop-Loss
- **Long Stop**: $\text{Entry} - \max(1.0, 0.8 \times \text{ATR})$.
- **Short Stop**: $\text{Entry} + \max(1.0, 0.8 \times \text{ATR})$.
- Mandatory: Submitted simultaneously with entry order as a protective stop.

### Profit Target
- **Long Target**: $\text{Entry} \times (1 + 0.0025)$ ($+0.25\%$).
- **Short Target**: $\text{Entry} \times (1 - 0.0025)$ ($-0.25\%$).

### Time & Session Stop
- **Time Stop**: 15 minutes max holding period.
- **Session Cutoff**: 15:15 IST mandatory square-off.

---

## 5. Cost-Aware Statutory Gate
Before emitting any signal, `IndianCostCalculator` evaluates full round-trip friction:
- Brokerage: $\min(20, \text{Turnover} \times 0.0003)$ per leg.
- Securities Transaction Tax (STT): $0.025\%$ on equity sell leg / applicable derivative STT.
- Exchange Turnover Fees: $0.00345\%$.
- SEBI Turnover Charges: ₹10 / crore.
- Stamp Duty: $0.003\%$ on buy leg.
- GST: $18\%$ on (Brokerage + Exchange Fees + SEBI).
- Slippage Buffer: Configurable (default 5 bps).

**Gate Condition**: Expected Net P&L after all statutory taxes and slippage must be strictly positive:
$$\text{Net PnL} > 0$$

---

## 6. Audit & Discrepancy Findings
1. **Quantity Assumption in Cost Gate**: Currently evaluates costs with a static `quantity=100`. In production, this should scale with the user's allocated risk capital and lot size to ensure the statutory minimums match true account execution.
2. **Zero-Lookahead Guarantee**: Verified. `on_candle` processes completed bars. Resampled 5m bars must strictly exclude forming/incomplete bars to avoid intra-bar repainting.
3. **Parity**: Identical logic runs across backtest, paper broker, and live gateway.
