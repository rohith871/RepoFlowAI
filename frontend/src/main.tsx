import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = "http://127.0.0.1:8000";
type Page = "dashboard" | "repositories" | "architecture" | "assistant" | "learning" | "videos" | "settings";
type VideoScope = "repository" | "module" | "feature" | "question";
type VideoDetail = "summary" | "detailed";
type Repository = { repository_id: string; name?: string; source_url?: string; source_path?: string; description?: string; languages?: string[]; status?: string; summary?: Record<string, number>; last_error?: string | null };
type Overview = { revision_id: string; languages: Record<string, number>; summary: Record<string, number>; unsupported: { path: string; unsupported_reason?: string }[] };
type GraphNode = { id: string; label: string; kind: string; path: string; line_start: number; line_end?: number };
type GraphEdge = { id: string; source: string; target: string; source_label?: string; target_label?: string; type: string; status: string; evidence_ids: string[] };
type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };
type Scene = { scene_id: string; title: string; kind: string; narration: string; source_refs: string[]; duration_ms: number };
type Step = { step_id: string; objective: string; status?: string; completion_criteria: { question_score_min: number; minimum_evidence_refs: number } };
type CheckpointOption = { id: string; text: string; is_correct?: boolean; explanation?: string };
type Checkpoint = { checkpoint_id: string; scene_id: string; checkpoint_type: string; question_text: string; options: CheckpointOption[]; correct_answer_explanation?: string };
type Lesson = { lesson_id: string; repository_id: string; title: string; generation_provider: string; chapters: { chapter_id: string; title: string; scene_ids: string[] }[]; scenes: Scene[]; steps: Step[]; checkpoints?: Checkpoint[] };
type Progress = { steps: Step[]; learner_state: Record<string, number>; policy_decision: { action_id: string; policy_version: string }; checkpoint_progress?: { total: number; answered: number; correct: number; accuracy: number; history: Record<string, any> }; concept_mastery?: Record<string, number>; adaptive_recommendations?: string[] };
type Video = { video_id: string; lesson_id: string; repository_id: string; title: string; topic: string; status: string; manifest: { narration?: { status: string }; chapters?: { title: string; start_ms: number; end_ms: number }[]; video_path?: string; actual_duration_ms?: number; estimated_duration_ms?: number; generation_provider?: string; scope?: string } };
type Message = { message_id: string; role: string; content: string; citations: { evidence_ids?: string[]; text?: string }[] };
type Source = { path: string; content: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail?.message ?? payload.message ?? `Request failed (${response.status})`);
  return payload as T;
}

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [files, setFiles] = useState<{ path: string; language: string; line_count: number }[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [enrollmentId, setEnrollmentId] = useState("");
  const [videos, setVideos] = useState<Video[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [localPath, setLocalPath] = useState("fixtures/sample_project");
  const [githubUrl, setGithubUrl] = useState("");
  const [videoScope, setVideoScope] = useState<VideoScope>("repository");
  const [videoDetail, setVideoDetail] = useState<VideoDetail>("summary");
  const [videoQuestion, setVideoQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = useMemo(() => repositories.find((item) => item.repository_id === selectedRepo), [repositories, selectedRepo]);

  useEffect(() => { void refreshRepositories(); void refreshVideos(); }, []);
  useEffect(() => { if (selectedRepo) void refreshRepository(selectedRepo); }, [selectedRepo]);

  async function refreshRepositories() { try { setRepositories(await api<Repository[]>("/api/repositories")); } catch (err) { setError((err as Error).message); } }
  async function refreshVideos() { try { setVideos(await api<Video[]>("/api/videos")); } catch { setVideos([]); } }
  async function refreshProgress(id: string) { setProgress(await api<Progress>(`/api/enrollments/${id}/progress`)); }
  async function refreshRepository(id: string) {
    try {
      const [nextOverview, nextGraph, nextFiles, lessons, nextMessages] = await Promise.all([
        api<Overview>(`/api/repositories/${id}/overview`),
        api<Graph>(`/api/repositories/${id}/graph`),
        api<{ path: string; language: string; line_count: number }[]>(`/api/repositories/${id}/files`),
        api<Lesson[]>(`/api/repositories/${id}/lessons`),
        api<Message[]>(`/api/repositories/${id}/conversations`),
      ]);
      setOverview(nextOverview); setGraph(nextGraph); setFiles(nextFiles); setMessages(nextMessages);
      const latest = lessons[0];
      if (latest) {
        setLesson(latest);
        const enrol = await api<{ enrollment_id: string }>(`/api/lessons/${latest.lesson_id}/enrol`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ learner_id: "local-learner" }) });
        setEnrollmentId(enrol.enrollment_id); await refreshProgress(enrol.enrollment_id);
      }
    } catch (err) { setError((err as Error).message); }
  }
  async function pollJob(jobId: string): Promise<Record<string, unknown>> {
    for (let index = 0; index < 900; index += 1) {
      const job = await api<{ status: string; progress: number; message: string; result?: Record<string, unknown>; error?: { message: string } }>(`/api/jobs/${jobId}`);
      setNotice(`${job.message} · ${Math.round(job.progress * 100)}%`);
      if (job.status === "completed") return job.result ?? {};
      if (job.status === "failed" || job.status === "cancelled") throw new Error(job.error?.message ?? job.message);
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    throw new Error("Job timed out while waiting for the backend");
  }
  async function analyseLocal() { setBusy(true); setError(""); try { const job = await api<{ job_id: string }>("/api/repositories/analyse-job", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: localPath }) }); const result = await pollJob(job.job_id); await refreshRepositories(); setSelectedRepo(String(result.repository_id)); setPage("repositories"); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function importGithub() { setBusy(true); setError(""); try { const job = await api<{ job_id: string; repository_id: string }>("/api/repositories/import/github", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: githubUrl }) }); await pollJob(job.job_id); await refreshRepositories(); setSelectedRepo(job.repository_id); setPage("repositories"); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function openSource(path: string) { try { setSource(await api<Source>(`/api/repositories/${selectedRepo}/source/${encodeURIComponent(path)}`)); } catch (err) { setError((err as Error).message); } }
  async function createLesson() { if (!selectedRepo) return; setBusy(true); try { const next = await api<Lesson>("/api/lessons", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ repository_id: selectedRepo, goal: "Understand the architecture, data flow, and important source relationships" }) }); setLesson(next); const enrol = await api<{ enrollment_id: string }>(`/api/lessons/${next.lesson_id}/enrol`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ learner_id: "local-learner" }) }); setEnrollmentId(enrol.enrollment_id); await refreshProgress(enrol.enrollment_id); setPage("learning"); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function askQuestion() { if (!selectedRepo || !question) return; setBusy(true); try { const result = await api<{ answer: string; claims: { text: string; evidence_ids: string[] }[]; unresolved_questions: string[] }>(`/api/repositories/${selectedRepo}/questions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }); setMessages((items) => [...items, { message_id: crypto.randomUUID(), role: "user", content: question, citations: [] }, { message_id: crypto.randomUUID(), role: "assistant", content: `${result.answer}\n\n${result.claims.map((claim) => `• ${claim.text} [${claim.evidence_ids.join(", ")}]`).join("\n")}\n\n${result.unresolved_questions.join("\n")}`, citations: result.claims }]); setQuestion(""); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function submitStep() { const step = progress?.steps.find((item) => item.status === "available"); if (!step) return; try { await api(`/api/enrollments/${enrollmentId}/attempts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step_id: step.step_id, score: .85, evidence_refs: 2 }) }); await refreshProgress(enrollmentId); } catch (err) { setError((err as Error).message); } }
  async function requestHint() { const step = progress?.steps.find((item) => item.status === "available"); if (!step) return; try { const hint = await api<{ message: string }>(`/api/enrollments/${enrollmentId}/hints`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step_id: step.step_id }) }); setNotice(hint.message); } catch (err) { setError((err as Error).message); } }
  async function answerCheckpoint(checkpointId: string, optionId: string) {
    if (!enrollmentId) return;
    try {
      const res = await api<{ is_correct: boolean; explanation: string; recommended_action: string }>(
        `/api/enrollments/${enrollmentId}/checkpoint-response`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ checkpoint_id: checkpointId, selected_option_id: optionId }),
        }
      );
      await refreshProgress(enrollmentId);
      return res;
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function requestVideo() { if (!selectedRepo) return; setBusy(true); setError(""); try { const job = await api<{ job_id: string; estimated_duration_ms: number; model: string; model_available: boolean }>(`/api/repositories/${selectedRepo}/video-job`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope: videoScope, detail: videoDetail, question: videoQuestion }) }); setNotice(`${job.model_available ? `LLM configured: ${job.model}` : `Groq/Ollama unavailable; deterministic storyboard used instead of ${job.model}`} · estimated ${Math.round(job.estimated_duration_ms / 1000)}s`); const result = await pollJob(job.job_id); await refreshVideos(); setNotice(`Video finished: ${String(result.video_status ?? "unknown")} · actual ${Math.round(Number(result.actual_duration_ms ?? 0) / 1000)}s`); setPage("videos"); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  async function renderLessonVideo() { if (!lesson) return; setBusy(true); try { const job = await api<{ job_id: string }>(`/api/lessons/${lesson.lesson_id}/render-job`, { method: "POST" }); await pollJob(job.job_id); await refreshVideos(); setPage("videos"); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }

  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark">R</span><span>RepoFlow <b>AI</b></span></div><p className="tagline">Learn the system behind the source.</p><nav>{(["dashboard", "repositories", "architecture", "assistant", "learning", "videos", "settings"] as Page[]).map((item) => <button className={page === item ? "nav-item active" : "nav-item"} onClick={() => setPage(item)} key={item}><span className="nav-icon">{({ dashboard: "⌂", repositories: "◈", architecture: "⌘", assistant: "✦", learning: "◒", videos: "▶", settings: "⚙" } as Record<Page, string>)[item]}</span>{item[0].toUpperCase() + item.slice(1)}</button>)}</nav><div className="sidebar-footer"><span className="status-dot" /> Local workspace<br /><small>Evidence-first mode</small></div></aside><main className="main-content"><header className="topbar"><div><span className="eyebrow">REPOFLOW AI / {page.toUpperCase()}</span><h1>{({ dashboard: "Your codebase, made learnable.", repositories: "Repositories", architecture: "Architecture explorer", assistant: "AI assistant", learning: "Learning workspace", videos: "Video library", settings: "Settings" } as Record<Page, string>)[page]}</h1></div><div className="topbar-actions"><span className="runtime-badge">● Groq → Ollama · qwen2.5-coder:7b</span><button className="ghost" onClick={() => { void refreshRepositories(); void refreshVideos(); }}>Refresh</button></div></header>{error && <div className="alert error"><b>Something needs attention</b><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}{notice && <div className="alert notice"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}{page === "dashboard" && <Dashboard repositories={repositories} videos={videos} selected={selected} onSelect={(id) => { setSelectedRepo(id); setPage("repositories"); }} onStart={() => setPage("repositories")} />} {page === "repositories" && <Repositories repositories={repositories} selectedRepo={selectedRepo} setSelectedRepo={setSelectedRepo} localPath={localPath} setLocalPath={setLocalPath} githubUrl={githubUrl} setGithubUrl={setGithubUrl} analyseLocal={analyseLocal} importGithub={importGithub} busy={busy} selected={selected} overview={overview} files={files} source={source} setSource={setSource} openSource={openSource} createLesson={createLesson} videoScope={videoScope} setVideoScope={setVideoScope} videoDetail={videoDetail} setVideoDetail={setVideoDetail} videoQuestion={videoQuestion} setVideoQuestion={setVideoQuestion} requestVideo={requestVideo} />} {page === "architecture" && <Architecture graph={graph} files={files} source={source} onOpenSource={openSource} />} {page === "assistant" && <Assistant messages={messages} question={question} setQuestion={setQuestion} askQuestion={askQuestion} busy={busy} selected={selected} onVideo={requestVideo} />} {page === "learning" && <Learning lesson={lesson} progress={progress} onCreate={createLesson} onSubmit={submitStep} onHint={requestHint} onRender={renderLessonVideo} onAnswerCheckpoint={answerCheckpoint} busy={busy} selected={selected} />} {page === "videos" && <Videos videos={videos} />} {page === "settings" && <SettingsPanel />} </main></div>;
}

