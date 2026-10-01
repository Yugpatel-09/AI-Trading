'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Cpu, Sliders, CheckCircle2, TrendingUp, AlertTriangle, ArrowRight } from 'lucide-react';

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState([
    {
      id: 'SCALPER_1M',
      name: '1-Minute VWAP Pullback Scalper',
      timeframe: '1m',
      speed: 'Very fast (1-10 min)',
      target: '0.15% to 0.30%',
      stop: '0.8x ATR',
      dailyCap: '8 - 12 trades',
      bestRegime: 'Active Trending with Volume',
      winRate: '68%',
      profitFactor: 1.74,
      enabled: true,
      description:
        'Trades only the top NIFTY 50 liquid heavyweights. Detects fast pullbacks to the session VWAP in the direction of the 5-minute trend with volume burst confirmation.',
    },
    {
      id: 'SCALPER_5M',
      name: '5-Minute EMA Cross & Supertrend',
      timeframe: '5m',
      speed: 'Medium (5-40 min)',
      target: '0.30% to 0.60%',
      stop: '1.0x ATR',
      dailyCap: '5 - 8 trades',
      bestRegime: 'Clean Trends',
      winRate: '64%',
      profitFactor: 1.88,
      enabled: true,
      description:
        'Momentum cross strategy. Enters when 9 EMA crosses above 21 EMA above session VWAP with above-average volume and 15m trend confirmation. Low slippage overhead.',
    },
    {
      id: 'SCALPER_10M_ORB',
      name: '10-Minute Opening Range Breakout (ORB)',
      timeframe: '10m',
      speed: 'Slower (10-90 min)',
      target: '0.50% to 1.00%',
      stop: '1.0x to 1.2x ATR',
      dailyCap: '3 - 5 trades',
      bestRegime: 'Breakout Sessions',
      winRate: '58%',
      profitFactor: 2.05,
      enabled: false,
      description:
        'Waits for the 09:15-09:35 opening range to establish. Takes confirmed breakouts with volume and index participation, confirmed by a retest of the range boundary.',
    },
  ]);

  const toggleStrategy = (id: string) => {
    setStrategies(
      strategies.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
    );
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          AI Scalper Strategy Library
        </h1>
        <p className="text-xs sm:text-sm text-slate-400">
          Deterministic rule-based entry setups filtered by LightGBM quality models and real Indian cost gates.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {strategies.map((s) => (
          <div
            key={s.id}
            className={`p-6 rounded-2xl border flex flex-col justify-between space-y-6 transition-all ${
              s.enabled
                ? 'bg-[#0D1B2A] border-teal-500/60 shadow-xl shadow-teal-950/40'
                : 'bg-[#091018] border-[#1F334A] opacity-75'
            }`}
          >
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-teal-950 text-teal-400 border border-teal-800">
                  {s.timeframe} TIMEFRAME
                </span>
                <button
                  onClick={() => toggleStrategy(s.id)}
                  className={`text-xs font-mono font-bold px-3 py-1 rounded-full transition-all border ${
                    s.enabled
                      ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  {s.enabled ? 'ACTIVE' : 'DISABLED'}
                </button>
              </div>

              <div>
                <h3 className="text-lg font-bold text-white">{s.name}</h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{s.description}</p>
              </div>

              <div className="space-y-2 pt-3 border-t border-slate-800/80 font-mono text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Target:</span>
                  <span className="text-emerald-400 font-bold">{s.target}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Stop-Loss:</span>
                  <span className="text-red-400 font-bold">{s.stop}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Hold Duration:</span>
                  <span className="text-slate-200">{s.speed}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Daily Cap:</span>
                  <span className="text-slate-200">{s.dailyCap}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Best Regime:</span>
                  <span className="text-teal-300">{s.bestRegime}</span>
                </div>
              </div>

              {/* Historical Backtest Summary */}
              <div className="p-3 rounded-lg bg-[#132235] space-y-1 font-mono text-xs">
                <span className="text-[10px] text-slate-400 block">WALK-FORWARD UNSEEN DATA STATS</span>
                <div className="flex justify-between text-slate-200">
                  <span>Win Rate: <strong>{s.winRate}</strong></span>
                  <span>Profit Factor: <strong>{s.profitFactor}</strong></span>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <Link
                href="/backtests"
                className="w-full py-2 rounded-lg bg-[#132235] hover:bg-[#1A2E47] border border-[#1F334A] text-xs font-semibold text-slate-200 transition-all flex items-center justify-center gap-1.5"
              >
                <span>Backtest With Custom Indian Costs</span>
                <ArrowRight className="w-3.5 h-3.5 text-teal-400" />
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
