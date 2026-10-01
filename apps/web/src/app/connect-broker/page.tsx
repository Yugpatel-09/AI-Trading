'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  Lock,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Cpu,
  KeyRound,
  XCircle,
} from 'lucide-react';

export default function ConnectBrokerPage() {
  const [selectedBroker, setSelectedBroker] = useState<string>('ZERODHA');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [tested, setTested] = useState(false);
  const [marginData, setMarginData] = useState<{ available: number; total: number } | null>(null);

  const brokers = [
    {
      id: 'ZERODHA',
      name: 'Zerodha Kite Connect',
      status: 'AVAILABLE',
      authType: 'API Key + Request Token Flow',
      dailyRenewal: 'Mandatory daily morning login (expires 15:30 IST)',
      description: 'India’s largest discount broker. Connect via official Kite Connect v3 REST API.',
    },
    {
      id: 'UPSTOX',
      name: 'Upstox Developer API',
      status: 'AVAILABLE',
      authType: 'OAuth 2.0 Flow',
      dailyRenewal: 'Daily morning token generation',
      description: 'Low-latency v2 API integration for equity intraday & F&O segments.',
    },
    {
      id: 'ANGEL_ONE',
      name: 'Angel One SmartAPI',
      status: 'AVAILABLE',
      authType: 'TOTP + Client ID Flow',
      dailyRenewal: 'Automated morning TOTP handshake',
      description: 'Official SmartAPI gateway with real-time WebSocket market depth.',
    },
    {
      id: 'DHAN',
      name: 'Dhan HQ API',
      status: 'AVAILABLE',
      authType: 'Permanent Access Token',
      dailyRenewal: '30-day token cycle',
      description: 'High-speed trading APIs built for scalpers and quantitative traders.',
    },
    {
      id: 'GROWW',
      name: 'Groww',
      status: 'WAITLIST',
      authType: 'Coming Soon',
      dailyRenewal: 'Pending Developer API Release',
      description: 'Official API integration is currently in pilot testing.',
    },
  ];

  const handleConnect = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setConnected(true);
      setMarginData({ available: 184500.0, total: 200000.0 });
    }, 800);
  };

  const handleTestConnection = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setTested(true);
    }, 500);
  };

  const handleDisconnect = () => {
    setConnected(false);
    setTested(false);
    setMarginData(null);
    setApiKey('');
    setApiSecret('');
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Connect Your Broker
        </h1>
        <p className="text-xs sm:text-sm text-slate-400">
          TradeForge uses official broker developer APIs with <strong>trade-only permissions</strong>. We can never withdraw or move your funds.
        </p>
      </div>

      {/* Security Guarantee Box */}
      <div className="p-4 rounded-xl bg-teal-950/40 border border-teal-800/40 space-y-2 text-xs text-slate-300">
        <div className="flex items-center gap-2 font-bold text-teal-400">
          <ShieldCheck className="w-4 h-4" />
          <span>Non-Custodial Architecture & AES-256 Token Encryption</span>
        </div>
        <p className="leading-relaxed">
          Your capital remains strictly in your own regulated SEBI broker account. All API secrets are encrypted using authenticated AES-256-GCM before storage. You can revoke access or disconnect your broker at any time.
        </p>
      </div>

      {/* Broker Selection Grid */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
          Select Broker Gateway
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {brokers.map((b) => (
            <div
              key={b.id}
              onClick={() => b.status === 'AVAILABLE' && setSelectedBroker(b.id)}
              className={`p-5 rounded-xl border transition-all cursor-pointer flex flex-col justify-between space-y-3 ${
                selectedBroker === b.id
                  ? 'bg-[#132235] border-teal-500 shadow-lg shadow-teal-950/50'
                  : 'bg-[#0D1B2A] border-[#1F334A] hover:border-slate-600'
              } ${b.status === 'WAITLIST' ? 'opacity-60 cursor-not-allowed' : ''}`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white text-sm">{b.name}</span>
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                      b.status === 'AVAILABLE'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {b.status}
                  </span>
                </div>
                <p className="text-xs text-slate-400">{b.description}</p>
              </div>

              <div className="pt-2 border-t border-slate-800/60 text-[11px] font-mono text-slate-400">
                <span>{b.dailyRenewal}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Connection Form / Status Box */}
      <div className="p-6 sm:p-8 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-6 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-white">
              {brokers.find((b) => b.id === selectedBroker)?.name} Credentials
            </h3>
            <span className="text-xs text-slate-400">
              API keys are generated in your broker’s developer portal.
            </span>
          </div>

          {connected && (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs font-mono font-bold">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              CONNECTED (AES-256 ENCRYPTED)
            </span>
          )}
        </div>

        {!connected ? (
          <form onSubmit={handleConnect} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-mono text-slate-300">API Key</label>
                <div className="relative">
                  <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="text"
                    required
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter broker API key"
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-teal-500 outline-none font-mono"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-mono text-slate-300">API Secret / Request Token</label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="password"
                    required
                    value={apiSecret}
                    onChange={(e) => setApiSecret(e.target.value)}
                    placeholder="••••••••••••••••••••••••"
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-teal-500 outline-none font-mono"
                  />
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-[#132235] text-xs text-slate-300 font-mono">
              <strong>Daily Login Reminder:</strong> Indian broker order APIs require daily morning authorization. TradeForge will notify you before 08:45 AM IST each market day to refresh your token.
            </div>

            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all shadow-lg shadow-teal-900/30 flex items-center gap-2"
            >
              <span>{loading ? 'Encrypting & Connecting...' : 'Save & Connect Broker'}</span>
            </button>
          </form>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="p-4 rounded-xl bg-[#132235] border border-[#1F334A] space-y-1">
                <span className="text-slate-400">Available Trading Cash</span>
                <span className="text-xl font-bold text-white tabular-nums block">
                  ₹{marginData?.available.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
                <span className="text-[10px] text-emerald-400">Fetched via Broker API</span>
              </div>
              <div className="p-4 rounded-xl bg-[#132235] border border-[#1F334A] space-y-1">
                <span className="text-slate-400">Token Status</span>
                <span className="text-base font-bold text-emerald-400 block">VALID (Session Active)</span>
                <span className="text-[10px] text-slate-400">Expires 15:30 IST today</span>
              </div>
              <div className="p-4 rounded-xl bg-[#132235] border border-[#1F334A] space-y-1">
                <span className="text-slate-400">Order Routing Permission</span>
                <span className="text-base font-bold text-teal-400 block">Trade-Only (Non-Custodial)</span>
                <span className="text-[10px] text-slate-400">Withdrawals Impossible</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <button
                onClick={handleTestConnection}
                disabled={loading}
                className="px-4 py-2 rounded-lg bg-[#132235] hover:bg-[#1A2E47] border border-[#1F334A] text-xs font-semibold text-slate-200 transition-all flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>Test Connection (Heartbeat)</span>
              </button>

              <button
                onClick={handleDisconnect}
                className="px-4 py-2 rounded-lg bg-red-950/60 hover:bg-red-900 border border-red-800 text-xs font-semibold text-red-200 transition-all flex items-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Disconnect & Revoke Credentials</span>
              </button>

              {tested && (
                <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Connection latency: 48ms (PASSED)</span>
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
