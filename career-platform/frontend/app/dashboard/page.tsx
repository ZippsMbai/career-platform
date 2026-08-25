"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "../lib/api";

type Resume = { id: string; label: string; raw_text: string };
type Job = { id: string; title?: string; company?: string; raw_text: string };
type Analysis = {
  id: string;
  job_id: string;
  fit_score: number;
  summary: string;
  matched_signals: string[];
  gaps: string[];
  tailored_bullets: string[];
  cover_letter_opening: string;
};
type Application = {
  id: string;
  job_id: string;
  analysis_id: string | null;
  status: string;
  notes: string | null;
};

export default function Dashboard() {
  const router = useRouter();
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);

  const [newResumeLabel, setNewResumeLabel] = useState("default");
  const [newResumeText, setNewResumeText] = useState("");
  const [newJobText, setNewJobText] = useState("");
  const [newJobTitle, setNewJobTitle] = useState("");
  const [newJobCompany, setNewJobCompany] = useState("");

  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [selectedJobId, setSelectedJobId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");

  const [batchResults, setBatchResults] = useState<Analysis[]>([]);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");
  const [minScore, setMinScore] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    refreshAll();
  }, []);

  async function refreshAll() {
    try {
      const [r, j, a] = await Promise.all([api.listResumes(), api.listJobs(), api.listApplications()]);
      setResumes(r);
      setJobs(j);
      setApplications(a);
    } catch (e) {
      // token likely expired
      clearToken();
      router.push("/");
    }
  }

  async function addResume(e: React.FormEvent) {
    e.preventDefault();
    if (!newResumeText.trim()) return;
    await api.createResume(newResumeLabel, newResumeText);
    setNewResumeText("");
    refreshAll();
  }

  async function addJob(e: React.FormEvent) {
    e.preventDefault();
    if (!newJobText.trim()) return;
    await api.createJob(newJobText, newJobTitle || undefined, newJobCompany || undefined);
    setNewJobText("");
    setNewJobTitle("");
    setNewJobCompany("");
    refreshAll();
  }

  async function runAnalysis() {
    if (!selectedResumeId || !selectedJobId) {
      setError("Pick a resume and a job first.");
      return;
    }
    setError("");
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const result = await api.runAnalysis(selectedJobId, selectedResumeId);
      setAnalysis(result);
    } catch (e: any) {
      setError("Analysis failed: " + e.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function trackApplication(status: string) {
    if (!analysis || !selectedJobId) return;
    await api.createApplication(selectedJobId, analysis.id, status);
    refreshAll();
  }

  async function runBatchTriage() {
    if (!selectedResumeId) {
      setError("Pick a resume first.");
      return;
    }
    setError("");
    setBatchMessage("");
    setBatchRunning(true);
    try {
      const results: Analysis[] = await api.batchAnalyze(selectedResumeId);
      setBatchResults(results.sort((a, b) => b.fit_score - a.fit_score));
      if (results.length === 0) {
  setBatchMessage("No new jobs to analyze — every saved job already has an analysis for this resume. Add another job first, or pick a different resume.");
}
    } catch (e: any) {
      setError("Batch triage failed: " + e.message);
    } finally {
      setBatchRunning(false);
    }
  }

  async function trackFromBatch(a: Analysis, status: string) {
    await api.createApplication(a.job_id, a.id, status);
    refreshAll();
  }

  async function updateStatus(id: string, status: string) {
    await api.updateApplication(id, { status });
    refreshAll();
  }

  function jobLabel(job_id: string) {
    const j = jobs.find((j) => j.id === job_id);
    return j ? (j.title ? `${j.title}${j.company ? " — " + j.company : ""}` : j.raw_text.slice(0, 60) + "…") : job_id;
  }

  return (
    <main className="min-h-screen px-6 py-10 max-w-5xl mx-auto">
      <div className="flex justify-between items-start mb-8">
        <div>
          <div className="font-mono text-[11px] tracking-widest uppercase text-stamp border border-stamp inline-block px-2 py-1 rounded mb-3">
            Dashboard
          </div>
          <h1 className="text-3xl font-serif">Career Intelligence</h1>
        </div>
        <button
          onClick={() => { clearToken(); router.push("/"); }}
          className="font-mono text-xs uppercase tracking-wide text-[#cfc7b4] border border-[#4a4438] px-3 py-2 rounded hover:border-stamp hover:text-stamp"
        >
          Sign out
        </button>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        {/* Resumes */}
        <section className="bg-paper text-textdark rounded p-5">
          <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Resumes</h2>
          <ul className="mb-4 space-y-1">
            {resumes.map((r) => (
              <li key={r.id} className="text-sm font-serif">• {r.label}</li>
            ))}
            {resumes.length === 0 && <li className="text-sm text-textmuted font-mono">No resumes yet.</li>}
          </ul>
          <form onSubmit={addResume} className="space-y-2">
            <input
              className="w-full px-3 py-2 rounded border border-paperdark text-sm font-mono"
              placeholder="Label (e.g. security, dev)"
              value={newResumeLabel}
              onChange={(e) => setNewResumeLabel(e.target.value)}
            />
            <textarea
              className="w-full px-3 py-2 rounded border border-paperdark text-sm font-serif min-h-[100px]"
              placeholder="Paste resume text..."
              value={newResumeText}
              onChange={(e) => setNewResumeText(e.target.value)}
            />
            <button className="bg-stamp text-[#1a1206] font-mono text-xs uppercase tracking-widest px-4 py-2 rounded font-bold">
              Save resume
            </button>
          </form>
        </section>

        {/* Jobs */}
        <section className="bg-paper text-textdark rounded p-5">
          <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Jobs</h2>
          <ul className="mb-4 space-y-1">
            {jobs.map((j) => (
              <li key={j.id} className="text-sm font-serif">• {jobLabel(j.id)}</li>
            ))}
            {jobs.length === 0 && <li className="text-sm text-textmuted font-mono">No jobs yet.</li>}
          </ul>
          <form onSubmit={addJob} className="space-y-2">
            <div className="flex gap-2">
              <input
                className="w-1/2 px-3 py-2 rounded border border-paperdark text-sm font-mono"
                placeholder="Title (optional)"
                value={newJobTitle}
                onChange={(e) => setNewJobTitle(e.target.value)}
              />
              <input
                className="w-1/2 px-3 py-2 rounded border border-paperdark text-sm font-mono"
                placeholder="Company (optional)"
                value={newJobCompany}
                onChange={(e) => setNewJobCompany(e.target.value)}
              />
            </div>
            <textarea
              className="w-full px-3 py-2 rounded border border-paperdark text-sm font-serif min-h-[100px]"
              placeholder="Paste job posting text..."
              value={newJobText}
              onChange={(e) => setNewJobText(e.target.value)}
            />
            <button className="bg-stamp text-[#1a1206] font-mono text-xs uppercase tracking-widest px-4 py-2 rounded font-bold">
              Save job
            </button>
          </form>
        </section>
      </div>

      {/* Run analysis */}
      <section className="bg-paper text-textdark rounded p-5 mb-8">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Run Analysis</h2>
        <div className="flex flex-wrap gap-3 items-center mb-3">
          <select
            className="px-3 py-2 rounded border border-paperdark text-sm font-mono"
            value={selectedResumeId}
            onChange={(e) => setSelectedResumeId(e.target.value)}
          >
            <option value="">Select resume…</option>
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>{r.label}</option>
            ))}
          </select>
          <select
            className="px-3 py-2 rounded border border-paperdark text-sm font-mono"
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
          >
            <option value="">Select job…</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>{jobLabel(j.id)}</option>
            ))}
          </select>
          <button
            onClick={runAnalysis}
            disabled={analyzing}
            className="bg-stamp text-[#1a1206] font-mono text-xs uppercase tracking-widest px-4 py-2 rounded font-bold disabled:opacity-50"
          >
            {analyzing ? "Analyzing…" : "Run Analysis"}
          </button>
        </div>
        {error && <p className="text-flag text-sm font-mono mb-2">{error}</p>}

        {analysis && (
          <div className="border-t border-paperdark pt-4 mt-2">
            <div className="flex justify-between items-start mb-4">
              <p className="text-sm font-serif max-w-xl">{analysis.summary}</p>
              <div className="font-mono border-2 border-stamp text-stamp rounded px-3 py-2 text-lg font-bold -rotate-3 whitespace-nowrap">
                {analysis.fit_score}% MATCH
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4 mb-4">
              <div>
                <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted mb-1">Matched Signals</h3>
                <ul className="text-sm space-y-1">
                  {analysis.matched_signals?.map((s, i) => <li key={i} className="text-teal">✓ {s}</li>)}
                </ul>
              </div>
              <div>
                <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted mb-1">Gaps Flagged</h3>
                <ul className="text-sm space-y-1">
                  {analysis.gaps?.map((g, i) => <li key={i} className="text-flag">⚑ {g}</li>)}
                </ul>
              </div>
            </div>
            <div className="mb-4">
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted mb-1">Tailored Bullets</h3>
              <ul className="text-sm list-decimal list-inside space-y-1">
                {analysis.tailored_bullets?.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            </div>
            <div className="mb-4">
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted mb-1">Cover Letter Opening</h3>
              <p className="text-sm italic border-l-2 border-stamp pl-3">{analysis.cover_letter_opening}</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => trackApplication("saved")} className="font-mono text-xs uppercase tracking-widest px-3 py-2 rounded border border-textdark">
                Save for later
              </button>
              <button onClick={() => trackApplication("applied")} className="bg-teal text-white font-mono text-xs uppercase tracking-widest px-3 py-2 rounded">
                Mark as applied
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Batch triage */}
      <section className="bg-paper text-textdark rounded p-5 mb-8">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Triage — Analyze All New Jobs</h2>
        <p className="text-sm font-serif text-textmuted mb-3">
          Score every job that doesn't have an analysis yet against the selected resume above, then sort by fit
          instead of opening postings one at a time. Run this after syncing new jobs in.
        </p>
        <div className="flex flex-wrap gap-3 items-center mb-3">
          <button
            onClick={runBatchTriage}
            disabled={batchRunning}
            className="bg-stamp text-[#1a1206] font-mono text-xs uppercase tracking-widest px-4 py-2 rounded font-bold disabled:opacity-50"
          >
            {batchRunning ? "Analyzing all…" : "Analyze All New Jobs"}
          </button>
          {batchResults.length > 0 && (
            <label className="text-xs font-mono uppercase tracking-wide text-textmuted flex items-center gap-2">
              Min fit score: {minScore}%
              <input type="range" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} />
            </label>
          )}
        </div>

        {batchResults.length > 0 && (
          <div className="space-y-2">
            {batchResults.filter((a) => a.fit_score >= minScore).map((a) => (
              <div key={a.id} className="border-b border-paperdark pb-2">
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <div className="text-sm font-serif font-bold">{jobLabel(a.job_id)}</div>
                    <div className="text-xs font-serif text-textmuted">{a.summary}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono text-xs font-bold border border-stamp text-stamp rounded px-2 py-1">{a.fit_score}%</span>
                    <button onClick={() => trackFromBatch(a, "saved")} className="font-mono text-[10px] uppercase px-2 py-1 rounded border border-textdark">Save</button>
                    <button onClick={() => trackFromBatch(a, "applied")} className="bg-teal text-white font-mono text-[10px] uppercase px-2 py-1 rounded">Applied</button>
                  </div>
                </div>
              </div>
            ))}
            {batchResults.filter((a) => a.fit_score >= minScore).length === 0 && (
              <p className="text-sm text-textmuted font-mono">No jobs meet that threshold — lower it or sync more postings.</p>
            )}
          </div>
          {batchMessage && <p className="text-sm font-mono text-textmuted mb-3">{batchMessage}</p>}
        )}
      </section>

      {/* Applications */}
      <section className="bg-paper text-textdark rounded p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Applications</h2>
        {applications.length === 0 && <p className="text-sm text-textmuted font-mono">Nothing tracked yet.</p>}
        <div className="space-y-2">
          {applications.map((a) => (
            <div key={a.id} className="flex justify-between items-center border-b border-paperdark pb-2">
              <span className="text-sm font-serif">{jobLabel(a.job_id)}</span>
              <select
                className="text-xs font-mono uppercase px-2 py-1 rounded border border-paperdark"
                value={a.status}
                onChange={(e) => updateStatus(a.id, e.target.value)}
              >
                {["saved", "applied", "interviewing", "rejected", "offer"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
