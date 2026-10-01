import pytest
from scripts.seed_data import generate_candles
from services.engine.strategies.scalper_1m import Scalper1M
from services.engine.strategies.scalper_5m import Scalper5M
from services.backtester.engine import Backtester
from tradeforge_shared.costs import IndianCostCalculator

def test_backtester_runs_scalper_with_indian_costs():
    candles = generate_candles("RELIANCE", base_price=2500.0, count=100, timeframe="1m")
    scalper = Scalper1M(target_pct=0.003, stop_atr_mult=0.8)
    backtester = Backtester()

    results = backtester.run(
        strategy=scalper,
        candles=candles,
        initial_capital=100000.0,
        risk_per_trade_inr=1000.0,
    )

    assert "total_trades" in results
    assert "win_rate_pct" in results
    assert "total_statutory_taxes_inr" in results
    assert "net_profit_after_costs_inr" in results
    assert results["strategy"] == "SCALPER_1M"

def test_backtester_5m_scalper():
    candles = generate_candles("NIFTY", base_price=22000.0, count=80, timeframe="5m")
    scalper = Scalper5M()
    backtester = Backtester()

    results = backtester.run(
        strategy=scalper,
        candles=candles,
        initial_capital=200000.0,
        risk_per_trade_inr=1500.0,
    )

    assert results["symbol"] == "NIFTY"
    assert results["strategy"] == "SCALPER_5M"
