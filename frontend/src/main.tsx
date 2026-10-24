import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Health = { status: string; service: string; version: string };

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("http://127.0.0.1:8000/health")
      .then((res) => res.json())
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);
  return (
    <main className="shell">
      <header><span className="eyebrow">REPOFLOW AI</span><h1>Understand the codebase. Learn the system.</h1><p>Source-grounded lessons from real repositories.</p></header>
      <section className="card"><h2>System status</h2><p className={health ? "ok" : "muted"}>{health ? `${health.service} ${health.version} is ${health.status}.` : error ?? "Connecting to the local backend…"}</p></section>
      <section className="grid"><div className="card"><h2>Repository intelligence</h2><p>Analyse files, symbols, relationships, evidence, and uncertainty.</p></div><div className="card"><h2>Learning journey</h2><p>Watch, question, practise, and unlock progress by demonstrating understanding.</p></div></section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
