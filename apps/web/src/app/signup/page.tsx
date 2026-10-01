'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ShieldCheck, Mail, Lock, CheckSquare, Square, ArrowRight, QrCode } from 'lucide-react';

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [consentRisk, setConsentRisk] = useState(false);
  const [consentTerms, setConsentTerms] = useState(false);
  const [consentData, setConsentData] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [totpSecret, setTotpSecret] = useState('JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP');
  const [loading, setLoading] = useState(false);

  const handleSignup = (e: React.FormEvent) => {
    e.preventDefault();
    if (!consentRisk || !consentTerms || !consentData) {
      alert('You must accept all regulatory risk disclosures to proceed.');
      return;
    }
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setRegistered(true);
    }, 700);
  };

  const handleFinish = () => {
    router.push('/dashboard');
  };

  return (
    <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex p-3 rounded-xl bg-teal-950/60 border border-teal-800 text-teal-400 mb-2">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Create TradeForge Account
          </h1>
          <p className="text-xs text-slate-400">
            Compliant with SEBI intraday trading guidelines & India DPDP Act.
          </p>
        </div>

        <div className="p-6 sm:p-8 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-6 shadow-2xl">
          {!registered ? (
            <form onSubmit={handleSignup} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-mono text-slate-300">Email Address</label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:border-teal-500 outline-none"
                    placeholder="trader@tradeforge.io"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-mono text-slate-300">Password</label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="password"
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:border-teal-500 outline-none font-mono"
                    placeholder="Min. 8 characters"
                  />
                </div>
              </div>

              {/* Regulatory Consent Checkboxes */}
              <div className="pt-2 border-t border-slate-800 space-y-3 text-xs text-slate-300">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentRisk}
                    onChange={(e) => setConsentRisk(e.target.checked)}
                    className="mt-0.5 accent-teal-500 rounded"
                    required
                  />
                  <span>
                    <strong>SEBI Intraday Risk Acknowledgment:</strong> I acknowledge that 9 out of 10 individual traders in Indian equity and derivative markets lose money. TradeForge does not guarantee profits.
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentTerms}
                    onChange={(e) => setConsentTerms(e.target.checked)}
                    className="mt-0.5 accent-teal-500 rounded"
                    required
                  />
                  <span>
                    <strong>Terms of Platform & Execution:</strong> I agree that TradeForge is a non-custodial software execution tool and does not manage my portfolio.
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentData}
                    onChange={(e) => setConsentData(e.target.checked)}
                    className="mt-0.5 accent-teal-500 rounded"
                    required
                  />
                  <span>
                    <strong>DPDP Consent:</strong> I authorize minimal encrypted storage of my trading preferences in compliance with the Digital Personal Data Protection Act.
                  </span>
                </label>
              </div>

              <button
                type="submit"
                disabled={loading || !consentRisk || !consentTerms || !consentData}
                className="w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-teal-900/30 disabled:opacity-50"
              >
                <span>{loading ? 'Creating Account...' : 'Continue to Mandatory 2FA Setup'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          ) : (
            <div className="space-y-6 text-center">
              <div className="p-4 rounded-xl bg-[#132235] border border-teal-500/40 space-y-3">
                <h3 className="text-sm font-bold text-white flex items-center justify-center gap-2">
                  <QrCode className="w-5 h-5 text-teal-400" />
                  <span>Setup 2-Factor Authentication (TOTP)</span>
                </h3>
                <p className="text-xs text-slate-300">
                  Scan this code or enter the Base32 key in Google Authenticator or 1Password. 2FA is required before any order can be authorized.
                </p>

                {/* Simulated QR Code Box */}
                <div className="w-36 h-36 mx-auto bg-white p-2 rounded-lg flex items-center justify-center shadow-lg">
                  <div className="w-full h-full bg-slate-900 rounded p-2 flex flex-col justify-between text-[8px] font-mono text-teal-400 select-none">
                    <div className="flex justify-between"><span>[QR-A]</span><span>[QR-B]</span></div>
                    <div className="text-center font-bold text-white text-[10px]">TRADEFORGE</div>
                    <div className="flex justify-between"><span>[TOTP]</span><span>[2026]</span></div>
                  </div>
                </div>

                <div className="space-y-1">
                  <span className="text-[11px] text-slate-400 font-mono">Manual Secret Key:</span>
                  <div className="p-2 rounded bg-[#070D14] border border-[#1F334A] font-mono text-xs text-teal-300 select-all">
                    {totpSecret}
                  </div>
                </div>
              </div>

              <button
                onClick={handleFinish}
                className="w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all shadow-lg shadow-teal-900/30"
              >
                Launch Dashboard in Paper Mode
              </button>
            </div>
          )}

          <div className="text-center text-xs text-slate-400 border-t border-slate-800 pt-4">
            Already have an account?{' '}
            <Link href="/login" className="text-teal-400 font-semibold hover:underline">
              Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