function Dashboard({ repositories, videos, selected, onSelect, onStart }: { repositories: Repository[]; videos: Video[]; selected?: Repository; onSelect: (id: string) => void; onStart: () => void }) { return <div className="page-stack"><section className="hero-panel"><div><span className="eyebrow">SOURCE-GROUNDED LEARNING</span><h2>Turn an unfamiliar repository into a guided understanding.</h2><p>Import code, explore its actual architecture, ask evidence-backed questions, and generate narrated technical stories directly from the repository.</p><button onClick={onStart}>Import a repository <span>→</span></button></div><div className="hero-orbit"><div className="orbit orbit-a" /><div className="orbit orbit-b" /><div className="orbit-core">R</div></div></section><section className="metric-grid"><Metric label="Repositories" value={repositories.length} detail="persisted source workspaces" /><Metric label="Generated videos" value={videos.length} detail="narrated explainers" /><Metric label="Current project" value={selected?.name ?? "—"} detail={selected ? "ready to explore" : "select a repository"} /></section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">RECENT REPOSITORIES</span><h3>Continue where you left off</h3></div></div>{repositories.length === 0 ? <Empty icon="◈" title="No repositories yet" text="Import a GitHub URL or analyze a local repository to begin." action="Import repository" onClick={onStart} /> : <div className="repo-list">{repositories.slice(0, 5).map((repo) => <button className="repo-row" onClick={() => onSelect(repo.repository_id)} key={repo.repository_id}><span className="repo-avatar">{(repo.name ?? "R").slice(0, 1).toUpperCase()}</span><span className="repo-main"><b>{repo.name ?? repo.repository_id}</b><small>{repo.source_url ?? repo.source_path}</small></span><span className="pill success">{repo.status ?? "ready"}</span><span>→</span></button>)}</div>}</section></div>; }
function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) { return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Empty({ icon, title, text, action, onClick }: { icon: string; title: string; text: string; action: string; onClick: () => void }) { return <div className="empty"><span className="empty-icon">{icon}</span><b>{title}</b><p>{text}</p><button className="secondary" onClick={onClick}>{action} →</button></div>; }

function Repositories(props: { repositories: Repository[]; selectedRepo: string; setSelectedRepo: (id: string) => void; localPath: string; setLocalPath: (v: string) => void; githubUrl: string; setGithubUrl: (v: string) => void; analyseLocal: () => void; importGithub: () => void; busy: boolean; selected?: Repository; overview: Overview | null; files: { path: string; language: string; line_count: number }[]; source: Source | null; setSource: (source: Source | null) => void; openSource: (path: string) => void; createLesson: () => void; videoScope: VideoScope; setVideoScope: (v: VideoScope) => void; videoDetail: VideoDetail; setVideoDetail: (v: VideoDetail) => void; videoQuestion: string; setVideoQuestion: (v: string) => void; requestVideo: () => void }) { return <div className="page-stack"><section className="import-grid"><div className="panel import-card"><span className="eyebrow">GITHUB IMPORT</span><h2>Bring a real codebase into the workspace.</h2><p>Clone a public GitHub repository safely, then build an immutable evidence model.</p><div className="input-row"><input value={props.githubUrl} onChange={(event) => props.setGithubUrl(event.target.value)} placeholder="https://github.com/owner/repository" /><button onClick={props.importGithub} disabled={props.busy || !props.githubUrl}>Import & analyze</button></div></div><div className="panel import-card"><span className="eyebrow">LOCAL ANALYSIS</span><h2>Analyze a folder already on this machine.</h2><p>Source snapshots remain local and repository code is never executed.</p><div className="input-row"><input value={props.localPath} onChange={(event) => props.setLocalPath(event.target.value)} placeholder="C:\path\to\repository" /><button onClick={props.analyseLocal} disabled={props.busy || !props.localPath}>Analyze folder</button></div></div></section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">YOUR REPOSITORIES</span><h3>Indexed source workspaces</h3></div><span className="count-badge">{props.repositories.length}</span></div><div className="repo-list">{props.repositories.length === 0 ? <Empty icon="◈" title="Nothing indexed yet" text="Use one of the import options above." action="Use local analysis" onClick={props.analyseLocal} /> : props.repositories.map((repo) => <button className={`repo-row ${props.selectedRepo === repo.repository_id ? "selected" : ""}`} onClick={() => props.setSelectedRepo(repo.repository_id)} key={repo.repository_id}><span className="repo-avatar">{(repo.name ?? "R").slice(0, 1).toUpperCase()}</span><span className="repo-main"><b>{repo.name ?? repo.repository_id}</b><small>{repo.source_url ?? repo.source_path}</small></span><span>{repo.languages?.join(" · ") || "languages pending"}</span><span className="pill success">{repo.status ?? "ready"}</span></button>)}</div></section>{props.selected && <section className="split-grid"><div className="panel"><div className="panel-heading"><div><span className="eyebrow">SELECTED REPOSITORY</span><h3>{props.selected.name ?? props.selected.repository_id}</h3></div><button onClick={props.createLesson}>Create learning path →</button></div><p>{props.selected.description || "Explore the facts and evidence extracted from this revision."}</p>{props.overview && <div className="metric-grid compact">{Object.entries(props.overview.summary).map(([label, value]) => <Metric key={label} label={label} value={value} detail="in pinned revision" />)}</div>}<div className="language-row">{props.overview && Object.entries(props.overview.languages).map(([language, count]) => <span className="tag" key={language}>{language} · {count}</span>)}</div><div className="video-request"><span className="eyebrow">REPOSITORY VIDEO</span><h3>Explain this repository with an animated video.</h3><div className="input-row"><select value={props.videoScope} onChange={(event) => props.setVideoScope(event.target.value as VideoScope)}><option value="repository">Entire repository</option><option value="module">Module or directory</option><option value="feature">Feature or execution path</option><option value="question">Specific question</option></select><select value={props.videoDetail} onChange={(event) => props.setVideoDetail(event.target.value as VideoDetail)}><option value="summary">Summary</option><option value="detailed">Detailed</option></select></div><input value={props.videoQuestion} onChange={(event) => props.setVideoQuestion(event.target.value)} placeholder="Optional feature, module, or question" /><button onClick={props.requestVideo} disabled={props.busy}>Explain with an animated video →</button></div></div><div className="panel code-panel"><div className="panel-heading"><div><span className="eyebrow">SOURCE FILES</span><h3>Open evidence</h3></div></div><div className="file-list">{props.files.slice(0, 12).map((file) => <button onClick={() => props.openSource(file.path)} key={file.path}><span>{file.language}</span><b>{file.path}</b><small>{file.line_count} lines</small></button>)}</div></div></section>}{props.source && <section className="panel source-viewer"><div className="panel-heading"><h3>{props.source.path}</h3><button className="ghost" onClick={() => props.setSource(null)}>Close</button></div><pre>{props.source.content}</pre></section>}</div>; }

function Architecture({ graph, files, source, onOpenSource }: { graph: Graph | null; files: { path: string; language: string; line_count: number }[]; source: Source | null; onOpenSource: (path: string) => void }) {
  const [filter, setFilter] = useState("");
  const [kind, setKind] = useState("all");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const visibleNodes = (graph?.nodes ?? []).filter((node) => (!filter || `${node.label} ${node.path}`.toLowerCase().includes(filter.toLowerCase())) && (kind === "all" || node.kind === kind));
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = (graph?.edges ?? []).filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const positions = new Map(visibleNodes.map((node, index) => [node.id, { x: 90 + (index % 5) * 190, y: 75 + Math.floor(index / 5) * 125 }]));
  return <div className="page-stack"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">EVIDENCE-LINKED GRAPH</span><h3>{graph ? `${visibleNodes.length}/${graph.nodes.length} symbols · ${visibleEdges.length}/${graph.edges.length} relationships` : "Select a repository first"}</h3></div><span className="pill info">static analysis</span></div>{!graph ? <Empty icon="⌘" title="No graph loaded" text="Choose a repository from the Repositories page." action="Open repositories" onClick={() => undefined} /> : <><div className="graph-toolbar"><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search symbols or files" /><select value={kind} onChange={(event) => setKind(event.target.value)}><option value="all">All node types</option>{Array.from(new Set(graph.nodes.map((node) => node.kind))).sort().map((value) => <option value={value} key={value}>{value}</option>)}</select><button className="secondary" onClick={() => setZoom((value) => Math.min(1.8, value + .1))}>Zoom +</button><button className="secondary" onClick={() => setZoom((value) => Math.max(.55, value - .1))}>Zoom −</button><button className="ghost" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset</button></div><div className="graph-canvas interactive" onPointerDown={(event) => { setDragging(true); dragStart.current = { x: event.clientX - pan.x, y: event.clientY - pan.y }; }} onPointerMove={(event) => { if (dragging) setPan({ x: event.clientX - dragStart.current.x, y: event.clientY - dragStart.current.y }); }} onPointerUp={() => setDragging(false)} onPointerLeave={() => setDragging(false)}><svg className="graph-svg" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }} viewBox="0 0 1050 620">{visibleEdges.map((edge) => { const start = positions.get(edge.source); const end = positions.get(edge.target); return start && end ? <g key={edge.id}><line x1={start.x + 70} y1={start.y + 35} x2={end.x + 70} y2={end.y + 35} className="graph-edge-line" /><text x={(start.x + end.x) / 2 + 70} y={(start.y + end.y) / 2 + 28} className="graph-edge-label">{edge.type}</text></g> : null; })}{visibleNodes.map((node) => { const position = positions.get(node.id) ?? { x: 0, y: 0 }; return <g key={node.id} className="graph-svg-node" onClick={() => onOpenSource(node.path)}><rect x={position.x} y={position.y} width="140" height="70" rx="10" /><text x={position.x + 10} y={position.y + 20} className="graph-node-kind">{node.kind}</text><text x={position.x + 10} y={position.y + 42} className="graph-node-label">{node.label.slice(0, 19)}</text><text x={position.x + 10} y={position.y + 59} className="graph-node-path">{node.path.split("/").slice(-1)[0]}:{node.line_start}</text></g>; })}</svg></div><div className="relationship-list compact-list">{visibleEdges.slice(0, 24).map((edge) => <div className="relationship" key={edge.id}><b>{edge.type}</b><span>{edge.source_label ?? edge.source.slice(0, 12)} → {edge.target_label ?? edge.target.slice(0, 12)}</span><small>{edge.status} · {edge.evidence_ids.length} evidence</small></div>)}</div></>}</section>{source && <section className="panel source-viewer"><div className="panel-heading"><h3>{source.path}</h3></div><pre>{source.content}</pre></section>}<section className="panel"><div className="panel-heading"><div><span className="eyebrow">FILE INVENTORY</span><h3>Browse source references</h3></div></div><div className="file-grid">{files.map((file) => <button className="file-card" onClick={() => onOpenSource(file.path)} key={file.path}><span>{file.language}</span><b>{file.path}</b><small>{file.line_count} lines</small></button>)}</div></section></div>;
}

