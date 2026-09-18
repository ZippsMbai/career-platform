"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, clearToken } from "../lib/api";

type Resume = { id: string; label: string; raw_text: string };
type Job = { id: string; title?: string; company?: string; raw_text: string; pay_text?: string | null; last_seen_at?: string | null };
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

type LocationFilter = "anywhere" | "kenya" | "remote" | "emea" | "fulltime";

const CITIZENSHIP_PATTERNS = [
  "u.s. citizen", "us citizen", "united states citizen",
  "must be authorized to work in the united states without sponsorship",
  "citizens only", "citizenship required",
];

function requiresUSCitizenship(job: Job): boolean {
  const text = `${job.title || ""} ${job.raw_text}`.toLowerCase();
  return CITIZENSHIP_PATTERNS.some((p) => text.includes(p));
}

// Catches "Remote within Spain" / "Remote in Poland" style postings — these are
// geographically restricted, not genuinely open-to-anywhere, even though they
// contain the literal word "remote". Kenya is exempted since that IS the
// relevant restriction for this candidate.
function isFalselyRemote(text: string): boolean {
  const match = text.toLowerCase().match(/remote\s+(?:within|in|from)\s+([a-z\s]+?)(?:[.,;)\n]|$)/);
  if (!match) return false;
  return !match[1].includes("kenya");
}

const EMEA_HINTS = [
  "emea", "europe", "middle east", "africa", "eu ", " eu,", "european union",
  "uk", "united kingdom", "germany", "france", "netherlands", "uae", "dubai",
  "south africa", "egypt", "nigeria",
];

function jobCategory(job: Job): "kenya" | "remote" | "emea" | "fulltime" | "other" {
  const text = `${job.title || ""} ${job.raw_text}`.toLowerCase();
  if (text.includes("kenya") || text.includes("nairobi")) return "kenya";
  if (isFalselyRemote(text)) return "other";
  const remoteHints = ["remote", "worldwide", "work from anywhere", "distributed team", "anywhere in the world", "100% remote", "fully remote"];
  if (remoteHints.some((h) => text.includes(h))) return "remote";
  if (EMEA_HINTS.some((h) => text.includes(h))) return "emea";
  const fulltimeHints = ["full-time", "full time", "permanent"];
  if (fulltimeHints.some((h) => text.includes(h))) return "fulltime";
  return "other";
}

function matchesLocationFilter(job: Job, filter: LocationFilter): boolean {
  if (filter === "anywhere") return true;
  return jobCategory(job) === filter;
}

function daysSince(dateStr?: string | null): number | null {
  if (!dateStr) return null;
  const then = new Date(dateStr).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / (1000 * 60 * 60 * 24));
}

function StalenessBadge({ lastSeenAt }: { lastSeenAt?: string | null }) {
  const days = daysSince(lastSeenAt);
  if (days === null) return null;
  const label = days === 0 ? "Seen today" : days === 1 ? "Seen 1 day ago" : `Seen ${days} days ago`;
  const isStale = days > 14;
  return (
    <span
      className={`inline-block font-mono text-[9px] uppercase tracking-wide rounded px-1.5 py-0.5 ${
        isStale ? "bg-flag/20 text-flag" : "text-textmuted border border-paperdark"
      }`}
    >
      {label}
    </span>
  );
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

  async function refreshAll(isRetry = false) {
    try {
      const [r, j, a] = await Promise.all([api.listResumes(), api.listJobs(), api.listApplications()]);
      setResumes(r);
      setJobs(j);
      setApplications(a);
      setError("");
    } catch (e) {
      if (!isRetry) {
        setError("☕ Waking the server up — one sec...");
        setTimeout(() => refreshAll(true), 4000);
      } else {
        clearToken();
        router.push("/");
      }
    }
  }

  useEffect(() => {
    if (!selectedResumeId) {
      setBatchResults([]);
      return;
    }
    api.listAnalysesForResume(selectedResumeId)
      .then((saved: Analysis[]) => setBatchResults(saved.sort((a, b) => b.fit_score - a.fit_score)))
      .catch(() => {});
  }, [selectedResumeId]);

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
    let offset = 0;
    try {
      let remaining = 1;
      let safety = 0;
      while (remaining > 0) {
        safety += 1;
        if (safety > 50) {
          setError("Stopped after 50 batches as a safety limit — that's an unusually large number of jobs.");
          break;
        }
        const { results, remaining: r } = await api.batchAnalyze(selectedResumeId, offset, locationFilter);
        offset += results.length;
        accumulated.push(...results);
        remaining = r;
        setBatchResults([...accumulated].sort((a, b) => b.fit_score - a.fit_score));
        if (remaining > 0) {
          setBatchMessage(`Analyzed ${accumulated.length} so far, ${remaining} more to go...`);
        }
      }
      setBatchMessage(`Done — analyzed ${accumulated.length} job${accumulated.length === 1 ? "" : "s"}.`);
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
    <main className="min-h-screen px-6 py-10 max-w-7xl mx-auto">
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
          <div className="flex items-center gap-2 my-3">
            <div className="h-px bg-paperdark flex-1" />
            <span className="text-[10px] font-mono uppercase text-textmuted">or</span>
            <div className="h-px bg-paperdark flex-1" />
          </div>
          <label className="block text-sm font-mono">
            <span className="block mb-1 text-xs uppercase tracking-wide text-textmuted">Upload a file (.pdf, .docx, .txt)</span>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  await api.uploadResume(newResumeLabel, file);
                  refreshAll();
                } catch (err: any) {
                  setError("Resume upload failed: " + err.message);
                } finally {
                  e.target.value = "";
                }
              }}
              className="w-full text-sm"
            />
          </label>
        </section>

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
                  <div className="flex items-center gap-1.5 mt-1">
                    <PayBadge pay={j.pay_text} />
                    <StalenessBadge lastSeenAt={j.last_seen_at} />
                  </div>
                </div>
              ))}
              {jobs.length === 0 && <p className="text-xs text-textmuted font-mono col-span-2">No jobs yet.</p>}
            </div>
          )}
        </section>
      </div>

      <section className="bg-paper text-textdark rounded p-5 mb-8">
        <h2 className="font-mono text-xs uppercase tracking-widest text-textmuted mb-3">Find &amp; Analyze a Job</h2>

        <div className="flex flex-wrap gap-4 items-center mb-3">
          <select
            className="px-3 py-2 rounded border border-paperdark text-sm font-mono"
            value={selectedResumeId}
            onChange={(e) => setSelectedResumeId(e.target.value)}
          >
            <option value="">Select