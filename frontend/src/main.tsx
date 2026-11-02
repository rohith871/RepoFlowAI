import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

type Workspace =
  | "dashboard"
  | "repositories"
  | "architecture"
  | "flows"
  | "videos"
  | "learning"
  | "generator"
  | "profile";

type Repository = {
  repository_id: string;
  name?: string;
  source_path?: string;
  source_url?: string;
  languages?: string[];
  status?: string;
  summary?: Record<string, number>;
  latest_published_revision_id?: string;
};

type ArchView = {
  view_id: string;
  question: string;
  view_type: string;
  components: any[];
  boundaries: any[];
  relationships: any[];
  annotations: any[];
  layout_data?: Record<string, any>;
};

type ExecutionPath = {
  path_id: string;
  name: string;
  description: string;
  steps: any[];
  data_lineage?: any[];
};

type Video = {
  video_id: string;
  lesson_id: string;
  repository_id: string;
  title: string;
  topic: string;
  status: string;
  manifest: {
    video_path?: string;
    actual_duration_ms?: number;
    renderer?: string;
    chapters?: { title: string; start_ms: number; end_ms: number }[];
    transcript_validation?: any;
    scenes?: any[];
  };
};

type LearnerProfile = {
  learner_id: string;
  concept_mastery: Record<string, number>;
  projects_enrolled: string[];
  completed_projects: string[];
  project_history: string[];
  demonstrated_transfers: any[];
  total_hints_used: number;
  tutor_takeovers_count: number;
  tutor_takeovers_used?: number;
  dqn_features?: Record<string, number>;
  dqn_decision?: { action_id: string; policy_version: string; reason_code: string };
};

type LearningTask = {
  task_id: string;
  stage_id: string;
  order: number;
  title: string;
  learning_objective: string;
  why_it_matters: string;
  required_concepts: string[];
  relevant_files: string[];
  presentation_level: string;
  instructions: string;
  expected_outcome: string;
  completion_criteria: Record<string, any>;
  hints: { level: string; hint: string }[];
  tutor_demonstration?: any;
  follow_up_challenge?: any;
  status: string;
  attempts_count: number;
  hints_used: number;
  completed_at?: string;
  learner_response?: string;
  evaluation_feedback?: string;
};

type LearningStage = {
  stage_id: string;
  project_id: string;
  order: number;
  title: string;
  description: string;
  primary_concept: string;
  purpose?: string;
  why_it_matters?: string;
  learning_objectives?: string[];
  prerequisites?: string[];
  concepts_to_understand?: string[];
  expected_deliverables?: string;
  completion_criteria?: string;
  relevant_files_or_resources?: string[];
  video_id?: string;
  video_path?: string;
  video_generation_status?: string;
  video_url?: string;
  captions_url?: string;
  video_duration_seconds?: number;
  stage_video?: any;
  tasks: LearningTask[];
  status: string;
};

type LearningProject = {
  project_id: string;
  repository_id: string;
  learner_id: string;
  title: string;
  description: string;
  entry_mode?: string;
  domain?: string;
  reference_repository_id?: string;
  transferred_concepts?: any[];
  architecture_differences?: string;
  tools_and_technologies?: string[];
  learner_recommendation_reason?: string;
  stages: LearningStage[];
  status: string;
  total_tasks: number;
  completed_tasks: number;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail?.message ?? payload.message ?? `Request failed (${response.status})`);
  return payload as T;
}