function Assistant({ messages, question, setQuestion, askQuestion, busy, selected, onVideo }: { messages: Message[]; question: string; setQuestion: (value: string) => void; askQuestion: () => void; busy: boolean; selected?: Repository; onVideo: () => void }) { return <div className="assistant-layout"><section className="panel conversation"><div className="conversation-head"><div><span className="eyebrow">SOURCE-GROUNDED ASSISTANT</span><h3>{selected?.name ?? "Select a repository"}</h3></div><button className="secondary" onClick={onVideo} disabled={!selected || busy}>Turn this topic into a video</button></div><div className="messages">{messages.length === 0 ? <Empty icon="✦" title="Ask a repository question" text="Answers cite retrieved evidence and clearly label unresolved behavior." action="Ask below" onClick={() => undefined} /> : messages.map((message) => <div className={`message ${message.role}`} key={message.message_id}><span className="message-role">{message.role === "assistant" ? "REPOFLOW AI" : "YOU"}</span><p>{message.content}</p>{message.citations.length > 0 && <div className="citation-row">{message.citations.map((citation, index) => <span className="citation" key={`${message.message_id}-${index}`}>evidence {citation.evidence_ids?.[0] ?? "linked"}</span>)}</div>}</div>)}</div><div className="composer"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); askQuestion(); } }} placeholder="Ask how a request, function, or data flow works…" /><button onClick={askQuestion} disabled={busy || !question || !selected}>{busy ? "Thinking…" : "Ask"}</button></div></section><aside className="panel context-card"><span className="eyebrow">CONTEXT RULES</span><h3>Grounded by the selected revision</h3><ul><li>Exact files and symbols are retrieved first.</li><li>Claims must cite stored evidence.</li><li>Ambiguous relationships stay ambiguous.</li><li>Any answer can become a focused video.</li></ul></aside></div>; }

