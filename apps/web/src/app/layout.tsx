import type { Metadata } from 'next';
import './globals.css';
import { ShieldCheck, Activity, AlertTriangle } from 'lucide-react';

export const metadata: Metadata = {
  title: 'TradeForge — AI Trading Platform for NSE Intraday',
  description:
    'Institutional-grade AI intraday execution platform for Indian equities. Features 1m, 5m, and 10m scalpers, strict standalone RiskGuard, statutory cost modeling, and paper-mode verification.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0A141F] text-[#F1F5F9] antialiased">
        {/* Mandatory SEBI & Statutory Risk Disclosure Top Bar */}
        <div className="bg-[#132235] border-b border-[#1F334A] py-1.5 px-4 text-xs text-slate-300">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-amber-400 font-medium">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>SEBI Risk Warning:</span>
              <span className="text-slate-300 font-normal">
                9 out of 10 individual traders in Indian intraday & F&O markets incur net financial losses. Past backtests do not guarantee future profits.
              </span>
            </div>
            <div className="flex items-center gap-4 text-slate-400 text-[11px]">
              <span className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                NSE Live Feed: Connected (42ms)
              </span>
              <span className="bg-[#1F334A] px-2 py-0.5 rounded text-teal-300 font-mono font-medium">
                PAPER MODE ACTIVE
              </span>
            </div>
          </div>
        </div>

        {/* Global Navigation Header */}
        <header className="sticky top-0 z-50 backdrop-blur-md bg-[#0A141F]/90 border-b border-[#1F334A]">
          <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
            <div className="flex items-center gap-8">
              <a href="/" className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-teal-500 to-teal-700 flex items-center justify-center shadow-lg shadow-teal-500/20">
                  <Activity className="w-5 h-5 text-white" />
                </div>
                <div className="flex flex-col">
                  <span className="text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
                    TradeForge
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-teal-500/10 text-teal-400 border border-teal-500/30">
                      NSE Intraday
                    </span>
                  </span>
                </div>
              </a>

              <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-300">
                <a href="#how-it-works" className="hover:text-teal-400 transition-colors">How It Works</a>
                <a href="#scalpers" className="hover:text-teal-400 transition-colors">AI Scalpers</a>
                <a href="#risk-guard" className="hover:text-teal-400 transition-colors">Risk Guard</a>
                <a href="#costs" className="hover:text-teal-400 transition-colors">Cost Engine</a>
                <a href="#faq" className="hover:text-teal-400 transition-colors">FAQ</a>
              </nav>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden sm:flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2.5 py-1 rounded-md">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>RiskGuard: ARMED</span>
              </div>
              <a
                href="#demo"
                className="text-xs sm:text-sm font-semibold px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white shadow-md shadow-teal-600/20 transition-all flex items-center gap-1.5"
              >
                <span>Launch Demo</span>
              </a>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <main>{children}</main>

        {/* Comprehensive Risk & Statutory Footer */}
        <footer className="bg-[#070D14] border-t border-[#1F334A] py-12 px-4 text-xs text-slate-400">
          <div className="max-w-7xl mx-auto space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
              <div className="space-y-3">
                <span className="text-white font-bold text-sm">TradeForge</span>
                <p className="text-slate-400 leading-relaxed text-xs">
                  Institutional discipline engineering for Indian retail traders. Built on standalone risk isolation, statutory cost factoring, and deterministic execution.
                </p>
              </div>
              <div>
                <h4 className="text-white font-semibold mb-2">Supported Brokers</h4>
                <ul className="space-y-1 text-slate-400">
                  <li>Zerodha (Kite Connect API)</li>
                  <li>Upstox (v2 API)</li>
                  <li>Angel One (SmartAPI)</li>
                  <li>Dhan (HQ API)</li>
                  <li>Groww (Waitlist)</li>
                </ul>
              </div>
              <div>
                <h4 className="text-white font-semibold mb-2">Core Features</h4>
                <ul className="space-y-1 text-slate-400">
                  <li>1m VWAP Pullback Scalper</li>
                  <li>5m EMA/Supertrend Cross</li>
                  <li>10m Opening Range Breakout</li>
                  <li>Mandatory Stop-loss Bracket</li>
                  <li>15:15 IST Auto Square-off</li>
                </ul>
              </div>
              <div>
                <h4 className="text-white font-semibold mb-2">Compliance & Data</h4>
                <ul className="space-y-1 text-slate-400">
                  <li>India DPDP Act Compliant</li>
                  <li>Zero Fund Custody (Non-custodial)</li>
                  <li>AES-256 Encrypted Token Vault</li>
                  <li>No Profit Guarantees</li>
                </ul>
              </div>
            </div>

            <div className="pt-6 border-t border-slate-800 text-[11px] text-slate-400 leading-relaxed">
              <p>
                <strong>Statutory Notice:</strong> TradeForge does not solicit investment capital or offer Portfolio Management Services (PMS). TradeForge is an algorithmic software application that interfaces with user-owned accounts at SEBI-registered brokers via approved developer APIs. Users retain sole discretion and custody over their capital and orders at all times.
              </p>
              <p className="mt-2">
                © {new Date().getFullYear()} TradeForge Technologies. All rights reserved.
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
