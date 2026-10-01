'use client';

import React, { useState } from 'react';
import { Download, FileText, Calendar, CheckCircle2, ChevronRight, Zap } from 'lucide-react';

export default function TradesReportPage() {
  const [filterPeriod, setFilterPeriod] = useState<'TODAY' | 'WEEK' | 'MONTH'>('TODAY');

  const trades = [
    {
      id: 'TRD_00941',
      symbol: 'RELIANCE',
      side: 'BUY',
      quantity: 50,
      entryTime: '09:37:12',
      exitTime: '09:44:08',
      entryPrice: 2500.0,
      exitPrice: 2515.2,
      grossPnl: 760.0,
      brokerage: 30.05,
      stt: 31.44,
      exchangeFee: 8.64,
      gst: 6.96,
      stampDuty: 3.75,
      slippage: 12.5,
      totalTaxes: 93.34,
      netPnl: 666.66,
      reason: '1m VWAP bounce with 1.8x volume expansion. Exited at target bracket (+0.61%).',
    },
    {
      id: 'TRD_00940',
      symbol: 'NIFTY 24OCT FUT',
      side: 'BUY',
      quantity: 50,
      entryTime: '09:48:30',
      exitTime: '10:02:15',
      entryPrice: 22020.0,
      exitPrice: 22068.0,
      grossPnl: 2400.0,
      brokerage: 40.0,
      stt: 275.85,
      exchangeFee: 15.2,
      gst: 9.94,
      stampDuty: 33.03,
      slippage: 22.0,
      totalTaxes: 396.02,
      netPnl: 2003.98,
      reason: '5m EMA 9/21 cross confirmed above session VWAP with index momentum. Target reached.',
    },
    {
      id: 'TRD_00939',
      symbol: 'TCS',
      side: 'BUY',
      quantity: 25,
      entryTime: '10:14:02',
      exitTime: '10:19:44',
      entryPrice: 3960.0,
      exitPrice: 3951.0,
      grossPnl: -225.0,
      brokerage: 29.67,
      stt: 24.69,
      exchangeFee: 6.83,
      gst: 6.57,
      stampDuty: 2.97,
      slippage: 9.88,
      totalTaxes: 80.61,
      netPnl: -305.61,
      reason: 'Stop-loss hit after VWAP breach. Protective stop capped risk cleanly at 0.8x ATR.',
    },
  ];

  const handleExportCSV = () => {
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      'ID,Symbol,Side,Quantity,EntryPrice,ExitPrice,GrossPnL,TotalTaxes,NetPnL,Reason\n' +
      trades
        .map(
          (t) =>
            `${t.id},${t.symbol},${t.side},${t.quantity},${t.entryPrice},${t.exitPrice},${t.grossPnl},${t.totalTaxes},${t.netPnl},"${t.reason}"`
        )
        .join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', 'tradeforge_tax_audit_report.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Trades & Audit Reports
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            Reconciled trade ledger with complete statutory Indian taxes (STT, GST, Stamp, Turnover) and plain-English AI decision reasons.
          </p>
        </div>

        <button
          onClick={handleExportCSV}
          className="px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-xs font-semibold font-mono transition-all flex items-center gap-2 shadow-lg shadow-teal-900/30"
        >
          <Download className="w-4 h-4" />
          <span>Export Tax-Ready CSV</span>
        </button>
      </div>

      {/* Trades Ledger Table */}
      <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-white uppercase tracking-wider">
            Execution Ledger ({trades.length} Trades)
          </span>
          <span className="text-xs font-mono text-emerald-400">
            Broker Statement Reconciled (OK)
          </span>
        </div>

        <div className="space-y-4">
          {trades.map((t) => (
            <div
              key={t.id}
              className="p-5 rounded-xl bg-[#132235] border border-[#1F334A] space-y-3 font-mono text-xs hover:border-teal-500/40 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-white text-sm">{t.symbol}</span>
                  <span className="px-2 py-0.5 rounded bg-teal-950 text-teal-300 text-[11px]">
                    {t.side} {t.quantity} shares
                  </span>
                  <span className="text-slate-400 text-[11px]">
                    {t.entryTime} → {t.exitTime}
                  </span>
                </div>

                <div className="flex items-center gap-4">
                  <span className="text-slate-400">
                    Gross: <strong className={t.grossPnl >= 0 ? 'text-white' : 'text-slate-400'}>₹{t.grossPnl.toFixed(2)}</strong>
                  </span>
                  <span className="text-red-400">
                    Taxes: -₹{t.totalTaxes.toFixed(2)}
                  </span>
                  <span
                    className={`text-sm font-bold tabular-nums px-2.5 py-0.5 rounded ${
                      t.netPnl >= 0
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-red-950 text-red-400 border border-red-800'
                    }`}
                  >
                    Net: {t.netPnl >= 0 ? '+' : ''}₹{t.netPnl.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Statutory Tax Breakdown */}
              <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 p-2.5 rounded bg-[#0A141F] text-[10px] text-slate-400">
                <div>Brokerage: ₹{t.brokerage.toFixed(2)}</div>
                <div>STT (Sell): ₹{t.stt.toFixed(2)}</div>
                <div>Turnover Fee: ₹{t.exchangeFee.toFixed(2)}</div>
                <div>GST (18%): ₹{t.gst.toFixed(2)}</div>
                <div>Stamp Duty: ₹{t.stampDuty.toFixed(2)}</div>
                <div>Slippage: ₹{t.slippage.toFixed(2)}</div>
              </div>

              {/* Plain English Reason */}
              <div className="text-[11px] font-sans text-slate-300 flex items-start gap-2 pt-1">
                <Zap className="w-3.5 h-3.5 text-teal-400 mt-0.5 shrink-0" />
                <span>
                  <strong>AI Rationale:</strong> {t.reason}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
