import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Health = { status: string; service: string; version: string };
type Repository = { repository_id: string; name: string; latest_published_revision_id?: string };
type Lesson = { lesson_id: string; repository_id: string; title: string; chapters: { chapter_id: string; title: string; scene_ids: string[] }[]; scenes: Scene[]; steps: Step[] };
type Scene = { scene_id: string; title: string; kind: string; narration: string; source_refs: string[]; duration_ms: number };
type Step = { step_id: string; objective: string; status: string; completion_criteria: { question_score_min: number; minimum_evidence_refs: number } };
type Progress = { steps: Step[]; learner_state: Record<string, number>; policy_decision: { action_id: string } };

const API = "http://127.0.0.1:8000";

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [path, setPath] = useState("fixtures/sample_project");
  const [repositoryId, setRepositoryId] = useState("");
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [enrollmentId, setEnrollmentId] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mediaStatus, setMediaStatus] = useState<string | null>(null);

  const currentScene = useMemo(() => lesson?.scenes[sceneIndex] ?? null, [lesson, sceneIndex]);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((res) => res.json())
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
    fetch(`${API}/api/repositories`).then((res) => res.json()).then(setRepositories).catch(() => undefined);
  }, []);

  async function analyse() {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API}/api/repositories/analyse`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.message ?? "Analysis failed");
      setRepositoryId(data.repository_id);
      setRepositories((items) => [{ repository_id: data.repository_id, name: path, latest_published_revision_id: data.revision_id }, ...items.filter((item) => item.repository_id !== data.repository_id)]);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  async function createLesson() {
    if (!repositoryId) return;
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API}/api/lessons`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_id: repositoryId, goal: "Trace the repository from source to workflow" }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail?.message ?? "Lesson planning failed");
      setLesson(data); setSceneIndex(0);
      const enrol = await fetch(`${API}/api/lessons/${data.lesson_id}/enrol`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ learner_id: "local-learner" }) });
      const enrolData = await enrol.json(); setEnrollmentId(enrolData.enrollment_id);
      await refreshProgress(enrolData.enrollment_id);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  async function refreshProgress(id = enrollmentId) {
    if (!id) return;
    const res = await fetch(`${API}/api/enrollments/${id}/progress`); if (res.ok) setProgress(await res.json());
  }

  async function ask() {
    if (!lesson || !question) return;
    const res = await fetch(`${API}/api/lessons/${lesson.lesson_id}/questions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
    const data = await res.json(); setAnswer(`${data.answer}\n\n${(data.claims ?? []).map((claim: { text: string; evidence_ids: string[] }) => `• ${claim.text} [${claim.evidence_ids.join(", ")}]`).join("\n")}\n\n${(data.unresolved_questions ?? []).join("\n")}`);
  }

  async function submitStep() {
    const step = progress?.steps.find((item) => item.status === "available");
    if (!step || !enrollmentId) return;
    await fetch(`${API}/api/enrollments/${enrollmentId}/attempts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step_id: step.step_id, score: 0.85, evidence_refs: 2 }) });
    await refreshProgress();
  }

  async function render() {
    if (!lesson) return;
    setBusy(true);
    const res = await fetch(`${API}/api/lessons/${lesson.lesson_id}/render`, { method: "POST" });
    const data = await res.json();
    setMediaStatus(`${data.video_status}; narration: ${data.narration?.status ?? "unknown"}`);
    setBusy(false);
  }

  return (
    <main className="shell">
      <header><span className="eyebrow">REPOFLOW AI</span><h1>Understand the codebase. Learn the system.</h1><p>Source-grounded lessons from real repositories.</p></header>
      <section className="card"><h2>System status</h2><p className={health ? "ok" : "muted"}>{health ? `${health.service} ${health.version} is ${health.status}.` : error ?? "Connecting to the local backend…"}</p></section>
      {error && <section className="card error"><strong>Action needed:</strong> {error}</section>}
      <section className="card"><h2>1. Analyse a repository</h2><p>Static analysis creates an immutable, evidence-linked Project Knowledge Model. Uploaded code is not executed.</p><div className="actions"><input value={path} onChange={(event) => setPath(event.target.value)} aria-label="Repository path" /><button onClick={analyse} disabled={busy}>{busy ? "Analysing…" : "Analyse repository"}</button></div>{repositories.length > 0 && <select value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)}><option value="">Select an analysed repository</option>{repositories.map((repo) => <option value={repo.repository_id} key={repo.repository_id}>{repo.name} · {repo.repository_id}</option>)}</select>}</section>
      <section className="card"><h2>2. Create a lesson</h2><p>Chapters, scenes, narration text, source references, and locked learning steps are generated from the pinned PKM revision.</p><button onClick={createLesson} disabled={!repositoryId || busy}>Create evidence-linked lesson</button></section>
      {lesson && currentScene && <section className="lesson-layout"><div className="card player"><div className="player-top"><span>{currentScene.kind.replace(/_/g, " ")}</span><span>{sceneIndex + 1} / {lesson.scenes.length}</span></div><h2>{currentScene.title}</h2><p className="narration">{currentScene.narration}</p><div className="timeline"><div style={{ width: `${((sceneIndex + 1) / lesson.scenes.length) * 100}%` }} /></div><div className="actions"><button onClick={() => setSceneIndex(Math.max(0, sceneIndex - 1))}>Replay previous</button><button onClick={() => setSceneIndex(Math.min(lesson.scenes.length - 1, sceneIndex + 1))}>Next scene</button><button onClick={render} disabled={busy}>Render media</button></div>{mediaStatus && <p className="muted">Media: {mediaStatus}</p>}<p className="source">Source references: {currentScene.source_refs.join(", ") || "No direct source reference; this scene explains the analysis boundary."}</p></div><div className="card"><h2>Learning progression</h2>{progress?.steps.map((step) => <div className={`step ${step.status}`} key={step.step_id}><strong>{step.status}</strong><span>{step.objective}</span></div>)}<button onClick={submitStep} disabled={!progress?.steps.some((step) => step.status === "available")}>Submit evidence-backed checkpoint</button>{progress && <p className="muted">Policy suggestion: {progress.policy_decision.action_id}. This never unlocks a step.</p>}</div></section>}
      {lesson && <section className="card"><h2>Ask about the current lesson</h2><div className="actions"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="How does this repository work?" /><button onClick={ask}>Ask with evidence</button></div>{answer && <pre className="answer">{answer}</pre>}</section>}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
