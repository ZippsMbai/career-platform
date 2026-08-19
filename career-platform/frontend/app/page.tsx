"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "./lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.login(email, password);
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError("Login failed. Check your email/password against the .env you set on the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="bg-paper text-textdark rounded p-8 w-full max-w-sm shadow-2xl">
        <div className="font-mono text-[11px] tracking-widest uppercase text-stamp border border-stamp inline-block px-2 py-1 rounded mb-4">
          Career Intelligence
        </div>
        <h1 className="text-2xl font-serif mb-6">Sign in</h1>
        <label className="block text-xs font-mono uppercase tracking-wide text-textmuted mb-1">Email</label>
        <input
          className="w-full mb-4 px-3 py-2 rounded border border-paperdark bg-white/60 font-serif text-sm"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label className="block text-xs font-mono uppercase tracking-wide text-textmuted mb-1">Password</label>
        <input
          className="w-full mb-6 px-3 py-2 rounded border border-paperdark bg-white/60 font-serif text-sm"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="text-flag text-sm mb-4 font-mono">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-stamp text-[#1a1206] font-mono text-xs tracking-widest uppercase py-3 rounded font-bold disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