export function App() {
  const [workspace, setWorkspace] = useState<Workspace>("dashboard");
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("");
  const [learnerId] = useState("default_learner");

  // Repository data
  const [overview, setOverview] = useState<any>(null);
  const [archViews, setArchViews] = useState<ArchView[]>([]);
  const [activeViewType, setActiveViewType] = useState("high_level_system");
  const [flows, setFlows] = useState<ExecutionPath[]>([]);
  const [files, setFiles] = useState<any[]>([]);
  const [activeFile, setActiveFile] = useState<any>(null);
  const [sourceCode, setSourceCode] = useState<string>("");

  // Architecture inspector
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [selectedEdge, setSelectedEdge] = useState<any>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [subsystemFilter, setSubsystemFilter] = useState("all");

  // Media
  const [videos, setVideos] = useState<Video[]>([]);
  const [activeVideo, setActiveVideo] = useState<Video | null>(null);

  // Learning Project
  const [activeProject, setActiveProject] = useState<LearningProject | null>(null);
  const [learnerProfile, setLearnerProfile] = useState<LearnerProfile | null>(null);
  const [expandedStageId, setExpandedStageId] = useState<string>("");
  const [revealedHints, setRevealedHints] = useState<Record<string, number>>({});
  const [solutionInputs, setSolutionInputs] = useState<Record<string, string>>({});
  const [activeTakeoverTask, setActiveTakeoverTask] = useState<LearningTask | null>(null);
  const [playingStageVideoId, setPlayingStageVideoId] = useState<string | null>(null);
  const [playingRepoExplainer, setPlayingRepoExplainer] = useState<boolean>(false);
  const [videoPlaybackRate, setVideoPlaybackRate] = useState<number>(1.0);

  // Ingestion inputs
  const [localPathInput, setLocalPathInput] = useState("fixtures/sample_project");
  const [githubUrlInput, setGithubUrlInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const selectedRepo = useMemo(() => repositories.find((r) => r.repository_id === selectedRepoId), [repositories, selectedRepoId]);
  const activeView = useMemo(() => archViews.find((v) => v.view_type === activeViewType) ?? archViews[0] ?? null, [archViews, activeViewType]);

  // Initial load
  useEffect(() => {
    void refreshRepositories();
    void refreshVideos();
    void refreshProfile();
  }, []);

  // When selected repo changes, refresh repo details
  useEffect(() => {
    if (selectedRepoId) void loadRepoData(selectedRepoId);
  }, [selectedRepoId]);

  async function refreshRepositories() {
    try {
      const list = await api<Repository[]>("/api/repositories");
      setRepositories(list);
      if (list.length > 0 && !selectedRepoId) {
        setSelectedRepoId(list[0].repository_id);
      }
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function refreshVideos() {
    try {
      const list = await api<Video[]>("/api/videos");
      setVideos(list);
      if (list.length > 0 && !activeVideo) setActiveVideo(list[0]);
    } catch {
      setVideos([]);
    }
  }

  async function refreshProfile() {
    try {
      const prof = await api<LearnerProfile>(`/api/learners/${learnerId}/profile`);
      setLearnerProfile(prof);
      const projs = await api<LearningProject[]>(`/api/learners/${learnerId}/projects`);
      if (projs.length > 0 && !activeProject) {
        setActiveProject(projs[0]);
        if (projs[0].stages.length > 0) setExpandedStageId(projs[0].stages[0].stage_id);
      }
    } catch {}
  }

  async function loadRepoData(repoId: string) {
    try {
      setBusy(true);
      const [ov, views, fl, flist] = await Promise.all([
        api<any>(`/api/repositories/${repoId}/overview`).catch(() => null),
        api<ArchView[]>(`/api/repositories/${repoId}/views`).catch(() => []),
        api<ExecutionPath[]>(`/api/repositories/${repoId}/flows`).catch(() => []),
        api<any[]>(`/api/repositories/${repoId}/files`).catch(() => []),
      ]);
      setOverview(ov);
      setArchViews(views);
      setFlows(fl);
      setFiles(flist);
      if (flist.length > 0) {
        setActiveFile(flist[0]);
        void loadSource(repoId, flist[0].path);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadSource(repoId: string, path: string) {
    try {
      const res = await api<{ content: string }>(`/api/repositories/${repoId}/source/${path}`);
      setSourceCode(res.content);
    } catch {
      setSourceCode("// Could not load source content.");
    }
  }

  // Repository Ingestion Handlers
  async function handleAnalyseLocal() {
    if (!localPathInput.trim()) return;
    try {
      setBusy(true);
      setError("");
      setNotice(`Analyzing codebase at ${localPathInput}...`);
      const res = await api<any>("/api/repositories/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: localPathInput.trim() }),
      });
      await refreshRepositories();
      setSelectedRepoId(res.repository_id);
      setNotice(`Repository analyzed successfully! Verified ${res.summary?.symbols ?? 0} symbols.`);
      setWorkspace("architecture");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleImportGithub() {
    if (!githubUrlInput.trim()) return;
    try {
      setBusy(true);
      setError("");
      setNotice(`Cloning and analyzing GitHub repository ${githubUrlInput}...`);
      const res = await api<any>("/api/repositories/import/github", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: githubUrlInput.trim() }),
      });
      await refreshRepositories();
      setSelectedRepoId(res.repository_id);
      setNotice(`GitHub repository ingested successfully!`);
      setWorkspace("architecture");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // Video Rendering Handlers
  async function handleRenderRepoExplainer() {
    if (!selectedRepoId) return;
    try {
      setBusy(true);
      setError("");
      setNotice(`Rendering YouTube-grade technical explainer video for ${selectedRepo?.name ?? selectedRepoId}...`);
      await api<any>(`/api/repositories/${selectedRepoId}/render-explainer`, { method: "POST" });
      await refreshVideos();
      setPlayingRepoExplainer(true);
      setNotice("Repository explainer video rendered and validated! Ready to watch.");
    } catch (err: any) {
      setError(`Explainer video render failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRenderStageVideo(stageId: string) {
    if (!activeProject) return;
    try {
      setBusy(true);
      setError("");
      setNotice("Rendering and validating dedicated technical teaching video for this stage...");
      await api<any>(`/api/learning-projects/${activeProject.project_id}/stages/${stageId}/render-video`, { method: "POST" });
      const updatedProj = await api<LearningProject>(`/api/learning-projects/${activeProject.project_id}`);
      setActiveProject(updatedProj);
      await refreshVideos();
      setPlayingStageVideoId(stageId);
      setNotice("Stage video verified! You can watch it directly in this stage.");
    } catch (err: any) {
      setError(`Stage video render failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  // 3 Entry Modes
  async function handleGenerateDomainProject(domain: string) {
    try {
      setBusy(true);
      setError("");
      setNotice(`Generating original 8-stage ${domain} project curriculum...`);
      const proj = await api<LearningProject>("/api/projects/generate/domain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, learner_id: learnerId }),
      });
      setActiveProject(proj);
      if (proj.stages.length > 0) setExpandedStageId(proj.stages[0].stage_id);
      await refreshProfile();
      setNotice(`Project '${proj.title}' generated successfully!`);
      setWorkspace("learning");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRecommendProject() {
    try {
      setBusy(true);
      setError("");
      setNotice("AI Tutor is evaluating your profile, skills, and gaps to recommend an optimal project...");
      const res = await api<any>("/api/projects/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ learner_id: learnerId }),
      });
      setActiveProject(res.project);
      if (res.project.stages.length > 0) setExpandedStageId(res.project.stages[0].stage_id);
      await refreshProfile();
      setNotice(`AI Tutor recommended: '${res.project.title}' (${res.recommended_domain})`);
      setWorkspace("learning");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateReferenceInspiredProject() {
    if (!selectedRepoId) {
      setError("Please select or upload a reference repository first.");
      return;
    }
    try {
      setBusy(true);
      setError("");
      setNotice(`Deeply analyzing '${selectedRepo?.name ?? selectedRepoId}' to generate an original inspired project...`);
      const proj = await api<LearningProject>("/api/projects/generate/reference", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository_id: selectedRepoId, learner_id: learnerId }),
      });
      setActiveProject(proj);
      if (proj.stages.length > 0) setExpandedStageId(proj.stages[0].stage_id);
      await refreshProfile();
      setNotice(`Original project inspired by '${selectedRepo?.name}' generated!`);
      setWorkspace("learning");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // Task interaction
  async function handleRevealHint(taskId: string) {
    if (!activeProject) return;
    try {
      await api<any>(`/api/learning-projects/${activeProject.project_id}/tasks/${taskId}/hint`, { method: "POST" });
      setRevealedHints((prev) => ({ ...prev, [taskId]: (prev[taskId] ?? 0) + 1 }));
      const updatedProj = await api<LearningProject>(`/api/learning-projects/${activeProject.project_id}`);
      setActiveProject(updatedProj);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleSubmitSolution(taskId: string) {
    if (!activeProject) return;
    const text = solutionInputs[taskId] ?? "";
    if (text.trim().length < 5) {
      setError("Please write an implementation solution before submitting.");
      return;
    }
    try {
      setBusy(true);
      const res = await api<any>(`/api/learning-projects/${activeProject.project_id}/tasks/${taskId}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ learner_response: text, learner_id: learnerId }),
      });
      const updatedProj = await api<LearningProject>(`/api/learning-projects/${activeProject.project_id}`);
      setActiveProject(updatedProj);
      await refreshProfile();
      if (res.passed) {
        setNotice("Task evaluated and PASSED! Concept mastery updated.");
      } else {
        setError(res.evaluation_feedback || "Evaluation incomplete.");
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleTriggerTutorTakeover(task: LearningTask) {
    if (!activeProject) return;
    try {
      setBusy(true);
      const res = await api<any>(`/api/learning-projects/${activeProject.project_id}/tasks/${task.task_id}/tutor-takeover`, { method: "POST" });
      const updatedProj = await api<LearningProject>(`/api/learning-projects/${activeProject.project_id}`);
      setActiveProject(updatedProj);
      setActiveTakeoverTask({ ...task, tutor_demonstration: res.tutor_demonstration, follow_up_challenge: res.follow_up_challenge });
      await refreshProfile();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      {/* SIDEBAR NAVIGATION */}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">RF</span>
          <span>RepoFlow<b>AI</b></span>
        </div>
        <p className="tagline">Intelligent Software Tutor & Codebase Understanding</p>

        {/* REPOSITORY QUICK PICKER */}
        <div style={{ padding: "0 12px 18px" }}>
          <small style={{ display: "block", color: "#65d6ff", fontSize: "10px", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: "6px" }}>
            Active Repository
          </small>
          <select
            style={{ width: "100%", background: "#0a1727", color: "#e6f2ff", border: "1px solid #1e3852", borderRadius: "8px", padding: "8px", fontSize: "12px", cursor: "pointer", outline: "none" }}
            value={selectedRepoId}
            onChange={(e) => setSelectedRepoId(e.target.value)}
            title="Switch the active repository for architecture, flows, and source exploration"
          >
            {repositories.map((r) => {
              const displayName = r.name && r.name !== "source" ? r.name : r.repository_id;
              const fileCount = r.summary?.files;
              const langStr = r.languages && r.languages.length > 0 ? ` · ${r.languages.slice(0, 2).join(", ")}` : "";
              const label = `${displayName}${fileCount ? ` (${fileCount} files${langStr})` : ""}`;
              return (
                <option key={r.repository_id} value={r.repository_id}>
                  {label}
                </option>
              );
            })}
          </select>
        </div>

        {/* 8 WORKSPACES */}
        <nav>
          <button className={`nav-item ${workspace === "dashboard" ? "active" : ""}`} onClick={() => setWorkspace("dashboard")}>
            <span className="nav-icon">⊞</span> Dashboard
          </button>
          <button className={`nav-item ${workspace === "repositories" ? "active" : ""}`} onClick={() => setWorkspace("repositories")}>
            <span className="nav-icon">📁</span> Codebase Explorer
          </button>
          <button className={`nav-item ${workspace === "architecture" ? "active" : ""}`} onClick={() => setWorkspace("architecture")}>
            <span className="nav-icon">☊</span> Architecture Studio
          </button>
          <button className={`nav-item ${workspace === "flows" ? "active" : ""}`} onClick={() => setWorkspace("flows")}>
            <span className="nav-icon">⇄</span> Execution Flows
          </button>
          <button className={`nav-item ${workspace === "videos" ? "active" : ""}`} onClick={() => setWorkspace("videos")}>
            <span className="nav-icon">▶</span> Video Studio
          </button>
          <button className={`nav-item ${workspace === "learning" ? "active" : ""}`} onClick={() => setWorkspace("learning")}>
            <span className="nav-icon">🎓</span> Learning Workspace
          </button>
          <button className={`nav-item ${workspace === "generator" ? "active" : ""}`} onClick={() => setWorkspace("generator")}>
            <span className="nav-icon">⚡</span> Project Generator
          </button>
          <button className={`nav-item ${workspace === "profile" ? "active" : ""}`} onClick={() => setWorkspace("profile")}>
            <span className="nav-icon">👤</span> Learner Profile
          </button>
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot"></span>
          <b>DQN Adaptive Policy</b>
          <br />
          <small>{learnerProfile?.dqn_decision?.action_id ?? "active"}</small>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <main className="main-content">
        {/* TOP BAR */}
        <header className="topbar">
          <div>
            <span className="eyebrow">ENTERPRISE ONBOARDING & ACTIVE LEARNING PLATFORM</span>
            <h1>
              {workspace === "dashboard" && "Platform Overview"}
              {workspace === "repositories" && "Repository Ingestion & Source Explorer"}
              {workspace === "architecture" && "Interactive 7-Perspective Architecture Studio"}
              {workspace === "flows" && "Reconstructed Causal Execution Journeys"}
              {workspace === "videos" && "Technical Media Studio & Remotion Player"}
              {workspace === "learning" && "Adaptive Project-Based Learning Workspace"}
              {workspace === "generator" && "Software Project Generator (3 Entry Modes)"}
              {workspace === "profile" && "DQN Adaptive Policy & Cross-Project Mastery"}
            </h1>
          </div>
          <div className="topbar-actions">
            {selectedRepo && <span className="count-badge">Repo: {selectedRepo.name ?? selectedRepo.repository_id}</span>}
            <span className="runtime-badge">● Remotion 1080p Engine Ready</span>
          </div>
        </header>

        {/* ALERTS */}
        {error && (
          <div className="alert error">
            <span>{error}</span>
            <button onClick={() => setError("")}>✕</button>
          </div>
        )}
        {notice && (
          <div className="alert notice">
            <span>{notice}</span>
            <button onClick={() => setNotice("")}>✕</button>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 1: DASHBOARD
           ========================================================================= */}
        {workspace === "dashboard" && (
          <div className="page-stack">
            {/* HERO PANEL */}
            <section className="hero-panel">
              <div>
                <span className="eyebrow">INTELLIGENT REPOSITORY TUTOR</span>
                <h2>Understand Real Software. Build Authentic Projects.</h2>
                <p>
                  RepoFlow AI bridges static repository evidence, interactive architecture reasoning, professional YouTube-grade technical animations, and an independent adaptive tutor.
                </p>
                <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
                  <button className="btn-primary" onClick={() => setWorkspace("repositories")}>
                    Analyze a Codebase <span>→</span>
                  </button>
                  <button className="btn-secondary" onClick={() => setWorkspace("generator")}>
                    Generate Learning Project <span>⚡</span>
                  </button>
                </div>
              </div>
              <div className="hero-orbit">
                <div className="orbit orbit-a"></div>
                <div className="orbit orbit-b"></div>
                <div className="orbit-core">RF</div>
              </div>
            </section>

            {/* METRICS */}
            <div className="metric-grid">
              <div className="metric-card">
                <span>Repositories Analyzed</span>
                <strong>{repositories.length}</strong>
                <small>Ingested into Project Knowledge Models</small>
              </div>
              <div className="metric-card">
                <span>Technical Videos</span>
                <strong>{videos.length}</strong>
                <small>Rendered with Remotion 1080p engine</small>
              </div>
              <div className="metric-card">
                <span>Knowledge Transfers</span>
                <strong>{learnerProfile?.demonstrated_transfers?.length ?? 0}</strong>
                <small>Verified concepts applied across repositories</small>
              </div>
            </div>

            {/* 3 ENTRY MODES SHORTCUT ROW */}
            <section className="panel">
              <span className="eyebrow">CHOOSE YOUR LEARNING JOURNEY</span>
              <h3>Three Primary Entry Workspaces</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "14px", marginTop: "14px" }}>
                <div style={{ border: "1px solid #204163", padding: "18px", borderRadius: "12px", background: "#0a1728" }}>
                  <span className="pill info" style={{ marginBottom: "8px" }}>MODE A</span>
                  <h4 style={{ margin: "4px 0 8px" }}>Choose a Domain</h4>
                  <p style={{ fontSize: "12px", color: "#92acc8" }}>Select Machine Learning, Backend, Full-Stack, Cloud, or Security to generate a full 8-stage roadmap.</p>
                  <button className="btn-secondary" style={{ width: "100%", marginTop: "10px" }} onClick={() => setWorkspace("generator")}>
                    Browse Domains →
                  </button>
                </div>
                <div style={{ border: "1px solid #204163", padding: "18px", borderRadius: "12px", background: "#0a1728" }}>
                  <span className="pill success" style={{ marginBottom: "8px" }}>MODE B</span>
                  <h4 style={{ margin: "4px 0 8px" }}>AI Recommendation</h4>
                  <p style={{ fontSize: "12px", color: "#92acc8" }}>The adaptive tutor inspects your demonstrated abilities and recommends your next engineering challenge.</p>
                  <button className="btn-secondary" style={{ width: "100%", marginTop: "10px" }} onClick={handleRecommendProject} disabled={busy}>
                    {busy ? "Recommending..." : "Get AI Recommendation →"}
                  </button>
                </div>
                <div style={{ border: "1px solid #204163", padding: "18px", borderRadius: "12px", background: "#0a1728" }}>
                  <span className="pill warning" style={{ marginBottom: "8px" }}>MODE C</span>
                  <h4 style={{ margin: "4px 0 8px" }}>Reference Repository</h4>
                  <p style={{ fontSize: "12px", color: "#92acc8" }}>Upload an existing repository and generate a new, original project transferring its core architectural patterns.</p>
                  <button className="btn-secondary" style={{ width: "100%", marginTop: "10px" }} onClick={handleGenerateReferenceInspiredProject} disabled={busy || !selectedRepoId}>
                    {busy ? "Generating..." : "Transform Reference Repo →"}
                  </button>
                </div>
              </div>
            </section>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 2: REPOSITORIES (INGESTION & SOURCE EXPLORER)
           ========================================================================= */}
        {workspace === "repositories" && (
          <div className="page-stack">
            {/* INGESTION CONTROLS */}
            <div className="import-grid">
              <div className="panel import-card">
                <span className="eyebrow">LOCAL REPOSITORY INGESTION</span>
                <h2>Analyze Local Repository</h2>
                <p>Provide a relative or absolute path on this machine to parse AST symbols, imports, and relationships.</p>
                <div className="input-row">
                  <input
                    type="text"
                    value={localPathInput}
                    onChange={(e) => setLocalPathInput(e.target.value)}
                    placeholder="e.g. fixtures/sample_project"
                  />
                  <button className="btn-primary" onClick={handleAnalyseLocal} disabled={busy}>
                    {busy ? "Analyzing..." : "Analyze Codebase"}
                  </button>
                </div>
              </div>

              <div className="panel import-card">
                <span className="eyebrow">GIT HOSTING PROVIDER</span>
                <h2>Clone from GitHub</h2>
                <p>Provide a public repository URL to clone and index its Project Knowledge Model.</p>
                <div className="input-row">
                  <input
                    type="text"
                    value={githubUrlInput}
                    onChange={(e) => setGithubUrlInput(e.target.value)}
                    placeholder="https://github.com/org/repo"
                  />
                  <button className="btn-primary" onClick={handleImportGithub} disabled={busy}>
                    {busy ? "Cloning..." : "Clone & Ingest"}
                  </button>
                </div>
              </div>
            </div>

            {/* REPOSITORY 5-STEP WORKFLOW & STATS */}
            {selectedRepo && (
              <section className="panel">
                {/* 5-STEP PIPELINE BANNER */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "10px", marginBottom: "22px", padding: "14px", background: "#05111d", borderRadius: "12px", border: "1px solid #142a42" }}>
                  <div style={{ borderLeft: "3px solid #10b981", paddingLeft: "10px" }}>
                    <small style={{ color: "#10b981", fontWeight: 700, fontSize: "10px", textTransform: "uppercase" }}>Step 1</small>
                    <b style={{ display: "block", fontSize: "12px", color: "#f1f7ff" }}>Add Codebase</b>
                    <span style={{ fontSize: "10px", color: "#64748b" }}>Ingested</span>
                  </div>
                  <div style={{ borderLeft: "3px solid #10b981", paddingLeft: "10px" }}>
                    <small style={{ color: "#10b981", fontWeight: 700, fontSize: "10px", textTransform: "uppercase" }}>Step 2</small>
                    <b style={{ display: "block", fontSize: "12px", color: "#f1f7ff" }}>Analyze PKM</b>
                    <span style={{ fontSize: "10px", color: "#64748b" }}>AST & Evidence</span>
                  </div>
                  <div style={{ borderLeft: "3px solid #38bdf8", paddingLeft: "10px" }}>
                    <small style={{ color: "#38bdf8", fontWeight: 700, fontSize: "10px", textTransform: "uppercase" }}>Step 3</small>
                    <b style={{ display: "block", fontSize: "12px", color: "#f1f7ff" }}>Explore Views</b>
                    <span style={{ fontSize: "10px", color: "#64748b" }}>7 Perspectives</span>
                  </div>
                  <div style={{ borderLeft: "3px solid #f59e0b", paddingLeft: "10px" }}>
                    <small style={{ color: "#f59e0b", fontWeight: 700, fontSize: "10px", textTransform: "uppercase" }}>Step 4</small>
                    <b style={{ display: "block", fontSize: "12px", color: "#f1f7ff" }}>Render Video</b>
                    <span style={{ fontSize: "10px", color: "#64748b" }}>Multi-Scene Remotion</span>
                  </div>
                  <div style={{ borderLeft: "3px solid #a855f7", paddingLeft: "10px" }}>
                    <small style={{ color: "#a855f7", fontWeight: 700, fontSize: "10px", textTransform: "uppercase" }}>Step 5</small>
                    <b style={{ display: "block", fontSize: "12px", color: "#f1f7ff" }}>Watch Explainer</b>
                    <span style={{ fontSize: "10px", color: "#64748b" }}>Captions & Audio</span>
                  </div>
                </div>

                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">SELECTED REPOSITORY OVERVIEW</span>
                    <h3>{selectedRepo.name ?? selectedRepo.repository_id}</h3>
                    <small className="muted">{selectedRepo.source_path ?? "Local storage"} · Revision {selectedRepo.latest_published_revision_id}</small>
                  </div>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                    {videos.some((v) => v.repository_id === selectedRepoId) ? (
                      <button className="btn-watch-video" onClick={() => setPlayingRepoExplainer(!playingRepoExplainer)}>
                        {playingRepoExplainer ? "Hide Explainer ▲" : "▶ Watch Repository Explainer"}
                      </button>
                    ) : (
                      <button className="btn-primary" onClick={handleRenderRepoExplainer} disabled={busy}>
                        {busy ? "Rendering..." : "🎬 Generate Explainer Video"}
                      </button>
                    )}
                    <button className="btn-secondary" onClick={() => setWorkspace("architecture")}>
                      Architecture (7 Views) ☊
                    </button>
                    <button className="btn-secondary" onClick={() => setWorkspace("flows")}>
                      Execution Flows ⚡
                    </button>
                  </div>
                </div>

                {/* INLINE EMBEDDED REPO EXPLAINER THEATER */}
                {playingRepoExplainer && (
                  <div style={{ marginBottom: "24px", padding: "18px", background: "#02070f", borderRadius: "14px", border: "1px solid #1e3852" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                      <b style={{ color: "#38bdf8", fontSize: "16px" }}>Repository Architectural Explainer</b>
                      <span className="pill success">1080p Playable</span>
                    </div>
                    <video
                      controls
                      autoPlay
                      style={{ width: "100%", maxHeight: "500px", borderRadius: "10px", background: "#000", display: "block" }}
                      src={`${API}/api/repositories/${selectedRepoId}/explainer/video`}
                      ref={(el) => {
                        if (el) el.playbackRate = videoPlaybackRate;
                      }}
                    >
                      <track kind="subtitles" src={`${API}/api/repositories/${selectedRepoId}/explainer/captions`} srcLang="en" label="English" default />
                    </video>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "14px", flexWrap: "wrap", gap: "10px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <span style={{ fontSize: "12px", color: "#94a3b8" }}>Speed:</span>
                        {[0.75, 1.0, 1.25, 1.5, 2.0].map((rate) => (
                          <button
                            key={rate}
                            className={`tag ${videoPlaybackRate === rate ? "pill info" : ""}`}
                            style={{ fontSize: "11px", padding: "4px 8px", cursor: "pointer" }}
                            onClick={() => setVideoPlaybackRate(rate)}
                          >
                            {rate}x
                          </button>
                        ))}
                      </div>
                      <div style={{ display: "flex", gap: "8px" }}>
                        <button className="btn-secondary" style={{ fontSize: "12px" }} onClick={handleRenderRepoExplainer} disabled={busy}>
                          🔄 Re-render Video
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "12px" }} onClick={() => setWorkspace("videos")}>
                          Open in Video Studio ↗
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="metric-grid compact">
                  <div className="metric-card"><span>Files</span><strong>{overview?.summary?.files ?? files.length}</strong></div>
                  <div className="metric-card"><span>Symbols</span><strong>{overview?.summary?.symbols ?? 0}</strong></div>
                  <div className="metric-card"><span>Relationships</span><strong>{overview?.summary?.relationships ?? 0}</strong></div>
                  <div className="metric-card"><span>Facts</span><strong>{overview?.summary?.facts ?? 0}</strong></div>
                  <div className="metric-card"><span>Evidence</span><strong>{overview?.summary?.evidence ?? 0}</strong></div>
                </div>

                {/* SPLIT FILE LIST & SYNTAX VIEWER */}
                <div className="split-grid" style={{ marginTop: "24px" }}>
                  <div className="file-list">
                    <span className="eyebrow">VERIFIED SOURCE FILES</span>
                    {files.map((f) => (
                      <button
                        key={f.path}
                        className={activeFile?.path === f.path ? "selected" : ""}
                        onClick={() => {
                          setActiveFile(f);
                          if (selectedRepoId) void loadSource(selectedRepoId, f.path);
                        }}
                      >
                        <span>{f.language}</span>
                        <b>{f.path}</b>
                        <small>{f.line_count} lines</small>
                      </button>
                    ))}
                  </div>

                  <div className="source-viewer">
                    <span className="eyebrow">{activeFile?.path ?? "Source View"}</span>
                    <pre>{sourceCode}</pre>
                  </div>
                </div>
              </section>
            )}
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 3: ARCHITECTURE (7 INTERACTIVE PERSPECTIVES)
           ========================================================================= */}
        {workspace === "architecture" && (
          <div className="page-stack">
            {/* VIEW PERSPECTIVE SWITCHER TABS */}
            <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "4px" }}>
              {[
                { type: "high_level_system", label: "1. High-Level System" },
                { type: "module_dependency", label: "2. Module Dependencies" },
                { type: "component_relationships", label: "3. Component Relationships" },
                { type: "api_communication", label: "4. API Communication" },
                { type: "database_interactions", label: "5. Database Interactions" },
                { type: "data_flow", label: "6. Data Flow Lifecycle" },
                { type: "execution_flow", label: "7. Execution Sequence" },
              ].map((tab) => (
                <button
                  key={tab.type}
                  className={`tag ${activeViewType === tab.type ? "pill info" : ""}`}
                  style={{ padding: "8px 14px", fontSize: "12px", cursor: "pointer", border: activeViewType === tab.type ? "1px solid #65d6ff" : "1px solid #1e3852" }}
                  onClick={() => {
                    setActiveViewType(tab.type);
                    setSelectedNode(null);
                    setSelectedEdge(null);
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* TOOLBAR */}
            <div className="graph-toolbar">
              <input
                type="text"
                placeholder="Search component by name, function, role or file..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <select value={subsystemFilter} onChange={(e) => setSubsystemFilter(e.target.value)}>
                <option value="all">All Subsystems</option>
                <option value="gateway">API & Gateway</option>
                <option value="domain">Core Domain Services</option>
                <option value="storage">Storage & Models</option>
                <option value="utility">Utilities</option>
              </select>
              <button className="btn-secondary" onClick={handleRenderRepoExplainer} disabled={busy}>
                Render Video Explainer ▶
              </button>
            </div>

            {/* INTERACTIVE CANVAS & INSPECTOR SPLIT */}
            <div className="split-grid" style={{ gridTemplateColumns: "minmax(0, 2fr) minmax(360px, 1fr)" }}>
              {/* SVG CANVAS */}
              <div className="graph-canvas interactive" style={{ overflow: "auto", background: "#060f1b" }}>
                <svg width="1380" height="740" viewBox="0 0 1380 740">
                  <defs>
                    <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
                    </pattern>
                  </defs>
                  <rect width="100%" height="100%" fill="url(#grid)" />

                  {/* BOUNDARIES */}
                  {activeView?.boundaries?.map((b) => (
                    <g key={b.boundary_id}>
                      <rect
                        x={b.x}
                        y={b.y}
                        width={b.width}
                        height={b.height}
                        rx="14"
                        fill="rgba(14, 34, 58, 0.45)"
                        stroke="#22d3ee"
                        strokeWidth="1.2"
                        strokeDasharray="6 4"
                      />
                      <text x={b.x + 14} y={b.y + 24} fill="#67e8f9" fontSize="12" fontWeight="800" letterSpacing="0.08em">
                        {b.label}
                      </text>
                    </g>
                  ))}

                  {/* EDGES */}
                  {activeView?.relationships?.map((rel) => {
                    const srcNode = activeView.components.find((c: any) => c.id === rel.source);
                    const tgtNode = activeView.components.find((c: any) => c.id === rel.target);
                    if (!srcNode || !tgtNode) return null;
                    const x1 = (srcNode.x ?? 100) + (srcNode.width ?? 200) / 2;
                    const y1 = (srcNode.y ?? 100) + (srcNode.height ?? 80) / 2;
                    const x2 = (tgtNode.x ?? 300) + (tgtNode.width ?? 200) / 2;
                    const y2 = (tgtNode.y ?? 100) + (tgtNode.height ?? 80) / 2;
                    const isSelected = selectedEdge?.id === rel.id;

                    return (
                      <g key={rel.id} style={{ cursor: "pointer" }} onClick={() => setSelectedEdge(rel)}>
                        <line
                          x1={x1}
                          y1={y1}
                          x2={x2}
                          y2={y2}
                          stroke={isSelected ? "#38bdf8" : "#0284c7"}
                          strokeWidth={isSelected ? 3 : 1.8}
                          strokeDasharray={rel.status === "inferred" ? "4 4" : "none"}
                        />
                        <circle cx={(x1 + x2) / 2} cy={(y1 + y2) / 2} r="5" fill="#38bdf8" />
                        <text x={(x1 + x2) / 2 + 8} y={(y1 + y2) / 2 - 4} fill="#7dd3fc" fontSize="10" fontFamily="monospace">
                          {rel.type}
                        </text>
                      </g>
                    );
                  })}

                  {/* NODES */}
                  {activeView?.components?.map((comp: any) => {
                    const matchesSearch = !searchTerm || comp.label?.toLowerCase().includes(searchTerm.toLowerCase()) || comp.role?.toLowerCase().includes(searchTerm.toLowerCase());
                    const matchesSubsystem = subsystemFilter === "all" || comp.subsystem === subsystemFilter;
                    const opacity = matchesSearch && matchesSubsystem ? 1.0 : 0.25;
                    const isSelected = selectedNode?.id === comp.id;

                    return (
                      <g
                        key={comp.id}
                        transform={`translate(${comp.x ?? 100}, ${comp.y ?? 100})`}
                        style={{ cursor: "pointer", opacity }}
                        onClick={() => {
                          setSelectedNode(comp);
                          setSelectedEdge(null);
                        }}
                      >
                        <rect
                          width={comp.width ?? 220}
                          height={comp.height ?? 80}
                          rx="10"
                          fill={isSelected ? "#133e5c" : "rgba(15, 23, 42, 0.85)"}
                          stroke={isSelected ? "#38bdf8" : "#22d3ee"}
                          strokeWidth={isSelected ? 2.5 : 1.2}
                        />
                        <text x="14" y="22" fill="#38bdf8" fontSize="9" fontWeight="800" style={{ textTransform: "uppercase" }}>
                          {comp.role ?? comp.kind}
                        </text>
                        <text x="14" y="42" fill="#f8fafc" fontSize="13" fontWeight="700">
                          {comp.label}
                        </text>
                        <text x="14" y="60" fill="#94a3b8" fontSize="10" fontFamily="monospace">
                          {comp.file_path ?? ""}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>

              {/* INSPECTOR DRAWER */}
              <div className="panel" style={{ height: "100%", overflowY: "auto" }}>
                {selectedNode ? (
                  <div>
                    <span className="eyebrow">NODE INSPECTOR</span>
                    <h3>{selectedNode.label}</h3>
                    <div style={{ display: "flex", gap: "6px", margin: "8px 0 16px" }}>
                      <span className="pill info">{selectedNode.role ?? selectedNode.kind}</span>
                      {selectedNode.confidence && <span className="pill success">Confidence {(selectedNode.confidence * 100).toFixed(0)}%</span>}
                    </div>

                    <div style={{ display: "grid", gap: "10px", fontSize: "12px" }}>
                      <div>
                        <b style={{ color: "#38bdf8" }}>What it does:</b>
                        <p style={{ margin: "4px 0" }}>{selectedNode.what_it_does ?? selectedNode.summary ?? "N/A"}</p>
                      </div>
                      <div>
                        <b style={{ color: "#38bdf8" }}>Why it exists:</b>
                        <p style={{ margin: "4px 0" }}>{selectedNode.why_it_exists ?? "Fulfills layer contract."}</p>
                      </div>
                      <div>
                        <b style={{ color: "#38bdf8" }}>Call Hierarchy:</b>
                        <p style={{ margin: "4px 0" }}>
                          <b>Callers:</b> {selectedNode.who_calls_it?.join(", ") || "None (Boundary)"}
                          <br />
                          <b>Callees:</b> {selectedNode.what_it_calls?.join(", ") || "None (Terminal)"}
                        </p>
                      </div>
                      <div>
                        <b style={{ color: "#38bdf8" }}>Source Reference:</b>
                        <p style={{ margin: "4px 0", fontFamily: "monospace" }}>
                          {selectedNode.file_path} {selectedNode.line_range ? `(Lines ${selectedNode.line_range[0]}-${selectedNode.line_range[1]})` : ""}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : selectedEdge ? (
                  <div>
                    <span className="eyebrow">EDGE INSPECTOR</span>
                    <h3>{selectedEdge.source_label} → {selectedEdge.target_label}</h3>
                    <span className={`pill ${selectedEdge.status === "verified_static" ? "success" : "warning"}`} style={{ margin: "8px 0" }}>
                      {selectedEdge.status ?? "verified_static"}
                    </span>
                    <p style={{ fontSize: "13px" }}>{selectedEdge.why_it_exists}</p>
                    <p style={{ fontSize: "11px", fontFamily: "monospace", color: "#64748b" }}>Type: {selectedEdge.type}</p>
                  </div>
                ) : (
                  <div className="empty">
                    <div className="empty-icon">☊</div>
                    <b>Interactive Inspector</b>
                    <p>Click any node or relationship on the canvas to inspect its role, callers, data flow, and AST evidence.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 4: EXECUTION FLOWS
           ========================================================================= */}
        {workspace === "flows" && (
          <div className="page-stack">
            <section className="panel">
              <span className="eyebrow">DETERMINISTIC CAUSAL RECONSTRUCTION</span>
              <h3>End-to-End Execution Sequences</h3>
              <p>Traces real execution journeys across layer boundaries, identifying input transformations and return packets.</p>

              {flows.length === 0 ? (
                <div className="empty">
                  <div className="empty-icon">⇄</div>
                  <b>No Execution Flows Discovered</b>
                  <p>Analyze a repository with entry routes to trace execution flows.</p>
                </div>
              ) : (
                flows.map((flow) => (
                  <div key={flow.path_id} style={{ border: "1px solid #1e3852", borderRadius: "12px", padding: "20px", marginTop: "16px", background: "#0a1727" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h4>{flow.name}</h4>
                      <span className="pill info">{flow.steps.length} Sequential Steps</span>
                    </div>
                    <p style={{ fontSize: "13px", color: "#94a3b8" }}>{flow.description}</p>

                    {/* STEPPING LIST */}
                    <div style={{ display: "grid", gap: "10px", marginTop: "16px" }}>
                      {flow.steps.map((st: any, sIdx: number) => (
                        <div
                          key={st.step_id ?? sIdx}
                          style={{ display: "grid", gridTemplateColumns: "36px 140px 1fr 140px", alignItems: "center", gap: "12px", padding: "10px 14px", background: "#07121f", borderRadius: "8px", border: "1px solid #14273c" }}
                        >
                          <span style={{ width: "24px", height: "24px", borderRadius: "50%", background: "#0284c7", color: "#fff", display: "grid", placeItems: "center", fontSize: "11px", fontWeight: "bold" }}>
                            {st.step_number ?? sIdx + 1}
                          </span>
                          <span className="pill warning">{st.operation_type ?? st.operation}</span>
                          <div>
                            <b style={{ fontSize: "13px" }}>{st.symbol_name ?? st.symbol}</b>
                            <small style={{ display: "block", color: "#64748b" }}>{st.summary_text ?? st.summary}</small>
                          </div>
                          <span style={{ fontSize: "10px", fontFamily: "monospace", color: "#94a3b8", textAlign: "right" }}>
                            {st.file_path ?? ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </section>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 5: VIDEO STUDIO
           ========================================================================= */}
        {workspace === "videos" && (
          <div className="page-stack">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">TECHNICAL VIDEO ENGINE (REMOTION 1080P)</span>
                  <h3>Generated Technical Video Explainers</h3>
                </div>
                <button className="btn-primary" onClick={handleRenderRepoExplainer} disabled={busy || !selectedRepoId}>
                  {busy ? "Rendering..." : "Generate Repository Explainer ▶"}
                </button>
              </div>

              {videos.length === 0 ? (
                <div className="empty">
                  <div className="empty-icon">▶</div>
                  <b>No Technical Videos Generated</b>
                  <p>Generate a full repository explainer video or stage teaching video using the Remotion engine.</p>
                </div>
              ) : (
                <div className="split-grid" style={{ gridTemplateColumns: "minmax(280px, 1fr) minmax(0, 2fr)" }}>
                  {/* VIDEO LIST */}
                  <div className="video-library">
                    {videos.map((vid) => (
                      <button
                        key={vid.video_id}
                        className={`video-row ${activeVideo?.video_id === vid.video_id ? "selected" : ""}`}
                        onClick={() => setActiveVideo(vid)}
                      >
                        <span className="video-thumb">▶</span>
                        <span>
                          <b>{vid.title}</b>
                          <small>{vid.topic} · {Math.round((vid.manifest.actual_duration_ms ?? 0) / 1000)}s</small>
                        </span>
                        <span className={`pill ${vid.status === "playable" ? "success" : "info"}`}>{vid.status}</span>
                      </button>
                    ))}
                  </div>

                  {/* ACTIVE PLAYER & TRANSCRIPT */}
                  <div>
                    {activeVideo?.manifest?.video_path ? (
                      <div className="player-panel">
                        <video controls autoPlay style={{ width: "100%", borderRadius: "12px", background: "#000" }} src={`${API}/api/videos/${activeVideo.video_id}/stream`}>
                          <track kind="subtitles" src={`${API}/api/videos/${activeVideo.video_id}/captions`} srcLang="en" label="English" default />
                        </video>
                        <div className="chapter-row" style={{ marginTop: "12px", display: "flex", gap: "6px", flexWrap: "wrap" }}>
                          {activeVideo.manifest.chapters?.map((ch) => (
                            <span key={ch.title} className="tag">{ch.title}</span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="empty"><p>Select a video from the library to play.</p></div>
                    )}
                  </div>
                </div>
              )}
            </section>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 6: LEARNING WORKSPACE
           ========================================================================= */}
        {workspace === "learning" && (
          <div className="page-stack">
            {activeProject ? (
              <div>
                {/* PROJECT BANNER */}
                <div className="lesson-banner" style={{ marginBottom: "20px" }}>
                  <div>
                    <span className="eyebrow">{activeProject.entry_mode?.toUpperCase() ?? "PROJECT WORKSPACE"}</span>
                    <h2>{activeProject.title}</h2>
                    <p>{activeProject.description}</p>
                    <div style={{ display: "flex", gap: "8px", marginTop: "10px" }}>
                      <span className="pill info">Domain: {activeProject.domain ?? "Software Engineering"}</span>
                      <span className="pill success">{activeProject.completed_tasks} of {activeProject.total_tasks} Tasks Complete</span>
                    </div>
                  </div>
                </div>

                {/* STAGE ACCORDIONS */}
                <div className="split-grid" style={{ gridTemplateColumns: "minmax(0, 2fr) minmax(320px, 1fr)" }}>
                  <div style={{ display: "grid", gap: "16px" }}>
                    {activeProject.stages.map((stage) => {
                      const isExpanded = expandedStageId === stage.stage_id;
                      return (
                        <div key={stage.stage_id} style={{ border: "1px solid #1e3852", borderRadius: "14px", background: "#091728", overflow: "hidden" }}>
                          <div
                            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "18px 22px", cursor: "pointer", background: isExpanded ? "#102842" : "#0a1727" }}
                            onClick={() => setExpandedStageId(isExpanded ? "" : stage.stage_id)}
                          >
                            <div>
                              <span className="pill info" style={{ marginRight: "8px" }}>Stage {stage.order}</span>
                              <b style={{ fontSize: "16px" }}>{stage.title}</b>
                              <small style={{ display: "block", color: "#64748b", marginTop: "4px" }}>{stage.description}</small>
                            </div>
                            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                              <span className={`pill ${stage.status === "completed" ? "success" : stage.status === "in_progress" ? "warning" : "muted"}`}>
                                {stage.status}
                              </span>
                              <span>{isExpanded ? "▲" : "▼"}</span>
                            </div>
                          </div>

                          {isExpanded && (
                            <div style={{ padding: "22px", borderTop: "1px solid #1e3852" }}>
                              {/* STAGE VIDEO WORKFLOW & MANDATORY UX */}
                              <div style={{ marginBottom: "20px", padding: "16px 20px", background: "#05111d", borderRadius: "12px", border: "1px solid #163653" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
                                  <div>
                                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                      <b style={{ color: "#38bdf8", fontSize: "15px" }}>Stage Video Explainer</b>
                                      {stage.video_path ? (
                                        <span className="pill success">Ready to Watch</span>
                                      ) : busy ? (
                                        <span className="pill warning">Generating...</span>
                                      ) : (
                                        <span className="pill muted">Not Generated</span>
                                      )}
                                    </div>
                                    <small style={{ display: "block", color: "#94a3b8", marginTop: "4px" }}>
                                      {stage.purpose || "Evidence-grounded technical walkthrough teaching contract boundaries and invariant enforcement."}
                                    </small>
                                  </div>

                                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                                    {stage.video_path ? (
                                      <button
                                        className="btn-watch-video"
                                        onClick={() => setPlayingStageVideoId(playingStageVideoId === stage.stage_id ? null : stage.stage_id)}
                                      >
                                        {playingStageVideoId === stage.stage_id ? "Hide Video ▲" : "▶ Watch Current Step Video"}
                                        {stage.video_duration_seconds ? ` (${Math.round(stage.video_duration_seconds)}s)` : ""}
                                      </button>
                                    ) : (
                                      <button className="btn-primary" onClick={() => handleRenderStageVideo(stage.stage_id)} disabled={busy}>
                                        {busy ? "Rendering..." : "🎬 Generate Stage Video"}
                                      </button>
                                    )}
                                    {stage.video_path && (
                                      <button className="btn-secondary" style={{ fontSize: "12px", padding: "8px 12px" }} onClick={() => handleRenderStageVideo(stage.stage_id)} disabled={busy}>
                                        🔄 Re-render
                                      </button>
                                    )}
                                  </div>
                                </div>

                                {/* EMBEDDED STAGE VIDEO THEATER */}
                                {playingStageVideoId === stage.stage_id && stage.video_path && (
                                  <div style={{ marginTop: "16px", padding: "16px", background: "#02070f", borderRadius: "12px", border: "1px solid #204163" }}>
                                    <video
                                      controls
                                      autoPlay
                                      style={{ width: "100%", maxHeight: "440px", borderRadius: "8px", background: "#000", display: "block" }}
                                      src={`${API}/api/learning-projects/${activeProject.project_id}/stages/${stage.stage_id}/video`}
                                      ref={(el) => {
                                        if (el) el.playbackRate = videoPlaybackRate;
                                      }}
                                    >
                                      <track kind="subtitles" src={`${API}/api/learning-projects/${activeProject.project_id}/stages/${stage.stage_id}/captions`} srcLang="en" label="English" default />
                                    </video>

                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "14px", flexWrap: "wrap", gap: "10px" }}>
                                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                        <span style={{ fontSize: "12px", color: "#94a3b8" }}>Playback Speed:</span>
                                        {[0.75, 1.0, 1.25, 1.5, 2.0].map((rate) => (
                                          <button
                                            key={rate}
                                            className={`tag ${videoPlaybackRate === rate ? "pill info" : ""}`}
                                            style={{ fontSize: "11px", padding: "4px 8px", cursor: "pointer" }}
                                            onClick={() => setVideoPlaybackRate(rate)}
                                          >
                                            {rate}x
                                          </button>
                                        ))}
                                      </div>
                                      <div style={{ fontSize: "12px", color: "#94a3b8" }}>
                                        Target Milestone: <span style={{ color: "#38bdf8", fontWeight: 700 }}>{stage.primary_concept}</span>
                                      </div>
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* TASKS */}
                              {stage.tasks.map((task) => (
                                <div key={task.task_id} style={{ border: "1px solid #18334f", borderRadius: "10px", padding: "18px", marginTop: "12px", background: "#071321" }}>
                                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <h4 style={{ margin: 0 }}>{task.title}</h4>
                                    <span className="pill info">[{task.presentation_level?.toUpperCase()}]</span>
                                  </div>
                                  <p style={{ fontSize: "13px", color: "#94a3b8", margin: "8px 0" }}>{task.instructions}</p>

                                  {/* HINTS */}
                                  <div style={{ margin: "14px 0" }}>
                                    <button className="btn-secondary" style={{ fontSize: "11px", padding: "6px 10px" }} onClick={() => handleRevealHint(task.task_id)}>
                                      Request Progressive Hint ({task.hints_used}/{task.hints.length})
                                    </button>
                                    {task.hints.slice(0, task.hints_used).map((h, hIdx) => (
                                      <p key={hIdx} style={{ fontSize: "12px", color: "#fbbf24", margin: "6px 0 0" }}>
                                        💡 Hint {h.level}: {h.hint}
                                      </p>
                                    ))}
                                  </div>

                                  {/* SOLUTION SUBMITTER */}
                                  <div style={{ marginTop: "14px" }}>
                                    <textarea
                                      style={{ width: "100%", background: "#040b14", border: "1px solid #1e3852", borderRadius: "8px", color: "#fff", padding: "10px", fontFamily: "monospace", fontSize: "12px" }}
                                      rows={4}
                                      placeholder="Write your implementation or analysis here..."
                                      value={solutionInputs[task.task_id] ?? ""}
                                      onChange={(e) => setSolutionInputs({ ...solutionInputs, [task.task_id]: e.target.value })}
                                    />
                                    <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                                      <button className="btn-primary" onClick={() => handleSubmitSolution(task.task_id)} disabled={busy}>
                                        Submit Solution
                                      </button>
                                      <button className="btn-secondary" onClick={() => handleTriggerTutorTakeover(task)} disabled={busy}>
                                        Tutor Takeover ⚡
                                      </button>
                                    </div>
                                    {task.evaluation_feedback && (
                                      <p style={{ fontSize: "12px", color: task.status === "completed" ? "#4ade80" : "#f87171", marginTop: "8px" }}>
                                        {task.evaluation_feedback}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* SIDEBAR: DQN STATE & CONCEPT MASTERY */}
                  <div>
                    <div className="panel" style={{ marginBottom: "16px" }}>
                      <span className="eyebrow">DQN ADAPTIVE MENTOR</span>
                      <h3>Active Guidance State</h3>
                      <div className="state-grid" style={{ margin: "12px 0" }}>
                        <div><small>Independence</small><b>{learnerProfile?.dqn_features?.independence_score ?? 0.8}</b></div>
                        <div><small>Correctness</small><b>{((learnerProfile?.dqn_features?.correctness_ema ?? 0.8) * 100).toFixed(0)}%</b></div>
                      </div>
                      <p className="muted">
                        DQN Recommendation: <b>{learnerProfile?.dqn_decision?.action_id ?? "continue_independent_attempt"}</b>
                      </p>
                    </div>

                    <div className="panel">
                      <span className="eyebrow">CONCEPT MASTERY</span>
                      <div style={{ display: "grid", gap: "8px", marginTop: "10px" }}>
                        {Object.entries(learnerProfile?.concept_mastery ?? {}).map(([c, val]) => (
                          <div key={c}>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8" }}>
                              <span>{c}</span>
                              <b>{(val * 100).toFixed(0)}%</b>
                            </div>
                            <div style={{ height: "5px", background: "#0a1727", borderRadius: "999px", overflow: "hidden", marginTop: "3px" }}>
                              <div style={{ height: "100%", width: `${val * 100}%`, background: "#38bdf8" }} />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="panel empty">
                <div className="empty-icon">🎓</div>
                <b>No Active Learning Project</b>
                <p>Generate a project using Mode A (Domain), Mode B (AI Recommended), or Mode C (Reference Repo).</p>
                <button className="btn-primary" onClick={() => setWorkspace("generator")}>Open Project Generator</button>
              </div>
            )}
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 7: PROJECT GENERATOR (3 ENTRY MODES)
           ========================================================================= */}
        {workspace === "generator" && (
          <div className="page-stack">
            {/* MODE A: CHOOSE A DOMAIN */}
            <section className="panel">
              <span className="eyebrow">MODE A</span>
              <h3>Choose a Software Engineering Domain</h3>
              <p>Select a domain to generate an authentic 8-stage software project roadmap with dedicated videos and tasks.</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "12px", marginTop: "16px" }}>
                {[
                  "Machine Learning",
                  "Backend Development",
                  "Full-Stack Development",
                  "Deep Learning",
                  "Cybersecurity",
                  "Cloud Computing",
                  "Computer Vision",
                  "Data Science",
                  "Web Development",
                  "DevOps",
                  "Data Engineering",
                ].map((d) => (
                  <div key={d} style={{ border: "1px solid #1e3852", borderRadius: "10px", padding: "14px", background: "#081525" }}>
                    <b style={{ display: "block", fontSize: "14px", color: "#38bdf8" }}>{d}</b>
                    <small style={{ color: "#64748b", display: "block", margin: "4px 0 12px" }}>8 Engineering Stages</small>
                    <button className="btn-primary" style={{ width: "100%", fontSize: "12px" }} onClick={() => handleGenerateDomainProject(d)} disabled={busy}>
                      Generate Project →
                    </button>
                  </div>
                ))}
              </div>
            </section>

            {/* MODE B: AI RECOMMENDED */}
            <section className="panel">
              <span className="eyebrow">MODE B</span>
              <h3>Personalized AI Project Recommendation</h3>
              <p>The tutor inspects your strengths and knowledge gaps to formulate your next learning challenge.</p>
              <button className="btn-primary" onClick={handleRecommendProject} disabled={busy}>
                {busy ? "Evaluating Profile..." : "Recommend & Generate Project ⚡"}
              </button>
            </section>

            {/* MODE C: REFERENCE REPO TO NEW PROJECT */}
            <section className="panel">
              <span className="eyebrow">MODE C</span>
              <h3>Transform Reference Repository into an Original Project</h3>
              <p>Analyze a reference repository and generate a new, original project transferring its architecture without copying code.</p>
              <p className="muted">Selected Reference Repo: <b>{selectedRepo?.name ?? selectedRepoId ?? "None"}</b></p>
              <button className="btn-primary" onClick={handleGenerateReferenceInspiredProject} disabled={busy || !selectedRepoId}>
                {busy ? "Analyzing Patterns..." : "Generate Inspired Original Project →"}
              </button>
            </section>
          </div>
        )}

        {/* =========================================================================
            WORKSPACE 8: LEARNER PROFILE
           ========================================================================= */}
        {workspace === "profile" && (
          <div className="page-stack">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">CROSS-PROJECT PERSISTENCE</span>
                  <h3>Learner Profile: {learnerId}</h3>
                </div>
                <span className="pill success">{learnerProfile?.projects_enrolled?.length ?? 0} Projects Enrolled</span>
              </div>

              <div className="metric-grid">
                <div className="metric-card">
                  <span>Independence Score</span>
                  <strong>{learnerProfile?.dqn_features?.independence_score ?? 0.8}</strong>
                  <small>Calculated from hints and error rates</small>
                </div>
                <div className="metric-card">
                  <span>Demonstrated Transfers</span>
                  <strong>{learnerProfile?.demonstrated_transfers?.length ?? 0}</strong>
                  <small>Concepts proven across multiple codebases</small>
                </div>
                <div className="metric-card">
                  <span>Tutor Takeovers Used</span>
                  <strong>{learnerProfile?.tutor_takeovers_count ?? 0}</strong>
                  <small>Guided demonstrations completed</small>
                </div>
              </div>

              <div style={{ marginTop: "24px" }}>
                <span className="eyebrow">DEMONSTRATED CROSS-PROJECT TRANSFERS</span>
                {learnerProfile?.demonstrated_transfers && learnerProfile.demonstrated_transfers.length > 0 ? (
                  <div style={{ display: "grid", gap: "8px", marginTop: "8px" }}>
                    {learnerProfile.demonstrated_transfers.map((t: any, idx: number) => (
                      <div key={idx} style={{ padding: "10px 14px", background: "#0a1b2d", borderRadius: "8px", border: "1px solid #163653" }}>
                        <span className="pill success" style={{ marginRight: "8px" }}>Certified</span>
                        <b>{t.concept ?? t}</b>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted" style={{ marginTop: "8px" }}>Complete tasks in two distinct repositories to certify cross-project knowledge transfer.</p>
                )}
              </div>
            </section>
          </div>
        )}
      </main>

      {/* TUTOR TAKEOVER MODAL */}
      {activeTakeoverTask && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)", display: "grid", placeItems: "center", zIndex: 9999, padding: "20px" }}>
          <div style={{ background: "#0a1727", border: "1px solid #38bdf8", borderRadius: "16px", padding: "28px", maxWidth: "680px", width: "100%", maxHeight: "85vh", overflowY: "auto" }}>
            <span className="eyebrow">TUTOR TAKEOVER DEMONSTRATION</span>
            <h3 style={{ margin: "8px 0" }}>{activeTakeoverTask.title}</h3>

            <div style={{ margin: "16px 0", padding: "14px", background: "#06101c", borderRadius: "10px" }}>
              <b style={{ color: "#38bdf8" }}>Step-by-Step Walkthrough:</b>
              <ul style={{ margin: "8px 0", paddingLeft: "20px", fontSize: "13px", lineHeight: "1.6" }}>
                {activeTakeoverTask.tutor_demonstration?.demonstration_walkthrough?.map((st: string, idx: number) => (
                  <li key={idx}>{st}</li>
                )) ?? <li>Demonstrating task execution...</li>}
              </ul>
            </div>

            <div style={{ margin: "14px 0", fontSize: "12px", color: "#94a3b8" }}>
              <b style={{ color: "#38bdf8" }}>Verified vs Inferred:</b>
              <p style={{ margin: "4px 0" }}>{activeTakeoverTask.tutor_demonstration?.verified_vs_inferred ?? "Verified by AST parser."}</p>
            </div>

            <div style={{ margin: "14px 0", padding: "12px", background: "#172b3f", borderRadius: "8px" }}>
              <b style={{ color: "#fbbf24" }}>Follow-up Challenge:</b>
              <p style={{ margin: "4px 0", fontSize: "13px" }}>
                {activeTakeoverTask.follow_up_challenge?.challenge ?? "Explain the architectural invariant preserved by this implementation."}
              </p>
            </div>

            <button className="btn-secondary" style={{ width: "100%", marginTop: "12px" }} onClick={() => setActiveTakeoverTask(null)}>
              Close Demonstration
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
