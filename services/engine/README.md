# TradeForge AI Engine (`services/engine`)

The analytical brain of TradeForge. Converts ticks to multi-timeframe candles, evaluates indicators, classifies market regimes, and generates rule-based signals filtered by machine learning quality models.

## Architecture
- `data_feed/`: Tick aggregator building 1m, 5m, and 10m OHLCV candles. Verifies freshness (< 5s staleness check).
- `features/`: High-performance technical feature store (VWAP, EMA 9/21, RSI 14, ATR, ADX, Opening Range High/Low, Volume Ratio).
- `regime/`: Market Regime Classifier (Trending Up, Trending Down, Range-Bound, Volatile/Chaotic).
- `strategies/`:
  - `scalper_1m.py`: 1-minute VWAP pullback with 5m trend confirmation.
  - `scalper_5m.py`: 5-minute EMA 9/21 cross & Supertrend flip with volume expansion.
  - `scalper_10m_orb.py`: 10-minute Opening Range Breakout with retest confirmation.
- `models/`: LightGBM signal quality classifier (predicts probability of hitting target before stop-loss).
- `sizing/`: Volatility-adjusted position sizer ($Size = \frac{CapitalRisk}{StopDistance}$).
- `costs/`: Real-time transaction cost gate (rejects setups where expected net profit < 1.5x total fees & slippage).