function Learning({
  lesson,
  progress,
  onCreate,
  onSubmit,
  onHint,
  onRender,
  onAnswerCheckpoint,
  busy,
  selected,
}: {
  lesson: Lesson | null;
  progress: Progress | null;
  onCreate: () => void;
  onSubmit: () => void;
  onHint: () => void;
  onRender: () => void;
  onAnswerCheckpoint: (checkpointId: string, optionId: string) => Promise<any>;
  busy: boolean;
  selected?: Repository;
}) {
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const [answering, setAnswering] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, { is_correct: boolean; explanation: string; action: string }>>({});

  const checkpoints = lesson?.checkpoints || [];
  const history = progress?.checkpoint_progress?.history || {};

  async function handleOptionSubmit(checkpointId: string) {
    const optId = selectedOptions[checkpointId];
    if (!optId) return;
    setAnswering(checkpointId);
    try {
      const res = await onAnswerCheckpoint(checkpointId, optId);
      if (res) {
        setFeedback((prev) => ({
          ...prev,
          [checkpointId]: {
            is_correct: res.is_correct,
            explanation: res.explanation,
            action: res.recommended_action,
          },
        }));
      }
    } finally {
      setAnswering(null);
    }
  }

  return (
    <div className="page-stack">
      {!lesson ? (
        <section className="panel">
          <Empty
            icon="◒"
            title="No active learning path"
            text={selected ? `Create an evidence-linked lesson from ${selected.name ?? "the selected repository"}.` : "Select and analyze a repository first."}
            action="Create learning path"
            onClick={onCreate}
          />
        </section>
      ) : (
        <>
          <section className="lesson-banner">
            <div>
              <span className="eyebrow">{lesson.generation_provider}</span>
              <h2>{lesson.title}</h2>
              <p>
                {lesson.scenes.length} scenes · {lesson.steps.length} assessed steps · {checkpoints.length} interactive checkpoints
              </p>
            </div>
            <span className="lesson-badge">
              {progress?.steps.filter((step) => step.status === "completed").length ?? 0}/{lesson.steps.length} complete
            </span>
          </section>

          <section className="split-grid">
            <div className="panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">SEQUENTIAL PATH</span>
                  <h3>Complete the next demonstrable step</h3>
                </div>
              </div>
              {progress?.steps.map((step, index) => (
                <div className={`learning-step ${step.status}`} key={step.step_id}>
                  <span className="step-number">{index + 1}</span>
                  <div>
                    <b>{step.objective}</b>
                    <small>
                      {step.status === "locked"
                        ? "Complete the prerequisite to unlock"
                        : step.status === "completed"
                        ? "Completed with backend evidence"
                        : "Available now"}
                    </small>
                  </div>
                  <span className="status-label">{step.status}</span>
                </div>
              ))}
              <div className="actions">
                <button onClick={onSubmit} disabled={!progress?.steps.some((step) => step.status === "available")}>
                  Submit step verification
                </button>
                <button className="secondary" onClick={onHint} disabled={!progress?.steps.some((step) => step.status === "available")}>
                  Request hint
                </button>
                <button className="secondary" onClick={onRender} disabled={busy}>
                  {busy ? "Rendering…" : "Render lesson video"}
                </button>
              </div>
            </div>

            <div className="panel">
              <span className="eyebrow">ADAPTIVE LEARNER MODEL</span>
              <h3>Mastery & Recommendations</h3>
              
              {/* Concept Mastery Bars */}
              <div style={{ marginTop: 14, marginBottom: 20 }}>
                <span className="eyebrow">CONCEPT MASTERY</span>
                {Object.entries(progress?.concept_mastery ?? {}).length === 0 ? (
                  <p className="muted">Answer checkpoints below to calibrate concept mastery.</p>
                ) : (
                  Object.entries(progress?.concept_mastery ?? {}).map(([concept, score]) => (
                    <div key={concept} style={{ marginTop: 8 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 3 }}>
                        <span style={{ textTransform: "capitalize", color: "#a5c4e0" }}>{concept.replace(/_/g, " ")}</span>
                        <b style={{ color: score >= 0.8 ? "#66e2a8" : score >= 0.5 ? "#f0c57d" : "#ff85a0" }}>{Math.round(score * 100)}%</b>
                      </div>
                      <div style={{ width: "100%", height: 6, backgroundColor: "#0b1c2e", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{ width: `${Math.round(score * 100)}%`, height: "100%", backgroundColor: score >= 0.8 ? "#66e2a8" : score >= 0.5 ? "#f0c57d" : "#ff85a0" }} />
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Adaptive Guidance Recommendations */}
              {progress?.adaptive_recommendations && progress.adaptive_recommendations.length > 0 && (
                <div style={{ backgroundColor: "#0e2438", padding: 14, borderRadius: 10, border: "1px solid #1f476b", marginBottom: 16 }}>
                  <span className="eyebrow">TARGETED GUIDANCE</span>
                  <ul style={{ margin: "6px 0 0 0", paddingLeft: 18, fontSize: 13, color: "#d0e4f7", lineHeight: 1.5 }}>
                    {progress.adaptive_recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="state-grid">
                <div>
                  <small>Checkpoint Accuracy</small>
                  <b>{progress?.checkpoint_progress?.accuracy ?? 0}%</b>
                </div>
                <div>
                  <small>Independence Score</small>
                  <b>{((progress?.learner_state?.independence_score ?? 0) * 100).toFixed(0)}%</b>
                </div>
              </div>
              <p className="muted">Active RL policy: <b>{progress?.policy_decision.action_id}</b>.</p>
            </div>
          </section>

          {/* Interactive Checkpoints Section */}
          {checkpoints.length > 0 && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">ACTIVE LEARNING</span>
                  <h3>Grounded Checkpoints ({progress?.checkpoint_progress?.answered ?? 0}/{checkpoints.length} Answered)</h3>
                </div>
              </div>
              <div style={{ display: "grid", gap: 16 }}>
                {checkpoints.map((chk, idx) => {
                  const past = history[chk.checkpoint_id] || feedback[chk.checkpoint_id];
                  const isAnswered = !!past;
                  const isCorrect = past?.is_correct;
                  const selectedOpt = selectedOptions[chk.checkpoint_id] || past?.selected_option_id;

                  return (
                    <div
                      key={chk.checkpoint_id}
                      style={{
                        padding: 18,
                        borderRadius: 12,
                        backgroundColor: "#081626",
                        border: isCorrect ? "1px solid #23634e" : isAnswered ? "1px solid #6b3e23" : "1px solid #1a3854",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                        <span className="eyebrow">
                          QUESTION {idx + 1} • {chk.checkpoint_type.toUpperCase()}
                        </span>
                        {isAnswered && (
                          <span className={`pill ${isCorrect ? "success" : "warning"}`}>
                            {isCorrect ? "✓ Mastered" : "⚠ Needs Review"}
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: 16, fontWeight: 600, color: "#ffffff", margin: "0 0 14px 0" }}>
                        {chk.question_text}
                      </p>

                      <div style={{ display: "grid", gap: 8, marginBottom: 14 }}>
                        {chk.options.map((opt) => (
                          <label
                            key={opt.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 10,
                              padding: "10px 14px",
                              borderRadius: 8,
                              backgroundColor: selectedOpt === opt.id ? "#133856" : "#0c1f33",
                              border: selectedOpt === opt.id ? "1px solid #64d7ff" : "1px solid #1d3b59",
                              cursor: "pointer",
                              fontSize: 14,
                              color: "#e2effa",
                            }}
                          >
                            <input
                              type="radio"
                              name={chk.checkpoint_id}
                              value={opt.id}
                              checked={selectedOpt === opt.id}
                              onChange={() => setSelectedOptions((prev) => ({ ...prev, [chk.checkpoint_id]: opt.id }))}
                              disabled={isAnswered}
                            />
                            <span>{opt.text}</span>
                          </label>
                        ))}
                      </div>

                      {!isAnswered ? (
                        <button
                          onClick={() => handleOptionSubmit(chk.checkpoint_id)}
                          disabled={!selectedOptions[chk.checkpoint_id] || answering === chk.checkpoint_id}
                          style={{
                            backgroundColor: "#64d7ff",
                            color: "#051321",
                            padding: "8px 16px",
                            borderRadius: 8,
                            fontWeight: 700,
                            cursor: "pointer",
                          }}
                        >
                          {answering === chk.checkpoint_id ? "Evaluating…" : "Submit Answer"}
                        </button>
                      ) : (
                        <div style={{ marginTop: 8, padding: "10px 14px", borderRadius: 8, backgroundColor: isCorrect ? "#0d2b22" : "#2e190f", borderLeft: isCorrect ? "4px solid #66e2a8" : "4px solid #f59f00" }}>
                          <b style={{ color: isCorrect ? "#66e2a8" : "#ffd43b", fontSize: 14 }}>
                            {isCorrect ? "Explanation:" : "Guidance:"}
                          </b>
                          <p style={{ margin: "4px 0 0 0", fontSize: 13, color: "#dbe8f5", lineHeight: 1.4 }}>
                            {past?.explanation || chk.correct_answer_explanation}
                          </p>
                          {past?.recommended_action && (
                            <small style={{ color: "#74c0fc", display: "block", marginTop: 4 }}>
                              Recommended next action: {past.recommended_action.replace(/_/g, " ")}
                            </small>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">LESSON SCENES</span>
                <h3>Repository-specific teaching story</h3>
              </div>
            </div>
            <div className="scene-grid">
              {lesson.scenes.map((scene) => (
                <div className="scene-card" key={scene.scene_id}>
                  <span>{scene.kind.replace(/_/g, " ")}</span>
                  <b>{scene.title}</b>
                  <p>{scene.narration}</p>
                  <small>{scene.source_refs.join(", ") || "analysis boundary"}</small>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Videos({ videos }: { videos: Video[] }) { const [active, setActive] = useState<Video | null>(videos[0] ?? null); const player = useRef<HTMLVideoElement>(null); useEffect(() => { if (videos[0] && (!active || !videos.some((video) => video.video_id === active.video_id))) setActive(videos[0]); }, [videos, active]); return <div className="page-stack"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">MEDIA LIBRARY</span><h3>Generated technical explainers</h3></div><span className="count-badge">{videos.length}</span></div>{videos.length === 0 ? <Empty icon="▶" title="No videos yet" text="Request an explainer from a repository or the assistant." action="Open repositories" onClick={() => undefined} /> : <div className="video-library">{videos.map((video) => <button className={`video-row ${active?.video_id === video.video_id ? "selected" : ""}`} onClick={() => setActive(video)} key={video.video_id}><span className="video-thumb">▶</span><span><b>{video.title}</b><small>{video.topic} · {video.manifest.scope ?? "lesson"} · {video.manifest.narration?.status ?? "unknown narration"}</small></span><span className={`pill ${video.status === "playable" ? "success" : "warning"}`}>{video.status}</span></button>)}</div>}</section>{active?.status === "playable" && <section className="panel player-panel"><div className="panel-heading"><div><span className="eyebrow">NOW PLAYING</span><h3>{active.title}</h3><small className="muted">{active.manifest.generation_provider} · {Math.round((active.manifest.actual_duration_ms ?? 0) / 1000)}s actual</small></div></div><video ref={player} controls preload="metadata" src={`${API}/api/lessons/${active.lesson_id}/media/video`}><track kind="subtitles" src={`${API}/api/lessons/${active.lesson_id}/media/captions`} srcLang="en" label="English" default /></video><div className="chapter-row">{active.manifest.chapters?.map((chapter) => <button className="tag" onClick={() => { if (player.current) player.current.currentTime = chapter.start_ms / 1000; }} key={chapter.title}>{chapter.title}</button>)}</div></section>}</div>; }

function SettingsPanel() { return <div className="page-stack"><section className="panel settings-card"><span className="eyebrow">MODEL ROUTING</span><h2>Groq first, local Qwen when needed.</h2><p>Groq is attempted first when <code>GROQ_API_KEY</code> is configured. Ollama uses the locally installed <code>qwen2.5-coder:7b</code> model as the fallback.</p><div className="setting-row"><span><b>Primary</b><small>Groq · configurable via GROQ_MODEL</small></span><span className="pill info">first</span></div><div className="setting-row"><span><b>Fallback</b><small>Ollama · http://localhost:11434 · qwen2.5-coder:7b</small></span><span className="pill success">enabled</span></div><div className="setting-row"><span><b>Narration</b><small>Pocket TTS · alba voice · measured scene durations</small></span><span className="pill success">configured</span></div><div className="setting-row"><span><b>Video renderer</b><small>deterministic frame scenes + FFmpeg assembly</small></span><span className="pill info">active</span></div></section><section className="panel"><span className="eyebrow">SAFETY</span><h3>Boundaries</h3><ul className="safety-list"><li>Uploaded repository code is never executed.</li><li>Storyboard references are validated against the pinned revision.</li><li>Provider and model metadata is persisted with generated results.</li><li>Adaptive policy decisions never unlock steps by themselves.</li></ul></section></div>; }

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
