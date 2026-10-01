'use client';

import React, { useState } from 'react';
import {
  ShieldAlert,
  Sliders,
  TrendingUp,
  Cpu,
  ArrowRight,
  CheckCircle2,
  DollarSign,
  AlertOctagon,
  Lock,
  Layers,
  Zap,
  BarChart3,
  Scale,
  RefreshCw,
} from 'lucide-react';

export default function LandingPage() {
  // Interactive Statutory Cost Calculator State
  const [calcBuyPrice, setCalcBuyPrice] = useState(500);
  const [calcSellPrice, setCalcSellPrice] = useState(502);
  const [calcQuantity, setCalcQuantity] = useState(100);

  // Emergency Kill Switch Demo State
  const [killSwitchActive, setKillSwitchActive] = useState(false);
  const [activeStrategy, setActiveStrategy] = useState<'1m' | '5m' | '10m'>('1m');

  // Calculate Indian Costs client-side for instant reactive UI
  const turnover = (calcBuyPrice + calcSellPrice) * calcQuantity;
  const buyTurnover = calcBuyPrice * calcQuantity;
  const sellTurnover = calcSellPrice * calcQuantity;
  const grossPnl = (calcSellPrice - calcBuyPrice) * calcQuantity;

  // Indian statutory rates
  const brokerage = Math.min(20, buyTurnover * 0.0003) + Math.min(20, sellTurnover * 0.0003);
  const stt = sellTurnover * 0.00025; // 0.025% on sell
  const exchangeFee = turnover * 0.0000345; // 0.00345%
  const sebiCharges = turnover * 0.000001; // ₹10 / cr
  const gst = (brokerage + exchangeFee + sebiCharges) * 0.18; // 18%
  const stampDuty = buyTurnover * 0.00003; // 0.003% on buy
  const slippage = turnover * 0.0005; // 5 bps slippage
  const totalCosts = brokerage + stt + exchangeFee + gst + sebiCharges + stampDuty + slippage;
  const netPnl = grossPnl - totalCosts;

  return (
    <div className="space-y-24 py-8">
      {/* ---------------------------------------------------------------------- */}
      {/* HERO SECTION */}
      {/* ---------------------------------------------------------------------- */}
      <section className="relative px-4 max-w-7xl mx-auto text-center space-y-8 pt-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-teal-950/60 border border-teal-800/60 text-teal-300 text-xs font-mono">
          <span className="w-2 h-2 rounded-full bg-teal-400 animate-ping"></span>
          <span>TradeForge v1.0 • Autonomous NSE Intraday Architecture</span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-white max-w-4xl mx-auto leading-[1.15]">
          Tools and Discipline for Intraday Traders.{' '}
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-teal-400 via-teal-300 to-emerald-400">
            Never Fake Returns.
          </span>
        </h1>

        <p className="text-lg sm:text-xl text-slate-400 max-w-3xl mx-auto font-normal leading-relaxed">
          The institutional AI trading platform for the Indian NSE market. Pre-trade risk isolation, mandatory bracket stop-losses, statutory tax accounting, and paper-mode verification before live deployment.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <a
            href="#demo"
            className="px-6 py-3.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white shadow-xl shadow-teal-900/40 transition-all flex items-center gap-2 text-sm sm:text-base"
          >
            <span>Explore Live Dashboard Demo</span>
            <ArrowRight className="w-4 h-4" />
          </a>
          <a
            href="#risk-guard"
            className="px-6 py-3.5 rounded-lg bg-[#132235] hover:bg-[#1A2E47] border border-[#1F334A] font-semibold text-slate-200 transition-all text-sm sm:text-base flex items-center gap-2"
          >
            <ShieldAlert className="w-4 h-4 text-teal-400" />
            <span>How RiskGuard Protects Capital</span>
          </a>
        </div>

        {/* Trust Badges */}
        <div className="pt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-4xl mx-auto text-xs text-slate-400 font-mono">
          <div className="p-3 rounded-lg bg-[#0D1B2A] border border-[#1F334A]">
            <span className="block text-white font-bold text-sm">Non-Custodial</span>
            <span>Funds always in your broker</span>
          </div>
          <div className="p-3 rounded-lg bg-[#0D1B2A] border border-[#1F334A]">
            <span className="block text-white font-bold text-sm">Mandatory Stops</span>
            <span>Sent with entry, never later</span>
          </div>
          <div className="p-3 rounded-lg bg-[#0D1B2A] border border-[#1F334A]">
            <span className="block text-white font-bold text-sm">Cost Factoring</span>
            <span>Real STT, GST & slippage</span>
          </div>
          <div className="p-3 rounded-lg bg-[#0D1B2A] border border-[#1F334A]">
            <span className="block text-white font-bold text-sm">15:15 IST Cutoff</span>
            <span>Auto square-off protection</span>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* 3-STEP WORKFLOW */}
      {/* ---------------------------------------------------------------------- */}
      <section id="how-it-works" className="px-4 max-w-7xl mx-auto space-y-12">
        <div className="text-center space-y-3">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-teal-400">
            Deterministic Process
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white">How TradeForge Works in 3 Steps</h2>
          <p className="text-slate-400 max-w-xl mx-auto text-sm">
            Disciplined quantitative trading follows a strict verification pipeline before any real rupee is risked.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 hover:border-teal-500/50 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-teal-950 border border-teal-700/50 flex items-center justify-center text-teal-400 font-mono font-bold">
              01
            </div>
            <h3 className="text-lg font-bold text-white">Connect Your Broker API</h3>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Connect via Zerodha Kite Connect, Upstox, or Angel One. All access tokens are encrypted using AES-256-GCM. We require <strong>trade-only permissions</strong>—we can never withdraw your money.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 hover:border-teal-500/50 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-teal-950 border border-teal-700/50 flex items-center justify-center text-teal-400 font-mono font-bold">
              02
            </div>
            <h3 className="text-lg font-bold text-white">Set Non-Negotiable Limits</h3>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Define your maximum daily loss limit (e.g., ₹2,500), maximum loss per trade (e.g., ₹500), and max concurrent positions. Once breached, the engine halts trading for the remainder of the session.
            </p>
          </div>

          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 hover:border-teal-500/50 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-teal-950 border border-teal-700/50 flex items-center justify-center text-teal-400 font-mono font-bold">
              03
            </div>
            <h3 className="text-lg font-bold text-white">Paper Trade, Then Go Live</h3>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Test on real-time live NSE feeds with virtual currency. Evaluate win rate, drawdowns, and post-brokerage slippage. Transition to <strong>Approve Mode</strong> or <strong>Auto Mode</strong> only when proven.
            </p>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* INTERACTIVE LIVE DASHBOARD & KILL SWITCH DEMO */}
      {/* ---------------------------------------------------------------------- */}
      <section id="demo" className="px-4 max-w-7xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-[#0D1B2A] border border-[#1F334A]">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>Live Intraday Execution Monitor</span>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                SIMULATED PAPER FEED
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Interactive preview of what the trader sees during active NSE market hours.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setKillSwitchActive(!killSwitchActive)}
              className={`px-4 py-2 rounded-lg text-xs font-bold font-mono transition-all flex items-center gap-1.5 ${
                killSwitchActive
                  ? 'bg-amber-600 hover:bg-amber-500 text-white'
                  : 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-600/30'
              }`}
            >
              <AlertOctagon className="w-4 h-4" />
              <span>{killSwitchActive ? 'RESUME TRADING' : 'EMERGENCY KILL SWITCH'}</span>
            </button>
          </div>
        </div>

        {/* Dashboard Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Chart & Position View */}
          <div className="lg:col-span-2 p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="text-xs font-mono text-slate-400">ACTIVE INSTRUMENT</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-white">RELIANCE</span>
                  <span className="text-xs font-mono text-slate-400">NSE • EQ</span>
                  <span className="text-lg font-mono font-bold text-emerald-400 tabular-nums">
                    ₹2,504.80
                  </span>
                  <span className="text-xs font-mono text-emerald-400">(+0.42%)</span>
                </div>
              </div>

              {/* Timeframe selector */}
              <div className="flex items-center gap-1 bg-[#132235] p-1 rounded-lg border border-[#1F334A] text-xs font-mono">
                <button
                  onClick={() => setActiveStrategy('1m')}
                  className={`px-3 py-1 rounded ${activeStrategy === '1m' ? 'bg-teal-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                >
                  1m Scalper
                </button>
                <button
                  onClick={() => setActiveStrategy('5m')}
                  className={`px-3 py-1 rounded ${activeStrategy === '5m' ? 'bg-teal-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                >
                  5m Scalper
                </button>
                <button
                  onClick={() => setActiveStrategy('10m')}
                  className={`px-3 py-1 rounded ${activeStrategy === '10m' ? 'bg-teal-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                >
                  10m ORB
                </button>
              </div>
            </div>

            {/* Simulated Candle Graphic */}
            <div className="h-64 rounded-lg bg-[#070D14] border border-[#1F334A] p-4 flex flex-col justify-between relative overflow-hidden font-mono text-xs">
              <div className="flex items-center justify-between text-slate-400">
                <span>VWAP: ₹2,499.20</span>
                <span>EMA 9: ₹2,502.10</span>
                <span>EMA 21: ₹2,498.40</span>
                <span>ATR: ₹11.50</span>
              </div>

              {/* Simulated Candlestick Visualization */}
              <div className="flex items-end justify-between h-40 px-2 py-4">
                {[
                  { h: 40, c: 'bg-emerald-500', t: '09:30' },
                  { h: 35, c: 'bg-red-500', t: '09:31' },
                  { h: 48, c: 'bg-emerald-500', t: '09:32' },
                  { h: 60, c: 'bg-emerald-500', t: '09:33' },
                  { h: 50, c: 'bg-red-500', t: '09:34' },
                  { h: 72, c: 'bg-emerald-500', t: '09:35' },
                  { h: 65, c: 'bg-red-500', t: '09:36' },
                  { h: 80, c: 'bg-emerald-500', t: '09:37 (BUY ENTRY)' },
                  { h: 88, c: 'bg-emerald-500', t: '09:38' },
                  { h: 92, c: 'bg-emerald-500', t: '09:39 (ACTIVE)' },
                ].map((bar, i) => (
                  <div key={i} className="flex flex-col items-center gap-1">
                    <div
                      className={`w-3.5 rounded-sm transition-all duration-300 ${bar.c}`}
                      style={{ height: `${bar.h}%` }}
                    ></div>
                    <span className="text-[9px] text-slate-400 rotate-45 mt-1">{bar.t.split(' ')[0]}</span>
                  </div>
                ))}
              </div>

              {/* Active Order Bracket Indicators */}
              <div className="flex items-center justify-between border-t border-slate-800 pt-2 text-[11px]">
                <span className="text-red-400">Stop-Loss: ₹2,490.00 (-₹10.00)</span>
                <span className="text-teal-400">Entry: ₹2,500.00 (Filled)</span>
                <span className="text-emerald-400">Target: ₹2,520.00 (+₹20.00)</span>
              </div>

              {/* Kill Switch Overlay if active */}
              {killSwitchActive && (
                <div className="absolute inset-0 bg-red-950/80 backdrop-blur-sm flex flex-col items-center justify-center text-center p-4 text-white">
                  <AlertOctagon className="w-12 h-12 text-red-400 animate-pulse mb-2" />
                  <span className="text-lg font-bold">EMERGENCY KILL SWITCH TRIGGERED</span>
                  <span className="text-xs text-red-200 max-w-sm mt-1">
                    All open orders cancelled. Position square-off dispatched. Trading halted for today.
                  </span>
                </div>
              )}
            </div>

            {/* Explainable AI Decision Card */}
            <div className="p-4 rounded-lg bg-[#132235] border border-teal-500/30 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-teal-400 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  <span>Explainable AI Trade Rationale (Specialist 2 & 3)</span>
                </span>
                <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800">
                  Model Quality Score: 0.78 (PASSED)
                </span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-sans">
                &ldquo;Entered <strong>50 shares</strong> at <strong>₹2,500.00</strong>. Reason: 1m VWAP pullback triggered while the 5m multi-timeframe trend is clean bullish. 1.8x volume expansion confirmed buyer absorption at ₹2,498 support. Stop bracket placed at ₹2,490.00 (-₹500 rupee risk). Expected net profit after Indian statutory taxes: +₹862.40.&rdquo;
              </p>
            </div>
          </div>

          {/* Right Column: Live Positions & Risk Guard Status */}
          <div className="space-y-6">
            <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4">
              <h4 className="text-sm font-bold text-white flex items-center justify-between">
                <span>Today&apos;s Live Metrics (Net)</span>
                <span className="text-xs font-mono text-slate-400">Post-Fees & Taxes</span>
              </h4>

              <div className="space-y-3 font-mono">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Realized Net P&L</span>
                  <span className="text-emerald-400 font-bold text-base tabular-nums">+₹1,420.50</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Unrealized P&L</span>
                  <span className="text-emerald-400 font-bold tabular-nums">+₹240.00</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Win Rate (Today)</span>
                  <span className="text-white font-bold tabular-nums">4 wins / 1 loss (80%)</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Total Statutory Taxes Paid</span>
                  <span className="text-slate-300 tabular-nums">₹182.40</span>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-800 space-y-2 text-xs">
                <span className="text-slate-400 font-mono text-[11px] block">ACTIVE RISK GUARD LIMITS</span>
                <div className="w-full bg-[#132235] h-2 rounded-full overflow-hidden">
                  <div className="bg-teal-500 h-full w-[35%]"></div>
                </div>
                <div className="flex justify-between text-[11px] font-mono text-slate-400">
                  <span>Daily Loss Used: ₹0 / ₹3,000</span>
                  <span>Trades: 5 / 8</span>
                </div>
              </div>
            </div>

            {/* Supported Brokers List */}
            <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-3">
              <h4 className="text-sm font-bold text-white">Broker Connections</h4>
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between p-2 rounded bg-[#132235] border border-emerald-900/40">
                  <span className="font-semibold text-white">Paper Broker (Internal)</span>
                  <span className="text-emerald-400 font-mono text-[11px]">CONNECTED</span>
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-[#132235] border border-slate-800">
                  <span className="text-slate-300">Zerodha Kite Connect</span>
                  <span className="text-teal-400 font-mono text-[11px] cursor-pointer hover:underline">
                    Connect API
                  </span>
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-[#132235] border border-slate-800">
                  <span className="text-slate-300">Upstox API v2</span>
                  <span className="text-teal-400 font-mono text-[11px] cursor-pointer hover:underline">
                    Connect API
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* THE 3 SCALPERS SPECIFICATION */}
      {/* ---------------------------------------------------------------------- */}
      <section id="scalpers" className="px-4 max-w-7xl mx-auto space-y-10">
        <div className="text-center space-y-3">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-teal-400">
            Algorithmic Edge
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white">The Three Intraday Scalpers</h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-sm">
            Scalpers target micro-moves with thin edges. Discipline, cost-accounting, and regime filters make or break the strategy.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* 1 Minute Scalper */}
          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 relative flex flex-col justify-between">
            <div className="space-y-3">
              <div className="inline-block px-2.5 py-1 rounded bg-teal-950 text-teal-400 border border-teal-800 text-xs font-mono font-bold">
                1-MINUTE SCALPER
              </div>
              <h3 className="text-lg font-bold text-white">VWAP Pullback & Volume</h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                Trades only the most liquid names (NIFTY 50 top weightage). Exploits quick retests of the intraday VWAP in the direction of the 5-minute trend.
              </p>
              <div className="pt-2 space-y-1.5 text-xs font-mono text-slate-300 border-t border-slate-800">
                <div className="flex justify-between">
                  <span className="text-slate-400">Target Move:</span>
                  <span>0.15% to 0.30%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Stop-Loss:</span>
                  <span>0.8x ATR (tight)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Trade Duration:</span>
                  <span>1 to 10 minutes</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Daily Cap:</span>
                  <span>8 to 12 trades</span>
                </div>
              </div>
            </div>
            <div className="p-3 rounded bg-[#132235] text-[11px] text-amber-300 font-mono">
              Danger: Costs and slippage eat thin gains. Requires strict liquid filter.
            </div>
          </div>

          {/* 5 Minute Scalper */}
          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-teal-500/50 space-y-4 relative flex flex-col justify-between shadow-lg shadow-teal-950/40">
            <div className="space-y-3">
              <div className="inline-block px-2.5 py-1 rounded bg-teal-600 text-white text-xs font-mono font-bold">
                5-MINUTE SCALPER (POPULAR)
              </div>
              <h3 className="text-lg font-bold text-white">EMA 9/21 & Supertrend Flip</h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                Identifies clean momentum transitions where fast moving averages cross and Supertrend flips with above-average volume and 15m trend alignment.
              </p>
              <div className="pt-2 space-y-1.5 text-xs font-mono text-slate-300 border-t border-slate-800">
                <div className="flex justify-between">
                  <span className="text-slate-400">Target Move:</span>
                  <span>0.30% to 0.60%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Stop-Loss:</span>
                  <span>1.0x ATR</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Trade Duration:</span>
                  <span>5 to 40 minutes</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Daily Cap:</span>
                  <span>5 to 8 trades</span>
                </div>
              </div>
            </div>
            <div className="p-3 rounded bg-[#132235] text-[11px] text-teal-300 font-mono">
              Best Regime: Clean trending market sessions with steady index participation.
            </div>
          </div>

          {/* 10 Minute Scalper */}
          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 relative flex flex-col justify-between">
            <div className="space-y-3">
              <div className="inline-block px-2.5 py-1 rounded bg-teal-950 text-teal-400 border border-teal-800 text-xs font-mono font-bold">
                10-MINUTE ORB
              </div>
              <h3 className="text-lg font-bold text-white">Opening Range Breakout</h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                Tracks the high and low of the initial opening range. Enters on confirmed breakout with retest and daily bias agreement.
              </p>
              <div className="pt-2 space-y-1.5 text-xs font-mono text-slate-300 border-t border-slate-800">
                <div className="flex justify-between">
                  <span className="text-slate-400">Target Move:</span>
                  <span>0.50% to 1.00%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Stop-Loss:</span>
                  <span>1.0x to 1.2x ATR</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Trade Duration:</span>
                  <span>10 to 90 minutes</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Daily Cap:</span>
                  <span>3 to 5 trades</span>
                </div>
              </div>
            </div>
            <div className="p-3 rounded bg-[#132235] text-[11px] text-amber-300 font-mono">
              Danger: False breakouts during high-volatility first 15 minutes of open.
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* STATUTORY COST CALCULATOR */}
      {/* ---------------------------------------------------------------------- */}
      <section id="costs" className="px-4 max-w-7xl mx-auto space-y-10">
        <div className="text-center space-y-3">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-teal-400">
            Transparency First
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white">
            Why Costs Decide Whether a Scalper Works
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-sm">
            Statutory Indian charges (STT, GST, Stamp Duty, Turnover Fees) compound rapidly on intraday trades. TradeForge models these in real-time before entering.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A]">
          {/* Controls */}
          <div className="space-y-6">
            <h3 className="text-lg font-bold text-white">Interactive NSE Intraday Cost Simulator</h3>
            <p className="text-xs text-slate-400">
              Test how brokerage, statutory levies, and slippage impact your net takeaway.
            </p>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-mono text-slate-300 block mb-1">
                  Buy Price (₹)
                </label>
                <input
                  type="number"
                  value={calcBuyPrice}
                  onChange={(e) => setCalcBuyPrice(Number(e.target.value) || 1)}
                  className="w-full bg-[#132235] border border-[#1F334A] rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-teal-500 outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-mono text-slate-300 block mb-1">
                  Sell Price (₹)
                </label>
                <input
                  type="number"
                  value={calcSellPrice}
                  onChange={(e) => setCalcSellPrice(Number(e.target.value) || 1)}
                  className="w-full bg-[#132235] border border-[#1F334A] rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-teal-500 outline-none"
                />
              </div>

              <div>
                <label className="text-xs font-mono text-slate-300 block mb-1">
                  Quantity (Shares)
                </label>
                <input
                  type="number"
                  value={calcQuantity}
                  onChange={(e) => setCalcQuantity(Number(e.target.value) || 1)}
                  className="w-full bg-[#132235] border border-[#1F334A] rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-teal-500 outline-none"
                />
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#132235] text-xs text-slate-300 leading-relaxed">
              <strong>Cost Gate Rule:</strong> The AI engine will automatically abort any proposed trade if the projected net profit after all fees is less than <strong>1.5x total costs</strong>.
            </div>
          </div>

          {/* Results Ledger */}
          <div className="p-6 rounded-xl bg-[#070D14] border border-[#1F334A] space-y-4 font-mono text-xs">
            <h4 className="text-white font-bold text-sm tracking-wide">STATUTORY CHARGES BREAKDOWN</h4>

            <div className="space-y-2 border-b border-slate-800 pb-4">
              <div className="flex justify-between text-slate-400">
                <span>Total Turnover (Buy + Sell)</span>
                <span className="text-white tabular-nums">₹{turnover.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Brokerage (₹20 cap or 0.03%)</span>
                <span className="text-slate-200 tabular-nums">₹{brokerage.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>STT (0.025% on sell side)</span>
                <span className="text-slate-200 tabular-nums">₹{stt.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>NSE Exchange Turnover Fee (0.00345%)</span>
                <span className="text-slate-200 tabular-nums">₹{exchangeFee.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>GST (18% on services)</span>
                <span className="text-slate-200 tabular-nums">₹{gst.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Stamp Duty (0.003% on buy)</span>
                <span className="text-slate-200 tabular-nums">₹{stampDuty.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>SEBI Turnover Charges</span>
                <span className="text-slate-200 tabular-nums">₹{sebiCharges.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Estimated Slippage (5 bps)</span>
                <span className="text-slate-200 tabular-nums">₹{slippage.toFixed(2)}</span>
              </div>
            </div>

            <div className="space-y-3 pt-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Gross Gain:</span>
                <span className={`font-bold tabular-nums ${grossPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ₹{grossPnl.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-400">Total Statutory Costs:</span>
                <span className="text-red-400 font-bold tabular-nums">-₹{totalCosts.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-base font-bold pt-2 border-t border-slate-800">
                <span className="text-white">Net Realized P&L:</span>
                <span className={`tabular-nums ${netPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ₹{netPnl.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* RISK GUARD DEEP DIVE */}
      {/* ---------------------------------------------------------------------- */}
      <section id="risk-guard" className="px-4 max-w-7xl mx-auto space-y-8">
        <div className="text-center space-y-3">
          <span className="text-xs font-mono font-semibold uppercase tracking-wider text-teal-400">
            Safety First
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold text-white">
            Risk Guard: Two Levels of Capital Protection
          </h2>
          <p className="text-slate-400 max-w-xl mx-auto text-sm">
            Algorithms fail when developers prioritize features over safeguards. In TradeForge, Risk Guard cannot be overridden.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Sliders className="w-5 h-5 text-teal-400" />
              <span>User-Configured Safeguards</span>
            </h3>
            <ul className="space-y-3 text-xs sm:text-sm text-slate-300">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                <span><strong>Capital Allocated</strong>: Strict limit on funds allocated to intraday trading.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                <span><strong>Daily Loss Ceiling</strong>: Once daily loss hits your threshold (e.g. ₹2,000), trading pauses immediately.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                <span><strong>Consecutive Loss Auto-Stop</strong>: 3 losses in a row pauses strategy for the day.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                <span><strong>Allowed Instruments</strong>: Restrict bot to trade only stocks you understand.</span>
              </li>
            </ul>
          </div>

          <div className="p-6 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Lock className="w-5 h-5 text-emerald-400" />
              <span>Platform-Level Safeguards (Non-Negotiable)</span>
            </h3>
            <ul className="space-y-3 text-xs sm:text-sm text-slate-300">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Illiquid Symbol Blacklist</strong>: Blocks penny stocks and illiquid ASM/GSM categories.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Fat-Finger Circuit</strong>: Orders deviating &gt; 2.5% from LTP are rejected.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>Idempotency Token Protection</strong>: Guarantees accidental double submissions are blocked.</span>
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <span><strong>15:15 IST Mandatory Square-Off</strong>: Flattens open positions before broker auto-squareoff charges apply.</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------------- */}
      {/* FREQUENTLY ASKED QUESTIONS */}
      {/* ---------------------------------------------------------------------- */}
      <section id="faq" className="px-4 max-w-4xl mx-auto space-y-8">
        <div className="text-center space-y-3">
          <h2 className="text-3xl font-bold text-white">Frequently Asked Questions</h2>
          <p className="text-slate-400 text-sm">
            Everything you need to know about compliance, safety, and operation.
          </p>
        </div>

        <div className="space-y-4 text-sm">
          <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
            <h4 className="font-bold text-white">Does TradeForge have access to my money?</h4>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              No. We use trade-only developer API tokens provided by SEBI-registered brokers. We cannot withdraw, transfer, or move your capital. Your funds never leave your own brokerage account.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
            <h4 className="font-bold text-white">Can TradeForge guarantee profit?</h4>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Absolutely not. Any platform claiming guaranteed returns is deceptive and violates SEBI regulations. What TradeForge provides is disciplined risk execution, automated bracket stop-losses, and elimination of emotional trading mistakes.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
            <h4 className="font-bold text-white">Is paper mode mandatory?</h4>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Yes. All newly registered accounts and strategies start in simulated paper mode. Real-money live trading can only be enabled explicitly after setting verified risk parameters and entering mandatory 2FA confirmation.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
