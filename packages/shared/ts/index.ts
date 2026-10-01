export type TradingMode = 'PAPER' | 'APPROVE' | 'AUTO';

export type OrderSide = 'BUY' | 'SELL';

export type OrderType = 'MARKET' | 'LIMIT' | 'SL' | 'SL_M';

export type OrderStatus =
  | 'PENDING'
  | 'RISK_APPROVED'
  | 'RISK_REJECTED'
  | 'SUBMITTED'
  | 'PARTIAL_FILL'
  | 'FILLED'
  | 'CANCELLED'
  | 'REJECTED';

export type MarketRegime =
  | 'TRENDING_BULLISH'
  | 'TRENDING_BEARISH'
  | 'RANGE_BOUND'
  | 'VOLATILE_CHAOTIC';

export type StrategyType = 'SCALPER_1M' | 'SCALPER_5M' | 'SCALPER_10M_ORB';

export type BrokerType =
  | 'PAPER'
  | 'ZERODHA'
  | 'UPSTOX'
  | 'ANGEL_ONE'
  | 'GROWW'
  | 'DHAN';

export interface Candle {
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
}

export interface Signal {
  id: string;
  strategy_type: StrategyType;
  symbol: string;
  side: OrderSide;
  timeframe: string;
  timestamp: string;
  entry_price: number;
  stop_loss: number;
  target: number;
  trailing_stop_delta?: number;
  time_stop_minutes: number;
  regime: MarketRegime;
  quality_score: number;
  expected_net_gain_pct: number;
  reason: string;
}

export interface UserRiskSettings {
  user_id: string;
  capital_allocated_inr: number;
  max_loss_per_trade_inr: number;
  max_daily_loss_inr: number;
  max_open_positions: number;
  max_daily_trades: number;
  mode: TradingMode;
  auto_stop_after_consecutive_losses: number;
  allowed_instruments: string[];
  trading_start_time_ist: string;
  trading_end_time_ist: string;
}

export interface IndianCostBreakdown {
  turnover: number;
  brokerage: number;
  stt: number;
  exchange_turnover_fee: number;
  gst: number;
  sebi_charges: number;
  stamp_duty: number;
  estimated_slippage: number;
  total_costs: number;
  gross_pnl: number;
  net_pnl: number;
}

export interface SystemHealthStatus {
  status: 'HEALTHY' | 'DEGRADED' | 'HALTED';
  data_feed_delay_ms: number;
  timescaledb_connected: boolean;
  redis_connected: boolean;
  kill_switch_active: boolean;
  open_positions_count: number;
  todays_realized_pnl_inr: number;
  active_mode: TradingMode;
  timestamp: string;
}
