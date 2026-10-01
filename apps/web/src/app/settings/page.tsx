'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  Bell,
  Trash2,
  Download,
  Lock,
  Smartphone,
  CheckCircle2,
  Mail,
} from 'lucide-react';

export default function SettingsPage() {
  const [telegramAlerts, setTelegramAlerts] = useState(true);
  const [smsAlerts, setSmsAlerts] = useState(false);
  const [lossAlerts, setLossAlerts] = useState(true);
  const [morningReminder, setMorningReminder] = useState(true);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleDownloadData = () => {
    alert('Preparing your encrypted data package under the Digital Personal Data Protection Act (DPDP)... Download will begin shortly.');
  };

  const handleDeleteData = () => {
    if (confirm('Are you sure you want to permanently delete your TradeForge profile and revoke all broker tokens? This cannot be undone.')) {
      alert('All broker tokens and user records queued for permanent deletion.');
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8">
      <div className="space-y-2">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Account & Security Settings
        </h1>
        <p className="text-xs sm:text-sm text-slate-400">
          Manage 2FA, daily morning token alerts, notification webhooks, and DPDP data rights.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Security & 2FA Status */}
        <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Lock className="w-4 h-4 text-teal-400" />
            <span>Two-Factor Authentication (2FA)</span>
          </h3>
          <div className="flex items-center justify-between p-4 rounded-xl bg-[#132235] border border-emerald-900/40">
            <div className="space-y-1">
              <span className="text-sm font-semibold text-white">Authenticator App (TOTP)</span>
              <p className="text-xs text-slate-400">
                Mandatory for session sign-in and autonomous mode order dispatch.
              </p>
            </div>
            <span className="text-xs font-mono text-emerald-400 font-bold px-3 py-1 rounded bg-emerald-950 border border-emerald-800">
              ACTIVE & ENFORCED
            </span>
          </div>
        </div>

        {/* Real-time Alerts & Notifications */}
        <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Bell className="w-4 h-4 text-teal-400" />
            <span>Operational Notifications & Morning Reminders</span>
          </h3>

          <div className="space-y-3 text-xs text-slate-300">
            <label className="flex items-center justify-between p-3 rounded-lg bg-[#132235] cursor-pointer">
              <div>
                <strong className="block text-white">08:45 AM IST Daily Token Refresh Reminder</strong>
                <span className="text-slate-400">Alert to log into your Indian broker before market open.</span>
              </div>
              <input
                type="checkbox"
                checked={morningReminder}
                onChange={(e) => setMorningReminder(e.target.checked)}
                className="accent-teal-500 w-4 h-4"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-lg bg-[#132235] cursor-pointer">
              <div>
                <strong className="block text-white">Telegram Instant Trade Alerts</strong>
                <span className="text-slate-400">Receive order fills, stop hits, and plain-English AI decision reasons.</span>
              </div>
              <input
                type="checkbox"
                checked={telegramAlerts}
                onChange={(e) => setTelegramAlerts(e.target.checked)}
                className="accent-teal-500 w-4 h-4"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-lg bg-[#132235] cursor-pointer">
              <div>
                <strong className="block text-white">Risk Guard Daily Loss Warnings</strong>
                <span className="text-slate-400">Immediate push alert if daily loss approaches 75% of your ceiling.</span>
              </div>
              <input
                type="checkbox"
                checked={lossAlerts}
                onChange={(e) => setLossAlerts(e.target.checked)}
                className="accent-teal-500 w-4 h-4"
              />
            </label>
          </div>

          <button
            type="submit"
            className="px-5 py-2 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-semibold text-xs transition-all shadow-md shadow-teal-900/30"
          >
            {saved ? 'Preferences Saved!' : 'Save Notification Preferences'}
          </button>
        </div>

        {/* DPDP Compliance & Data Privacy */}
        <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-4 shadow-xl">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Digital Personal Data Protection Act (DPDP)</span>
          </h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            In compliance with Indian data privacy statutes, you have complete ownership of your trading records and credentials.
          </p>

          <div className="flex flex-wrap items-center gap-4 pt-2">
            <button
              type="button"
              onClick={handleDownloadData}
              className="px-4 py-2 rounded-lg bg-[#132235] hover:bg-[#1A2E47] border border-[#1F334A] text-xs font-semibold text-slate-200 transition-all flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5 text-teal-400" />
              <span>Download My Full Data Archive</span>
            </button>

            <button
              type="button"
              onClick={handleDeleteData}
              className="px-4 py-2 rounded-lg bg-red-950/60 hover:bg-red-900 border border-red-800 text-xs font-semibold text-red-200 transition-all flex items-center gap-1.5"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Revoke All Broker Tokens & Delete Account</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
