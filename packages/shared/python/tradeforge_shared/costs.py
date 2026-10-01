from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class IndianCostBreakdown:
    """Detailed statutory fee breakdown for an intraday round-trip trade."""
    turnover: float
    brokerage: float
    stt: float
    exchange_turnover_fee: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    estimated_slippage: float
    total_costs: float
    gross_pnl: float
    net_pnl: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turnover": round(self.turnover, 2),
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_turnover_fee": round(self.exchange_turnover_fee, 2),
            "gst": round(self.gst, 2),
            "sebi_charges": round(self.sebi_charges, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "estimated_slippage": round(self.estimated_slippage, 2),
            "total_costs": round(self.total_costs, 2),
            "gross_pnl": round(self.gross_pnl, 2),
            "net_pnl": round(self.net_pnl, 2),
        }

class IndianCostCalculator:
    """
    Statutory Indian intraday equity transaction cost calculator.
    
    Standard Indian Rates (NSE Intraday Equities):
    - Brokerage: Min(₹20 per executed order, 0.03% of turnover)
    - STT (Securities Transaction Tax): 0.025% on sell side turnover
    - NSE Exchange Turnover Charges: 0.00345% of total turnover
    - GST: 18% on (Brokerage + Exchange Charges + SEBI charges)
    - SEBI Turnover Charges: ₹10 per crore (0.0001% of turnover)
    - Stamp Duty: 0.003% on buy side turnover
    - Slippage: Configurable basis points (default: 5 bps / 0.05%)
    """
    def __init__(
        self,
        flat_brokerage_per_order: float = 20.0,
        max_brokerage_pct: float = 0.0003, # 0.03%
        stt_rate_sell: float = 0.00025,    # 0.025% on sell
        exchange_fee_rate: float = 0.0000345, # 0.00345% NSE
        gst_rate: float = 0.18,            # 18%
        sebi_rate: float = 0.000001,       # ₹10 per crore (0.0001%)
        stamp_duty_buy: float = 0.00003,   # 0.003% on buy
        default_slippage_bps: float = 5.0, # 5 basis points (0.05%)
    ):
        self.flat_brokerage_per_order = flat_brokerage_per_order
        self.max_brokerage_pct = max_brokerage_pct
        self.stt_rate_sell = stt_rate_sell
        self.exchange_fee_rate = exchange_fee_rate
        self.gst_rate = gst_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_buy = stamp_duty_buy
        self.default_slippage_bps = default_slippage_bps

    def calculate_round_trip(
        self,
        buy_price: float,
        sell_price: float,
        quantity: int,
        slippage_bps: float | None = None,
    ) -> IndianCostBreakdown:
        """Calculate complete statutory costs and net P&L for a buy-then-sell round trip."""
        if quantity <= 0 or buy_price <= 0 or sell_price <= 0:
            raise ValueError("Price and quantity must be positive")

        buy_turnover = buy_price * quantity
        sell_turnover = sell_price * quantity
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage (2 orders: buy + sell)
        buy_brokerage = min(self.flat_brokerage_per_order, buy_turnover * self.max_brokerage_pct)
        sell_brokerage = min(self.flat_brokerage_per_order, sell_turnover * self.max_brokerage_pct)
        total_brokerage = buy_brokerage + sell_brokerage

        # 2. STT (Securities Transaction Tax) - applied on SELL side for intraday equity
        stt = sell_turnover * self.stt_rate_sell

        # 3. Exchange Turnover Fee
        exchange_fee = total_turnover * self.exchange_fee_rate

        # 4. SEBI Charges
        sebi_charges = total_turnover * self.sebi_rate

        # 5. GST (18% on Brokerage + Exchange Fee + SEBI Fee)
        taxable_services = total_brokerage + exchange_fee + sebi_charges
        gst = taxable_services * self.gst_rate

        # 6. Stamp Duty - applied on BUY side
        stamp_duty = buy_turnover * self.stamp_duty_buy

        # 7. Estimated Slippage
        active_slippage_bps = slippage_bps if slippage_bps is not None else self.default_slippage_bps
        slippage = total_turnover * (active_slippage_bps / 10000.0)

        total_costs = total_brokerage + stt + exchange_fee + gst + sebi_charges + stamp_duty + slippage
        gross_pnl = (sell_price - buy_price) * quantity
        net_pnl = gross_pnl - total_costs

        return IndianCostBreakdown(
            turnover=total_turnover,
            brokerage=total_brokerage,
            stt=stt,
            exchange_turnover_fee=exchange_fee,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            estimated_slippage=slippage,
            total_costs=total_costs,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
        )
