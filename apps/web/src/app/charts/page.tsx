'use client';

import React, { useState } from 'react';
import { BarChart3, Activity, Layers, Maximize2, Zap, ShieldCheck } from 'lucide-react';

export default function ChartsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE');
  const [timeframe, setTimeframe] = useState<'1m' | '5m' | '10m'>('1m');
  const [showVwap, setShowVwap] = useState(true);
  const [showEma, setShowEma] = useState(true);
  const [showSignals, setShowSignals] = useState(true);

  // Simulated candle bars
  const candles = [
    { time: '09:20', o: 2492.0, h: 2496.0, l: 2490.5, c: 2495.2, v: 5400, vwap: 2494.0 },
    { time: '09:21', o: 2495.2, h: 2498.0, l: 2493.0, c: 2497.0, v: 6200, vwap: 2495.5 },
    { time: '09:22', o: 2497.0, h: 2499.5, l: 2494.5, c: 2496.0, v: 4100, vwap: 2495.8 },
    { time: '09:23', o: 2496.0, h: 2497.5, l: 2491.0, c: 2492.5, v: 7800, vwap: 2494.8 },
    { time: '09:24', o: 2492.5, h: 2494.0, l: 2489.0, c: 2490.0, v: 9200, vwap: 2493.5 },
    { time: '09:25', o: 2490.0, h: 2495.0, l: 2489.5, c: 2494.5, v: 8100, vwap: 2493.8 },
    { time: '09:26', o: 2494.5, h: 2499.0, l: 2493.0, c: 2498.2, v: 11400, vwap: 2495.0 },
    { time: '09:27', o: 2498.2, h: 2503.0, l: 2497.5, c: 2501.0, v: 14200, vwap: 2496.8, signal: 'BUY (VWAP PULLBACK)' },
    { time: '09:28', o: 2501.0, h: 2505.5, l: 2500.0, c: 2504.8, v: 12800, vwap: 2498.2 },
    { time: '09:29', o: 2504.8, h: 2507.0, l: 2503.2, c: 2506.0, v: 9500, vwap: 2499.5 },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      {/* Chart Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] shadow-xl">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold text-white">{selectedSymbol}</span>
            <span className="text-xs font-mono text-slate-400">NSE • EQ</span>
            <span className="text-lg font-mono font-bold text-emerald-400 tabular-nums">₹2,506.00</span>
            <span className="text-xs font-mono text-emerald-400">(+0.56%)</span>
          </div>

          <div className="flex items-center gap-1 bg-[#132235] p-1 rounded-lg border border-[#1F334A] text-xs font-mono">
            {(['1m', '5m', '10m'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 rounded transition-all ${
                  timeframe === tf ? 'bg-teal-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Indicator Toggles */}
        <div className="flex items-center gap-2 text-xs font-mono">
          <button
            onClick={() => setShowVwap(!showVwap)}
            className={`px-2.5 py-1 rounded border transition-all ${
              showVwap
                ? 'bg-amber-950 text-amber-300 border-amber-800 font-bold'
                : 'bg-[#132235] text-slate-400 border-[#1F334A]'
            }`}
          >
            VWAP
          </button>
          <button
            onClick={() => setShowEma(!showEma)}
            className={`px-2.5 py-1 rounded border transition-all ${
              showEma
                ? 'bg-blue-950 text-blue-300 border-blue-800 font-bold'
                : 'bg-[#132235] text-slate-400 border-[#1F334A]'
            }`}
          >
            EMA 9/21
          </button>
          <button
            onClick={() => setShowSignals(!showSignals)}
            className={`px-2.5 py-1 rounded border transition-all ${
              showSignals
                ? 'bg-teal-950 text-teal-300 border-teal-800 font-bold'
                : 'bg-[#132235] text-slate-400 border-[#1F334A]'
            }`}
          >
            AI Signals Overlay
          </button>
        </div>
      </div>

      {/* Main Chart Canvas Container */}
      <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-6 shadow-2xl">
        <div className="h-96 rounded-xl bg-[#070D14] border border-[#1F334A] p-6 relative flex flex-col justify-between font-mono text-xs overflow-hidden">
          {/* Price Scale Lines */}
          <div className="absolute inset-0 flex flex-col justify-between p-6 pointer-events-none opacity-20">
            <div className="border-b border-slate-700 w-full flex justify-end"><span>₹2,510.00</span></div>
            <div className="border-b border-slate-700 w-full flex justify-end"><span>₹2,505.00</span></div>
            <div className="border-b border-slate-700 w-full flex justify-end"><span>₹2,500.00</span></div>
            <div className="border-b border-slate-700 w-full flex justify-end"><span>₹2,495.00</span></div>
            <div className="border-b border-slate-700 w-full flex justify-end"><span>₹2,490.00</span></div>
          </div>

          {/* Candle Bars Rendering */}
          <div className="h-full flex items-end justify-between px-4 z-10">
            {candles.map((c, i) => {
              const isGreen = c.c >= c.o;
              const heightPct = ((c.c - 2488) / (2510 - 2488)) * 100;
              return (
                <div key={i} className="flex flex-col items-center gap-1 group relative">
                  {/* AI Signal Tag */}
                  {c.signal && showSignals && (
                    <div className="absolute -top-12 z-20 px-2 py-1 rounded bg-teal-500 text-slate-950 font-bold text-[10px] whitespace-nowrap shadow-lg animate-bounce flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      <span>{c.signal}</span>
                    </div>
                  )}

                  {/* High/Low Wick */}
                  <div
                    className={`w-0.5 ${isGreen ? 'bg-emerald-400' : 'bg-red-400'}`}
                    style={{ height: '70px' }}
                  ></div>

                  {/* Candle Body */}
                  <div
                    className={`w-4 rounded-sm transition-all ${
                      isGreen ? 'bg-emerald-500 hover:bg-emerald-400' : 'bg-red-500 hover:bg-red-400'
                    }`}
                    style={{ height: `${Math.max(12, Math.abs(c.c - c.o) * 12)}px` }}
                  ></div>

                  <span className="text-[10px] text-slate-500 mt-2">{c.time}</span>
                </div>
              );
            })}
          </div>

          {/* Chart Overlay Badges */}
          <div className="z-10 flex items-center justify-between border-t border-slate-800 pt-3 text-[11px] text-slate-400">
            <div className="flex items-center gap-4">
              {showVwap && <span className="text-amber-400">VWAP: ₹2,499.50</span>}
              {showEma && <span className="text-blue-400">EMA(9): ₹2,503.20</span>}
              {showEma && <span className="text-indigo-400">EMA(21): ₹2,497.80</span>}
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Live Tick Broadcast Active (42ms)</span>
            </div>
          </div>
        </div>

        {/* Active Trade Bracket Overlay Details */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
          <div className="p-4 rounded-xl bg-[#132235] border border-red-900/40 space-y-1">
            <span className="text-slate-400">Protective Stop-Loss (Bracket)</span>
            <span className="text-base font-bold text-red-400 block">₹2,490.00 (-₹11.00)</span>
            <span className="text-[10px] text-slate-400">Sent with entry • 0.8x ATR</span>
          </div>
          <div className="p-4 rounded-xl bg-[#132235] border border-teal-900/40 space-y-1">
            <span className="text-slate-400">Filled Entry Price</span>
            <span className="text-base font-bold text-white block">₹2,501.00</span>
            <span className="text-[10px] text-teal-400">50 Shares • Paper Mode</span>
          </div>
          <div className="p-4 rounded-xl bg-[#132235] border border-emerald-900/40 space-y-1">
            <span className="text-slate-400">Take-Profit Target</span>
            <span className="text-base font-bold text-emerald-400 block">₹2,520.00 (+₹19.00)</span>
            <span className="text-[10px] text-slate-400">+0.76% Projected Gross</span>
          </div>
        </div>
      </div>
    </div>
  );
}
