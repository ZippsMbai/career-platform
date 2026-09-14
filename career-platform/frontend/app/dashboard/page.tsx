"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "../lib/api";

type Resume = { id: string; label: string; raw_text: string };
type Job = { id: string; title?: string; company?: string; raw_text: string; pay_text?: string | null };
type Analysis = {
  id: string;
  job_id: string;
  fit_score: number;
  summary: string;
  matched_signals: string[];
  gaps: string[];
  tailored_bullets: string[];
  cover_letter_opening: string;
  cover_letter_full?: string;
  tailored_resume?: string;
};
type Application = {
  id: string;
  job_id: string;
  analysis_id: string | null;
  status: string;
  notes: string | null;
};

type LocationFilter = "anywhere" | "kenya" | "remote" | "fulltime";

const CITIZENSHIP_PATTERNS = [
  "u.s. citizen", "us citizen", "united states citizen",
  "must be authorized to work in the united states without sponsorship",
  "citizens only", "citizenship required",
];

function requiresUSCitizenship(job: Job): boolean {
  const text = `${job.title || ""} ${job.raw_text}`.toLowerCase();
  return CITIZENSHIP_PATTERNS.some((p) => text.includes(p));
}

// Client-side heuristic purely for the filter UI — mirrors the spirit of
// job_watch.py's remote-eligibility check, but simpler since this only controls
// what's shown, not what's allowed into the system.
function jobCategory(job: Job): "kenya" | "remote" | "fulltime" | "other" {
  const text = `${job.title || ""} ${job.raw_text}`.toLowerCase();
  if (text.includes("kenya") || text.includes("nairobi")) return "kenya";
  const remoteHints = ["remote", "worldwide", "work from anywhere", "distributed team", "anywhere in the world", "100% remote", "fully remote"];
  if (remoteHints.some((h) => text.includes(h))) return "remote";
  const fulltimeHints = ["full-time", "full time", "permanent"];
  if (fulltimeHints.some((h) => text.includes(h))) return "fulltime";
  return "other";
}

function matchesLocationFilter(job: Job, filter: LocationFilter): boolean {
  if (filter === "anywhere") return true;
  return jobCategory(job) === filter;
}

