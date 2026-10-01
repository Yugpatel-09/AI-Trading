'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sliders, ShieldCheck, AlertCircle, ArrowRight, Lock } from 'lucide-react';

export default function OnboardingPage() {
  const router = useRouter();
  const [capital, setCapital] = useState(100000);
  const [maxLossPerTrade, setMaxLossPerTrade] = useState(1000);
  const [maxDailyLoss, setMaxDailyLoss] = useState(3000);
  const [maxOpenPositions, setMaxOpenPositions] = useState(2);
  const [maxDailyTrades, setMaxDailyTrades] = useState(8);
  const [tradingMode, setTradingMode] = useState<'PAPER' | 'APPROVE' | 'AUTO'>('PAPER');
  const [selectedInstruments, setSelectedInstruments] = useState<string[]>([
    'NIFTY',
    'BANKNIFTY',
    'RELIANCE',
    'TCS',
    'HDFCBANK',
  ]);
  const [saved, setSaved] = useState(false);

  const availableInstruments = [
    'NIFTY',
    'BANKNIFTY',
    'FINNIFTY',
    'RELIANCE',
    'TCS',
    'HDFCBANK',
    'INFY',
    'ICICIBANK',
    'SBIN',
    'BHARTIARTL',
  ];

  const toggleInstrument = (symbol: string) => {
    if (selectedInstruments.includes(symbol)) {
      if (selectedInstruments.length > 1) {
        setSelectedInstruments(selectedInstruments.filter((s) => s !== symbol));
      }
    } else {
      setSelectedInstruments([...selectedInstruments, symbol]);
    }
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => {
      router.push('/dashboard');
    }, 600);
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Risk Guard Setup & Guardrails
        </h1>
        <p className="text-xs sm:text-sm text-slate-400">
          Configure your personal safety boundaries. In TradeForge, orders exceeding your loss limits or position caps are rejected before reaching the broker.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Capital Allocation & Rupee Limits */}
        <div className="p-6 sm:p-8 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-6 shadow-xl">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Sliders className="w-4 h-4 text-teal-400" />
            <span>Capital & Loss Ceilings</span>
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <label className="text-slate-300">Intraday Capital Allocated (₹)</label>
                <span className="text-white font-bold tabular-nums">₹{capital.toLocaleString('en-IN')}</span>
              </div>
              <input
                type="range"
                min={10000}
                max={500000}
                step={5000}
                value={capital}
                onChange={(e) => setCapital(Number(e.target.value))}
                className="w-full accent-teal-500"
              />
              <span className="text-[11px] text-slate-400">Trading capital at risk in intraday session.</span>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <label className="text-slate-300">Max Loss Per Trade (₹)</label>
                <span className="text-amber-400 font-bold tabular-nums">₹{maxLossPerTrade.toLocaleString('en-IN')}</span>
              </div>
              <input
                type="range"
                min={200}
                max={5000}
                step={100}
                value={maxLossPerTrade}
                onChange={(e) => setMaxLossPerTrade(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
              <span className="text-[11px] text-slate-400">Position size automatically downscaled so risk ≤ ₹{maxLossPerTrade}.</span>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <label className="text-slate-300">Max Daily Loss Limit (₹)</label>
                <span className="text-red-400 font-bold tabular-nums">₹{maxDailyLoss.toLocaleString('en-IN')}</span>
              </div>
              <input
                type="range"
                min={1000}
                max={20000}
                step={500}
                value={maxDailyLoss}
                onChange={(e) => setMaxDailyLoss(Number(e.target.value))}
                className="w-full accent-red-500"
              />
              <span className="text-[11px] text-slate-400">Trading pauses for entire day if cumulative loss hits this ceiling.</span>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <label className="text-slate-300">Max Concurrent Positions</label>
                <span className="text-white font-bold tabular-nums">{maxOpenPositions} positions</span>
              </div>
              <input
                type="range"
                min={1}
                max={4}
                step={1}
                value={maxOpenPositions}
                onChange={(e) => setMaxOpenPositions(Number(e.target.value))}
                className="w-full accent-teal-500"
              />
              <span className="text-[11px] text-slate-400">Prevents portfolio overextension.</span>
            </div>
          </div>
        </div>

        {/* Trading Mode Selection */}
        <div className="p-6 sm:p-8 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
          <h3 className="text-base font-bold text-white">Default Execution Mode</h3>
          <p className="text-xs text-slate-400">
            Paper mode is mandatory for new accounts. Live modes can be activated when ready.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div
              onClick={() => setTradingMode('PAPER')}
              className={`p-4 rounded-xl border cursor-pointer space-y-2 ${
                tradingMode === 'PAPER'
                  ? 'bg-[#132235] border-teal-500 shadow-md'
                  : 'bg-[#0A141F] border-[#1F334A] hover:border-slate-600'
              }`}
            >
              <div className="flex justify-between font-bold text-white">
                <span>Paper Mode</span>
                <span className="text-teal-400 font-mono">(Default)</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Virtual money on real-time live prices. Zero capital risk. Best for testing strategies and costs.
              </p>
            </div>

            <div
              onClick={() => setTradingMode('APPROVE')}
              className={`p-4 rounded-xl border cursor-pointer space-y-2 ${
                tradingMode === 'APPROVE'
                  ? 'bg-[#132235] border-amber-500 shadow-md'
                  : 'bg-[#0A141F] border-[#1F334A] hover:border-slate-600'
              }`}
            >
              <div className="flex justify-between font-bold text-white">
                <span>Approve Mode</span>
                <span className="text-amber-400 font-mono">(Recommended)</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                AI proposes the trade with plain-English reasons. You tap approve on mobile/web before order fires.
              </p>
            </div>

            <div
              onClick={() => setTradingMode('AUTO')}
              className={`p-4 rounded-xl border cursor-pointer space-y-2 ${
                tradingMode === 'AUTO'
                  ? 'bg-[#132235] border-red-500 shadow-md'
                  : 'bg-[#0A141F] border-[#1F334A] hover:border-slate-600'
              }`}
            >
              <div className="flex justify-between font-bold text-white">
                <span>Auto Mode</span>
                <span className="text-red-400 font-mono">(Advanced)</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Autonomous order routing strictly bounded by your Risk Guard loss limits. Requires 2FA confirmation.
              </p>
            </div>
          </div>
        </div>

        {/* Allowed Instruments */}
        <div className="p-6 sm:p-8 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
          <h3 className="text-base font-bold text-white">Allowed Liquid Instruments</h3>
          <p className="text-xs text-slate-400">
            Select the stocks and indices the AI is permitted to trade. Illiquid stocks are permanently blocked.
          </p>

          <div className="flex flex-wrap gap-2">
            {availableInstruments.map((sym) => {
              const active = selectedInstruments.includes(sym);
              return (
                <button
                  type="button"
                  key={sym}
                  onClick={() => toggleInstrument(sym)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold transition-all border ${
                    active
                      ? 'bg-teal-600 text-white border-teal-500'
                      : 'bg-[#132235] text-slate-400 border-[#1F334A] hover:text-white'
                  }`}
                >
                  {sym}
                </button>
              );
            })}
          </div>
        </div>

        <button
          type="submit"
          className="w-full py-3 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all shadow-xl shadow-teal-900/40 flex items-center justify-center gap-2"
        >
          <span>{saved ? 'Activating Guardrails...' : 'Save Guardrails & Launch Dashboard'}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
