from datetime import datetime, timezone

import pytest
from tradeforge_shared.costs import IndianCostCalculator
from tradeforge_shared.enums import MarketRegime, OrderSide, StrategyType
from tradeforge_shared.schemas import Signal


def test_indian_cost_calculator_sample_trade():
    """
    Validates example from blueprint page 9:
    Buy 100 shares at Rs. 500 (value 50,000) and sell at +0.3% (Rs. 501.50).
    Gross profit = Rs. 150.
    Charges + slippage should reduce net profit significantly.
    """
    calc = IndianCostCalculator(default_slippage_bps=5.0)
    buy_price = 500.0
    sell_price = 501.50
    qty = 100

    result = calc.calculate_round_trip(buy_price, sell_price, qty)

    # Gross P&L is (501.50 - 500) * 100 = 150.0
    assert pytest.approx(result.gross_pnl, 0.01) == 150.0

    # Total turnover is 50,000 + 50,150 = 100,150
    assert pytest.approx(result.turnover, 0.01) == 100150.0

    # Brokerage: min(20, 50,000 * 0.03%) = 15 on buy, min(20, 50,150 * 0.03%) = 15.045 on sell
    assert result.brokerage > 0

    # STT on sell side: 50,150 * 0.00025 = ~12.54
    assert result.stt > 0

    # Costs eat into gross profit
    assert result.total_costs > 0
    assert result.net_pnl < result.gross_pnl
    assert result.net_pnl > 0  # Still marginally positive

def test_cost_check_catches_unprofitable_micro_gain():
    """A 0.05% gain on Rs. 500 stock cannot survive Indian statutory costs."""
    calc = IndianCostCalculator()
    buy_price = 500.0
    sell_price = 500.25 # +0.05%
    qty = 100

    result = calc.calculate_round_trip(buy_price, sell_price, qty)
    assert result.gross_pnl == 25.0
    # Net P&L will be negative after statutory charges!
    assert result.net_pnl < 0.0

def test_signal_requires_protective_stop():
    """Signals without a protective stop must fail schema validation (Non-negotiable rule 7)."""
    with pytest.raises(Exception):
        Signal(
            id="sig_test_1",
            strategy_type=StrategyType.SCALPER_1M,
            symbol="RELIANCE",
            side=OrderSide.BUY,
            timeframe="1m",
            timestamp=datetime.now(timezone.utc),
            entry_price=2500.0,
            # stop_loss missing
            target=2515.0,
            regime=MarketRegime.TRENDING_BULLISH,
            quality_score=0.72,
            expected_net_gain_pct=0.35,
            reason="VWAP pullback"
        )
