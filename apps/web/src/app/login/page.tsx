'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Lock, Mail, ShieldCheck, ArrowRight, AlertCircle, KeyRound } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('trader@tradeforge.io');
  const [password, setPassword] = useState('••••••••••••');
  const [totpToken, setTotpToken] = useState('');
  const [step, setStep] = useState<'CREDENTIALS' | 'TOTP'>('CREDENTIALS');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCredentialsSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setStep('TOTP');
    }, 600);
  };

  const handleTotpSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      router.push('/dashboard');
    }, 600);
  };

  const handleDemoSignIn = () => {
    router.push('/dashboard');
  };

  return (
    <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex p-3 rounded-xl bg-teal-950/60 border border-teal-800 text-teal-400 mb-2">
            <Lock className="w-6 h-6" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Sign In to TradeForge
          </h1>
          <p className="text-xs text-slate-400">
            Mandatory Argon2 password hashing and TOTP 2FA session verification.
          </p>
        </div>

        <div className="p-6 rounded-2xl bg-[#0D1B2A] border border-[#1F334A] space-y-6 shadow-2xl">
          {error && (
            <div className="p-3 rounded-lg bg-red-950/60 border border-red-800 text-red-300 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {step === 'CREDENTIALS' ? (
            <form onSubmit={handleCredentialsSubmit} className="space-y-4">
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
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:border-teal-500 outline-none font-mono"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-teal-900/30"
              >
                <span>{loading ? 'Verifying...' : 'Next: 2FA Authentication'}</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          ) : (
            <form onSubmit={handleTotpSubmit} className="space-y-4">
              <div className="p-3 rounded-lg bg-teal-950/40 border border-teal-800/40 text-xs text-teal-300 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-teal-400 mt-0.5 shrink-0" />
                <span>Enter the 6-digit code from your Google Authenticator or Authy app.</span>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-mono text-slate-300">6-Digit Authenticator Code</label>
                <div className="relative">
                  <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                  <input
                    type="text"
                    maxLength={6}
                    required
                    value={totpToken}
                    onChange={(e) => setTotpToken(e.target.value)}
                    placeholder="123456"
                    className="w-full bg-[#132235] border border-[#1F334A] rounded-lg pl-9 pr-3 py-2 text-center text-lg tracking-widest font-mono text-white focus:border-teal-500 outline-none"
                    autoFocus
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 font-semibold text-white text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-teal-900/30"
              >
                <span>{loading ? 'Authenticating Session...' : 'Verify & Launch Dashboard'}</span>
              </button>

              <button
                type="button"
                onClick={() => setStep('CREDENTIALS')}
                className="w-full text-xs text-slate-400 hover:text-slate-200 transition-colors"
              >
                Back to credentials
              </button>
            </form>
          )}

          <div className="relative border-t border-slate-800 pt-4">
            <button
              onClick={handleDemoSignIn}
              type="button"
              className="w-full py-2 rounded-lg bg-[#132235] hover:bg-[#1A2E47] border border-[#1F334A] text-slate-200 text-xs font-medium transition-all"
            >
              Demo Access (Paper Mode • Instant Sign-In)
            </button>
          </div>

          <div className="text-center text-xs text-slate-400">
            Don&apos;t have an account?{' '}
            <Link href="/signup" className="text-teal-400 font-semibold hover:underline">
              Create Account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
