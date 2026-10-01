'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  TrendingUp,
  TrendingDown,
  ShieldCheck,
  AlertOctagon,
  Pause,
  Play,
  Activity,
  Layers,
  Zap,
  CheckCircle2,
  Clock,
  ExternalLink,
  ChevronRight,
} from 'lucide-react';

export default function DashboardPage() {
  const [tradingPaused, setTradingPaused] = useState(false);
  const [killSwitchTriggered, setKillSwitchTriggered] = useState(false);
  const [showConfirmAuto, setShowConfirmAuto] = useState(false);
  const [currentMode, setCurrentMode] = useState<'PAPER' | 'APPROVE' | 'AUTO'>('PAPER');

  // Simulated open positions
  const [positions, setPositions] = useState([
    {
      symbol: 'RELIANCE',
      side: 'BUY',
      quantity: 50,
      entryPrice: 2500.0,
      currentPrice: 2508.4,
      stopLoss: 2490.0,
      target: 2520.0,
      grossPnl: 420.0,
      statutoryTaxes: 48.2,
      netPnl: 371.8,
      openedAt: '09:37:12 IST',
      strategy: '1m VWAP Pullback',
    },
    {
      symbol: 'NIFTY 24OCT FUT',
      side: 'BUY',
      quantity: 50,
      entryPrice: 22010.0,
      currentPrice: 22045.0,
      stopLoss: 21970.0,
      target: 22100.0,
      grossPnl: 1750.0,
      statutoryTaxes: 125.4,
      netPnl: 1624.6,
      openedAt: '09:42:05 IST',
      strategy: '5m EMA Cross',
    },
  ]);

  // Simulated plain-English AI signal proposals (Specialist 2 & 3)
  const signals = [
    {
      id: 'sig_rel_1',
      symbol: 'RELIANCE',
      timeframe: '1m',
      strategy: '1m VWAP Scalper',
      time: '09:37:05 IST',
      entry: 2500.0,
      stop: 2490.0,
      target: 2520.0,
      qualityScore: 0.82,
      status: 'EXECUTED (PAPER)',
      reason:
        'Price retested the session VWAP (₹2,499.20) in an active 5m bullish trend. 1.8x volume spike confirmed buying absorption. Risk is capped at ₹500.',
    },
    {
      id: 'sig_nifty_2',
      symbol: 'NIFTY 24OCT FUT',
      timeframe: '5m',
      strategy: '5m EMA Cross',
      time: '09:41:50 IST',
      entry: 22010.0,
      stop: 21970.0,
      target: 22100.0,
      qualityScore: 0.79,
      status: 'EXECUTED (PAPER)',
      reason:
        'EMA 9 crossed above EMA 21 on the 5m bar while holding above VWAP with above-average volume. Stop placed at 1.0x ATR.',
    },
    {
      id: 'sig_tcs_3',
      symbol: 'TCS',
      timeframe: '1m',
      strategy: '1m VWAP Scalper',
      time: '09:48:20 IST',
      entry: 3950.0,
      stop: 3942.0,
      target: 3968.0,
      qualityScore: 0.61,
      status: 'REJECTED (COST GATE)',
      reason:
        'Setup rejected: Expected gross gain of ₹18.00 cannot reliably exceed total round-trip statutory costs & slippage of ₹14.50. Cost buffer below 1.5x minimum.',
    },
  ];

  const totalGross = positions.reduce((acc, p) => acc + p.grossPnl, 0);
  const totalTaxes = positions.reduce((acc, p) => acc + p.statutoryTaxes, 0);
  const totalNet = positions.reduce((acc, p) => acc + p.netPnl, 0);

  const handleModeChange = (mode: 'PAPER' | 'APPROVE' | 'AUTO') => {
    if (mode === 'AUTO') {
      setShowConfirmAuto(true);
    } else {
      setCurrentMode(mode);
    }
  };

  const handleConfirmAuto = () => {
    setCurrentMode('AUTO');
    setShowConfirmAuto(false);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      {/* Top Banner: Mode & Emergency Safeguards */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <span className="text-xl font-bold text-white">Live Execution Terminal</span>
            <span
              className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                currentMode === 'PAPER'
                  ? 'bg-teal-950 text-teal-400 border-teal-700'
                  : currentMode === 'APPROVE'
                  ? 'bg-amber-950 text-amber-400 border-amber-700'
                  : 'bg-red-950 text-red-400 border-red-700'
              }`}
            >
              [{currentMode} MODE]
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Real-time feed connected • Next auto square-off at 15:15 IST • Pre-trade RiskGuard active
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          {/* Mode Selector */}
          <div className="flex items-center gap-1 bg-[#132235] p-1 rounded-lg border border-[#1F334A] text-xs font-mono">
            <button
              onClick={() => handleModeChange('PAPER')}
              className={`px-3 py-1.5 rounded transition-all ${
                currentMode === 'PAPER' ? 'bg-teal-600 text-white font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Paper
            </button>
            <button
              onClick={() => handleModeChange('APPROVE')}
              className={`px-3 py-1.5 rounded transition-all ${
                currentMode === 'APPROVE' ? 'bg-amber-600 text-white font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Approve
            </button>
            <button
              onClick={() => handleModeChange('AUTO')}
              className={`px-3 py-1.5 rounded transition-all ${
                currentMode === 'AUTO' ? 'bg-red-600 text-white font-bold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Auto
            </button>
          </div>

          {/* Pause Button */}
          <button
            onClick={() => setTradingPaused(!tradingPaused)}
            className={`px-3.5 py-2 rounded-lg text-xs font-mono font-semibold transition-all flex items-center gap-1.5 border ${
              tradingPaused
                ? 'bg-amber-600 text-white border-amber-500'
                : 'bg-[#132235] text-slate-200 border-[#1F334A] hover:bg-[#1A2E47]'
            }`}
          >
            {tradingPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
            <span>{tradingPaused ? 'RESUME' : 'PAUSE'}</span>
          </button>

          {/* Big Emergency Kill Button */}
          <button
            onClick={() => setKillSwitchTriggered(!killSwitchTriggered)}
            className={`px-4 py-2 rounded-lg text-xs font-mono font-bold transition-all flex items-center gap-1.5 shadow-lg ${
              killSwitchTriggered
                ? 'bg-amber-600 text-white shadow-amber-900/40'
                : 'bg-red-600 hover:bg-red-500 text-white shadow-red-900/40'
            }`}
          >
            <AlertOctagon className="w-4 h-4" />
            <span>{killSwitchTriggered ? 'RESET HALT' : 'KILL SWITCH'}</span>
          </button>
        </div>
      </div>

      {/* Emergency Kill Banner if triggered */}
      {killSwitchTriggered && (
        <div className="p-4 rounded-xl bg-red-950/90 border border-red-700 text-red-200 text-xs flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertOctagon className="w-6 h-6 text-red-400 shrink-0 animate-pulse" />
            <div>
              <strong className="block text-white text-sm">EMERGENCY KILL SWITCH ENGAGED</strong>
              <span>
                All open orders have been cancelled. Position square-off dispatched. Inbound AI signals blocked.
              </span>
            </div>
          </div>
          <button
            onClick={() => setKillSwitchTriggered(false)}
            className="px-3 py-1 rounded bg-red-800 hover:bg-red-700 text-white font-mono text-xs"
          >
            Acknowledge & Clear
          </button>
        </div>
      )}

      {/* Metric Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
          <span className="text-xs font-mono text-slate-400">TODAY&apos;S NET P&L</span>
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono text-emerald-400 tabular-nums">
              +₹{totalNet.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800">
              NET PROFIT
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono block">
            Gross: +₹{totalGross.toFixed(2)} • Taxes: -₹{totalTaxes.toFixed(2)}
          </span>
        </div>

        <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
          <span className="text-xs font-mono text-slate-400">DAILY RISK GUARD LIMITS</span>
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono text-white tabular-nums">₹0 / ₹3,000</span>
            <span className="text-xs font-mono text-teal-400 bg-teal-950/40 px-2 py-0.5 rounded border border-teal-800">
              0% USED
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono block">
            Max trades: 2 / 8 completed
          </span>
        </div>

        <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
          <span className="text-xs font-mono text-slate-400">ACTIVE POSITIONS</span>
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono text-white tabular-nums">
              {positions.length} Open
            </span>
            <span className="text-xs font-mono text-slate-300 bg-[#132235] px-2 py-0.5 rounded">
              Max 3 Allowed
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono block">
            Bracket stops active on all entries
          </span>
        </div>

        <div className="p-5 rounded-xl bg-[#0D1B2A] border border-[#1F334A] space-y-2">
          <span className="text-xs font-mono text-slate-400">TELEMETRY & FEED</span>
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold font-mono text-emerald-400 tabular-nums">42 ms</span>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800">
              HEALTHY
            </span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono block">
            NSE Live • Watchdog armed (&lt;5s threshold)
          </span>
        </div>
      </div>

      {/* Active Positions Table */}
      <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <span>Open Intraday Positions</span>
            <span className="text-xs font-mono text-teal-400">({positions.length})</span>
          </h3>
          <span className="text-xs font-mono text-slate-400">
            Mandatory stops placed at entry
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead>
              <tr className="border-b border-[#1F334A] text-slate-400">
                <th className="pb-3 font-semibold">INSTRUMENT</th>
                <th className="pb-3 font-semibold">STRATEGY</th>
                <th className="pb-3 font-semibold">QTY</th>
                <th className="pb-3 font-semibold">ENTRY</th>
                <th className="pb-3 font-semibold">LTP</th>
                <th className="pb-3 font-semibold">STOP BRACKET</th>
                <th className="pb-3 font-semibold">TARGET</th>
                <th className="pb-3 font-semibold">TAXES</th>
                <th className="pb-3 font-semibold text-right">NET P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1F334A]/50">
              {positions.map((pos, i) => (
                <tr key={i} className="hover:bg-[#132235]/40 transition-colors">
                  <td className="py-3 font-bold text-white">{pos.symbol}</td>
                  <td className="py-3 text-slate-300">{pos.strategy}</td>
                  <td className="py-3 text-slate-200">{pos.quantity}</td>
                  <td className="py-3 text-slate-200">₹{pos.entryPrice.toFixed(2)}</td>
                  <td className="py-3 text-emerald-400 font-bold">₹{pos.currentPrice.toFixed(2)}</td>
                  <td className="py-3 text-red-400">₹{pos.stopLoss.toFixed(2)}</td>
                  <td className="py-3 text-emerald-400">₹{pos.target.toFixed(2)}</td>
                  <td className="py-3 text-slate-400">₹{pos.statutoryTaxes.toFixed(2)}</td>
                  <td className="py-3 text-right font-bold text-emerald-400 tabular-nums">
                    +₹{pos.netPnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Explainable AI Live Signals Feed */}
      <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Zap className="w-4 h-4 text-teal-400" />
              <span>Real-Time AI Signals Feed & Plain-English Explanations</span>
            </h3>
            <p className="text-xs text-slate-400">
              Specialist 2 (Rules) + Specialist 3 (Quality Model) + Specialist 4 (Cost Gate)
            </p>
          </div>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-950/40 px-2.5 py-1 rounded border border-emerald-800">
            AUTO-STREAMING
          </span>
        </div>

        <div className="space-y-3">
          {signals.map((sig) => (
            <div
              key={sig.id}
              className="p-4 rounded-xl bg-[#132235] border border-[#1F334A] space-y-2 hover:border-teal-500/40 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">{sig.symbol}</span>
                  <span className="px-2 py-0.5 rounded bg-[#1F334A] text-teal-300">{sig.strategy}</span>
                  <span className="text-slate-400">{sig.time}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-slate-300">
                    Quality: <strong className="text-teal-400">{(sig.qualityScore * 100).toFixed(0)}%</strong>
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded font-bold ${
                      sig.status.includes('EXECUTED')
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-red-950 text-red-400 border border-red-800'
                    }`}
                  >
                    {sig.status}
                  </span>
                </div>
              </div>

              <p className="text-xs text-slate-300 font-sans leading-relaxed">
                &ldquo;{sig.reason}&rdquo;
              </p>

              <div className="flex items-center gap-4 text-[11px] font-mono text-slate-400 border-t border-slate-800 pt-2">
                <span>Entry: ₹{sig.entry.toFixed(2)}</span>
                <span>Stop: ₹{sig.stop.toFixed(2)}</span>
                <span>Target: ₹{sig.target.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Confirmation Modal for Auto Mode (Non-negotiable Rule 2) */}
      {showConfirmAuto && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-[#0D1B2A] border border-amber-600/60 p-6 rounded-2xl space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-amber-400 font-bold text-base">
              <AlertOctagon className="w-5 h-5" />
              <span>Confirm Switch to Autonomous Mode</span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              In <strong>Auto Mode</strong>, approved orders are dispatched autonomously to your broker account without manual per-trade approval. Orders remain strictly bounded by your configured Risk Guard daily loss ceilings.
            </p>
            <div className="p-3 rounded bg-amber-950/50 border border-amber-800 text-[11px] text-amber-200 font-mono">
              2FA Verification confirmed. Emergency Kill Switch remains armed at all times.
            </div>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setShowConfirmAuto(false)}
                className="px-4 py-2 rounded-lg bg-[#132235] text-xs font-semibold text-slate-300 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmAuto}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-xs font-semibold text-white font-mono"
              >
                Enable Auto Mode
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