function PayBadge({ pay }: { pay?: string | null }) {
  if (!pay) return null;
  return (
    <span className="inline-block font-mono text-[10px] uppercase tracking-wide bg-teal text-white rounded px-1.5 py-0.5">
      {pay}
    </span>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="font-mono text-[10px] uppercase tracking-wide px-2 py-1 rounded border border-textdark hover:bg-textdark hover:text-paper transition-colors"
    >
      {copied ? "Copied!" : label}
    </button>
  );
}

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
  const [showAllJobs, setShowAllJobs] = useState(false);

  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [selectedJobId, setSelectedJobId] = useState("");
  const [jobSearch, setJobSearch] = useState("");
  const [locationFilter, setLocationFilter] = useState<LocationFilter>("anywhere");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [showFullLetter, setShowFullLetter] = useState(false);
  const [showTailoredResume, setShowTailoredResume] = useState(false);

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

  const filteredJobs = useMemo(() => {
    const q = jobSearch.trim().toLowerCase();
    return jobs.filter((j) => {
        if (requiresUSCitizenship(j)) return false;
      if (!matchesLocationFilter(j, locationFilter)) return false;
      if (!q) return true;
      return (j.title || "").toLowerCase().includes(q) || (j.company || "").toLowerCase().includes(q) || j.raw_text.toLowerCase().includes(q);
    });
  }, [jobs, jobSearch, locationFilter]);

  async function runAnalysis() {
    if (!selectedResumeId || !selectedJobId) {
      setError("Pick a resume and a job first.");
      return;
    }
    setError("");
    setAnalyzing(true);
    setAnalysis(null);
    setShowFullLetter(false);
    setShowTailoredResume(false);
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
    const accumulated: Analysis[] = [];
    try {
      let remaining = 1;
      let safety = 0;
      while (remaining > 0) {
        safety += 1;
        if (safety > 50) {
          setError("Stopped after 50 batches as a safety limit — that's an unusually large number of pending jobs.");
          break;
        }
        const { results, remaining: r } = await api.batchAnalyze(selectedResumeId);
        accumulated.push(...results);
        remaining = r;
        setBatchResults([...accumulated].sort((a, b) => b.fit_score - a.fit_score));
        if (remaining > 0) {
          setBatchMessage(`Analyzed ${accumulated.length} so far, ${remaining} more to go...`);
        }
      }
      if (accumulated.length === 0) {
        setBatchMessage(
          "No new jobs to analyze — every saved job already has an analysis for this resume. Add another job first, or pick a different resume."
        );
      } else {
        setBatchMessage(`Done — analyzed ${accumulated.length} job${accumulated.length === 1 ? "" : "s"}.`);
      }
    } catch (e: any) {
      setError("Batch triage failed: " + e.message + (accumulated.length > 0 ? ` (${accumulated.length} jobs were analyzed before this happened — results below are still saved.)` : ""));
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

  async function deleteApplicationRow(id: string) {
    if (!confirm("Remove this application from tracking? This can't be undone.")) return;
    await api.deleteApplication(id);
    refreshAll();
  }

  async function deleteJobRow(id: string) {
    if (!confirm("Delete this job? This also removes any analyses and tracked applications for it. Can't be undone.")) return;
    await api.deleteJob(id);
    refreshAll();
  }

  function getJob(job_id: string) {
    return jobs.find((j) => j.id === job_id);
  }

  function jobLabel(job_id: string) {
    const j = getJob(job_id);
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
          <p className="text-xs font-mono text-textmuted mb-2">
            {resumes.length} saved — analysis pulls relevant experience from all of them, not just the one selected below.
          </p>
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

        {/* Add a job — intake only, browsing/picking happens below */}
        <section className="bg-paper text-textdark rounded p-5">
          <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Add a Job</h2>
          <p className="text-xs font-mono text-textmuted mb-2">
            {jobs.length} saved — pick one to analyze in the section below.
          </p>
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
          <button
            onClick={() => setShowAllJobs((v) => !v)}
            className="mt-3 font-mono text-[10px] uppercase tracking-wide text-textmuted underline"
          >
            {showAllJobs ? "Hide" : "Show"} all saved jobs (manage / delete)
          </button>
          {showAllJobs && (
            <div className="grid sm:grid-cols-2 gap-2 mt-3 max-h-56 overflow-y-auto pr-1">
              {jobs.map((j) => (
                <div key={j.id} className="relative border border-paperdark rounded p-2 pr-6 bg-white/40">
                  <button
                    onClick={() => deleteJobRow(j.id)}
                    title="Delete job"
                    className="absolute top-1.5 right-1.5 text-flag font-mono text-xs w-5 h-5 flex items-center justify-center rounded hover:bg-flag hover:text-white transition-colors"
                  >
                    ✕
                  </button>
                  <div className="text-xs font-serif font-bold text-teal leading-snug">
                    {j.title || j.raw_text.slice(0, 50) + "…"}
                  </div>
                  {j.company && <div className="text-[11px] font-mono text-textdark">{j.company}</div>}
                  <PayBadge pay={j.pay_text} />
                </div>
              ))}
              {jobs.length === 0 && <p className="text-xs text-textmuted font-mono col-span-2">No jobs yet.</p>}
            </div>
          )}
        </section>
      </div>

      {/* Find & analyze — the new searchable/filterable picker, replacing the plain dropdown */}
      <section className="bg-paper text-textdark rounded p-5 mb-8">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Find &amp; Analyze a Job</h2>

        <div className="flex flex-wrap gap-4 items-center mb-3">
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

          <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-wide">
            {([
              ["anywhere", "Anywhere"],
              ["kenya", "Kenya"],
              ["remote", "Remote"],
              ["fulltime", "Full-time"],
            ] as [LocationFilter, string][]).map(([value, label]) => (
              <label key={value} className="flex items-center gap-1 cursor-pointer">
                <input
                  type="radio"
                  name="locationFilter"
                  checked={locationFilter === value}
                  onChange={() => setLocationFilter(value)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>

        <input
          className="w-full px-3 py-2 rounded border border-paperdark text-sm font-mono mb-2"
          placeholder="Search jobs by title, company, or keyword…"
          value={jobSearch}
          onChange={(e) => setJobSearch(e.target.value)}
        />

        <div className="max-h-52 overflow-y-auto border border-paperdark rounded mb-3">
          {filteredJobs.length === 0 && (
            <p className="text-sm text-textmuted font-mono p-3">No jobs match this filter/search.</p>
          )}
          {filteredJobs.map((j) => (
            <button
              key={j.id}
              onClick={() => setSelectedJobId(j.id)}
              className={`w-full text-left px-3 py-2 border-b border-paperdark last:border-b-0 flex items-center justify-between gap-2 hover:bg-white/60 transition-colors ${
                selectedJobId === j.id ? "bg-stamp/20" : ""
              }`}
            >
              <span className="text-sm font-serif">
                {j.title || j.raw_text.slice(0, 60) + "…"}
                {j.company && <span className="text-textmuted"> — {j.company}</span>}
              </span>
              <span className="flex items-center gap-1.5 shrink-0">
                <span className="font-mono text-[9px] uppercase text-textmuted border border-paperdark rounded px-1">
                  {jobCategory(j)}
                </span>
                <PayBadge pay={j.pay_text} />
              </span>
            </button>
          ))}
        </div>

        <button
          onClick={runAnalysis}
          disabled={analyzing}
          className="bg-stamp text-[#1a1206] font-mono text-xs uppercase tracking-widest px-4 py-2 rounded font-bold disabled:opacity-50"
        >
          {analyzing ? "Analyzing…" : "Run Analysis"}
        </button>
        {error && <p className="text-flag text-sm font-mono mt-2">{error}</p>}

        {analysis && (
          <div className="border-t border-paperdark pt-4 mt-4">
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

            {/* Cover letter — the dedicated spot for it, short preview + full generated letter */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted">Cover Letter</h3>
                {analysis.cover_letter_full && (
                  <div className="flex gap-2">
                    <CopyButton text={analysis.cover_letter_full} label="Copy full letter" />
                    <button
                      onClick={() => setShowFullLetter((v) => !v)}
                      className="font-mono text-[10px] uppercase tracking-wide px-2 py-1 rounded border border-teal text-teal hover:bg-teal hover:text-white transition-colors"
                    >
                      {showFullLetter ? "Hide full letter" : "Show full letter"}
                    </button>
                  </div>
                )}
              </div>
              <p className="text-sm italic border-l-2 border-stamp pl-3">{analysis.cover_letter_opening}</p>
              {showFullLetter && analysis.cover_letter_full && (
                <pre className="text-sm font-serif whitespace-pre-wrap bg-white/50 border border-paperdark rounded p-3 mt-2">
                  {analysis.cover_letter_full}
                </pre>
              )}
            </div>

            {/* Tailored resume — new resume draft combining all saved resumes, fitted to this posting */}
            {analysis.tailored_resume && (
              <div className="mb-4">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-mono text-[10px] uppercase tracking-widest text-textmuted">Tailored Resume Draft</h3>
                  <div className="flex gap-2">
                    <CopyButton text={analysis.tailored_resume} label="Copy resume" />
                    <button
                      onClick={() => setShowTailoredResume((v) => !v)}
                      className="font-mono text-[10px] uppercase tracking-wide px-2 py-1 rounded border border-teal text-teal hover:bg-teal hover:text-white transition-colors"
                    >
                      {showTailoredResume ? "Hide" : "Show"} draft
                    </button>
                  </div>
                </div>
                {showTailoredResume && (
                  <pre className="text-sm font-serif whitespace-pre-wrap bg-white/50 border border-paperdark rounded p-3 mt-2">
                    {analysis.tailored_resume}
                  </pre>
                )}
              </div>
            )}

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
            disabled={batchRunning || !selectedResumeId}
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
        {!selectedResumeId && (
          <p className="text-xs font-mono text-textmuted mb-2">Select a resume in the section above first.</p>
        )}
        {error && <p className="text-flag text-sm font-mono mb-2">{error}</p>}
        {batchMessage && <p className="text-sm font-mono text-textmuted mb-3">{batchMessage}</p>}
        {batchResults.length > 0 && (
          <div className="space-y-2">
            {batchResults.filter((a) => a.fit_score >= minScore).map((a) => (
              <div key={a.id} className="border-b border-paperdark pb-2">
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <div className="text-sm font-serif font-bold flex items-center gap-2">
                      {jobLabel(a.job_id)}
                      <PayBadge pay={getJob(a.job_id)?.pay_text} />
                    </div>
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
        )}
      </section>

      {/* Applications */}
      <section className="bg-paper text-textdark rounded p-5">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Applications</h2>
        {applications.length === 0 && <p className="text-sm text-textmuted font-mono">Nothing tracked yet.</p>}
        <div className="space-y-2">
          {applications.map((a) => (
            <div key={a.id} className="flex justify-between items-center border-b border-paperdark pb-2 gap-2">
              <span className="text-sm font-serif truncate flex items-center gap-2">
                {jobLabel(a.job_id)}
                <PayBadge pay={getJob(a.job_id)?.pay_text} />
              </span>
              <div className="flex items-center gap-2 shrink-0">
                <select
                  className="text-xs font-mono uppercase px-2 py-1 rounded border border-paperdark"
                  value={a.status}
                  onChange={(e) => updateStatus(a.id, e.target.value)}
                >
                  {["saved", "applied", "interviewing", "rejected", "offer"].map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <button
                  onClick={() => deleteApplicationRow(a.id)}
                  title="Remove from tracking"
                  className="text-flag font-mono text-xs px-2 py-1 rounded border border-flag hover:bg-flag hover:text-white transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
 
}
