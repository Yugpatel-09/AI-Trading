# TradeForge Historical Market Datasets

To backtest with your own real market data instead of test fixtures, place your CSV or Apache Parquet files in this directory.

## File Naming Conventions
- CSV files: `{SYMBOL}_{timeframe}.csv` or `{SYMBOL}.csv`
  - Examples: `NIFTY_1m.csv`, `BANKNIFTY_1m.csv`, `RELIANCE_1m.csv`, `TCS_5m.csv`
- Parquet files: `{SYMBOL}_{timeframe}.parquet` or `{SYMBOL}.parquet`
  - Examples: `NIFTY_1m.parquet`, `RELIANCE_1m.parquet`

## Required Schema / Column Headers
Datasets must contain the following standard columns (case-insensitive):
- `timestamp` (or `datetime`, `date`): ISO-8601 string or datetime object (e.g. `2026-10-05 09:15:00` or `2026-10-05T03:45:00Z`). Timestamps can be IST (UTC+05:30) or UTC.
- `open`: float (bar open price in INR)
- `high`: float (bar high price in INR)
- `low`: float (bar low price in INR)
- `close`: float (bar close price in INR)
- `volume`: integer (traded shares/contracts)
- `vwap` (optional): float (volume weighted average price)

## Sample CSV Format
```csv
timestamp,open,high,low,close,volume,vwap
2026-10-05 09:15:00,2450.00,2455.50,2448.00,2453.20,15420,2452.10
2026-10-05 09:16:00,2453.20,2458.00,2451.00,2456.80,18300,2454.30
```

## Broker Historical API
Alternatively, if your Zerodha Kite account is connected, `BrokerHistoricalDataProvider` will download genuine historical data directly into TimescaleDB/cache via your broker API token.
