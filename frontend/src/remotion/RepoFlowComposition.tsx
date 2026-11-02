import React from "react";
import {
  Audio,
  interpolate,
  Series,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type {
  RepoFlowCompositionProps,
  SemanticSceneProps,
  VisualEdge,
  VisualNode,
} from "./types";

interface SceneRendererProps {
  scene: SemanticSceneProps;
  sceneIndex: number;
  totalScenes: number;
  durationInFrames: number;
}

export const SemanticSceneRenderer: React.FC<SceneRendererProps> = ({
  scene,
  sceneIndex,
  totalScenes,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = Math.min(1, Math.max(0, frame / Math.max(1, durationInFrames - 1)));
  const entranceOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });
  const entranceScale = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.8 },
  });

  // Calculate layout for architecture nodes if x, y not provided
  const nodes = scene.visual_nodes || [];
  const edges = scene.visual_edges || [];

  const nodeMap = React.useMemo(() => {
    const map = new Map<string, { x: number; y: number; width: number; height: number; node: VisualNode }>();
    const nodeWidth = 240;
    const nodeHeight = 90;
    const startX = 60;
    const startY = 70;
    const gapX = 50;
    const gapY = 50;

    nodes.forEach((n, idx) => {
      let x = n.x ?? (startX + (idx % 3) * (nodeWidth + gapX));
      let y = n.y ?? (startY + Math.floor(idx / 3) * (nodeHeight + gapY));
      map.set(n.id, { x, y, width: nodeWidth, height: nodeHeight, node: n });
    });
    return map;
  }, [nodes]);

  // Normalize visual type
  const vType = (scene.visual_type || scene.kind || "summary").toLowerCase();
  const isCode = vType.includes("code");
  const isDataFlow = vType.includes("data");
  const isFlow = vType.includes("flow") && !isDataFlow;
  const isArch = vType.includes("arch") || vType.includes("system") || vType.includes("component");

  // Code walkthrough active line calculation
  const codeLines = (scene.code_excerpt || "").split("\n").slice(0, 14);
  const startLine = scene.highlight_line || scene.highlight_lines?.[0] || 1;
  const activeLineIndex = Math.min(
    codeLines.length - 1,
    Math.floor(progress * Math.max(1, codeLines.length))
  );

  return (
    <div
      style={{
        width: 1920,
        height: 1080,
        background: "radial-gradient(circle at 50% 15%, #0f1f38 0%, #080d1a 65%, #04070f 100%)",
        color: "#f8fafc",
        fontFamily: "'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif",
        padding: "50px 70px",
        boxSizing: "border-box",
        position: "relative",
        overflow: "hidden",
        opacity: entranceOpacity,
      }}
    >
      {/* Ambient background glows */}
      <div
        style={{
          position: "absolute",
          top: -150,
          right: -100,
          width: 700,
          height: 700,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(0, 245, 255, 0.12) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: -150,
          left: -100,
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(168, 85, 247, 0.1) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Top Navigation Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid rgba(56, 189, 248, 0.2)",
          paddingBottom: 16,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span
              style={{
                color: "#00f5ff",
                fontSize: 14,
                fontWeight: 800,
                letterSpacing: 2,
                textTransform: "uppercase",
                background: "rgba(0, 245, 255, 0.1)",
                padding: "3px 10px",
                borderRadius: 6,
                border: "1px solid rgba(0, 245, 255, 0.3)",
              }}
            >
              REPOFLOW AI • {(scene.visual_type || scene.kind || "ARCHITECTURE").toUpperCase()}
            </span>
            <span
              style={{
                backgroundColor: "rgba(30, 41, 59, 0.8)",
                color: "#94a3b8",
                fontSize: 13,
                fontWeight: 600,
                padding: "3px 12px",
                borderRadius: 12,
                border: "1px solid rgba(148, 163, 184, 0.2)",
              }}
            >
              Scene {sceneIndex + 1} of {totalScenes}
            </span>
          </div>
          <h1
            style={{
              fontSize: 36,
              margin: "8px 0 0 0",
              color: "#ffffff",
              fontWeight: 800,
              letterSpacing: "-0.5px",
            }}
          >
            {scene.title}
          </h1>
        </div>

        {/* Source Ref Pill */}
        <div
          style={{
            background: "rgba(15, 23, 42, 0.8)",
            padding: "8px 18px",
            borderRadius: 10,
            border: "1px solid rgba(56, 189, 248, 0.25)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#10b981", boxShadow: "0 0 8px #10b981" }} />
          <span style={{ fontSize: 14, color: "#cbd5e1", fontWeight: 600 }}>
            {scene.source_refs?.[0] || "Verified Static PKM"}
          </span>
        </div>
      </div>

      {/* Main Body Grid */}
      <div style={{ display: "flex", marginTop: 26, gap: 36, height: 750 }}>
        {/* Left Side: Educational Takeaway, Invariants & Causal Reasoning */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            {/* Takeaway Card */}
            {scene.takeaway && (
              <div
                style={{
                  background: "linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(15, 23, 42, 0.8) 100%)",
                  borderLeft: "5px solid #00f5ff",
                  padding: "20px 24px",
                  borderRadius: "0 14px 14px 0",
                  marginBottom: 20,
                  borderTop: "1px solid rgba(56, 189, 248, 0.2)",
                  borderRight: "1px solid rgba(56, 189, 248, 0.2)",
                  borderBottom: "1px solid rgba(56, 189, 248, 0.2)",
                  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.35)",
                }}
              >
                <div style={{ color: "#00f5ff", fontSize: 13, fontWeight: 800, letterSpacing: 1.5 }}>
                  ARCHITECTURAL PRINCIPLE
                </div>
                <div style={{ color: "#f8fafc", fontSize: 20, fontWeight: 600, marginTop: 8, lineHeight: 1.45 }}>
                  {scene.takeaway}
                </div>
              </div>
            )}

            {/* Invariants / Scope Checklist */}
            {scene.invariants && scene.invariants.length > 0 && (
              <div
                style={{
                  background: "rgba(15, 23, 42, 0.8)",
                  border: "1px solid rgba(56, 189, 248, 0.25)",
                  borderRadius: 14,
                  padding: "18px 22px",
                  marginBottom: 20,
                }}
              >
                <div style={{ color: "#38bdf8", fontSize: 13, fontWeight: 800, letterSpacing: 1 }}>
                  VERIFIED STATIC INVARIANTS
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                  {scene.invariants.map((inv, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                      <span style={{ color: "#10b981", fontSize: 16 }}>✓</span>
                      <span style={{ color: "#e2e8f0", fontSize: 16, lineHeight: 1.4 }}>{inv}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hypothetical Failure Mode Reasoning */}
            {scene.counterfactual && (
              <div
                style={{
                  background: "linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(15, 23, 42, 0.85) 100%)",
                  border: "1px solid rgba(245, 158, 11, 0.35)",
                  borderRadius: 14,
                  padding: "18px 22px",
                  marginBottom: 20,
                  boxShadow: "0 8px 25px rgba(0, 0, 0, 0.3)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span
                    style={{
                      background: "#f59e0b",
                      color: "#000",
                      fontWeight: 800,
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 11,
                      letterSpacing: 1,
                    }}
                  >
                    HYPOTHETICAL
                  </span>
                  <span style={{ color: "#fbbf24", fontSize: 14, fontWeight: 700 }}>
                    BOUNDARY FAILURE MODE
                  </span>
                </div>
                <div style={{ color: "#fef3c7", fontSize: 17, lineHeight: 1.45 }}>
                  {scene.counterfactual.replace("[HYPOTHETICAL]", "").trim()}
                </div>
              </div>
            )}

            {/* Active Learning Checkpoint Teaser */}
            {scene.checkpoint && (
              <div
                style={{
                  background: "rgba(168, 85, 247, 0.12)",
                  border: "1px dashed rgba(168, 85, 247, 0.5)",
                  borderRadius: 14,
                  padding: "16px 20px",
                }}
              >
                <div style={{ color: "#c084fc", fontSize: 13, fontWeight: 800, letterSpacing: 1 }}>
                  ACTIVE LEARNING CHECKPOINT
                </div>
                <div style={{ color: "#f1f5f9", fontSize: 17, marginTop: 6, fontWeight: 500 }}>
                  {scene.checkpoint.question_text}
                </div>
              </div>
            )}
          </div>

          {/* Footer Metadata */}
          <div
            style={{
              paddingTop: 14,
              borderTop: "1px solid rgba(56, 189, 248, 0.2)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 14,
              color: "#64748b",
            }}
          >
            <span>Verified Source Grounding</span>
            <span>1080p @ 30 FPS • Remotion Engine</span>
          </div>
        </div>

        {/* Right Side: High-Fidelity Visual Representations */}
        <div
          style={{
            flex: 1.4,
            background: "rgba(10, 16, 29, 0.85)",
            backdropFilter: "blur(20px)",
            borderRadius: 20,
            border: "1px solid rgba(56, 189, 248, 0.25)",
            padding: 28,
            display: "flex",
            flexDirection: "column",
            position: "relative",
            overflow: "hidden",
            boxShadow: "0 20px 50px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.08)",
          }}
        >
          {/* 1. CODE WALKTHROUGH */}
          {isCode && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
              {/* macOS Style Window Bar */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  borderBottom: "1px solid rgba(56, 189, 248, 0.2)",
                  paddingBottom: 14,
                  marginBottom: 16,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#ff5f56" }} />
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#ffbd2e" }} />
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: "#27c93f" }} />
                  <span style={{ marginLeft: 14, color: "#38bdf8", fontSize: 15, fontFamily: "monospace", fontWeight: 600 }}>
                    {scene.source_refs?.[0] || scene.code_path || "source.py"}
                  </span>
                </div>
                <span
                  style={{
                    background: "rgba(0, 245, 255, 0.15)",
                    border: "1px solid rgba(0, 245, 255, 0.3)",
                    padding: "3px 12px",
                    borderRadius: 8,
                    color: "#00f5ff",
                    fontSize: 13,
                    fontFamily: "monospace",
                  }}
                >
                  Active Line {startLine + activeLineIndex}
                </span>
              </div>

              {/* Code Lines with Animated Tracer */}
              <div
                style={{
                  flex: 1,
                  fontFamily: "'Fira Code', 'JetBrains Mono', 'Consolas', monospace",
                  fontSize: 18,
                  lineHeight: 1.75,
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                }}
              >
                {codeLines.map((line, idx) => {
                  const lineNo = startLine + idx;
                  const isActive = idx === activeLineIndex;
                  return (
                    <div
                      key={idx}
                      style={{
                        display: "flex",
                        padding: "3px 12px",
                        borderRadius: 8,
                        backgroundColor: isActive ? "rgba(14, 165, 233, 0.25)" : "transparent",
                        borderLeft: isActive ? "4px solid #00f5ff" : "4px solid transparent",
                        boxShadow: isActive ? "0 0 20px rgba(0, 245, 255, 0.2)" : "none",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <span
                        style={{
                          width: 45,
                          color: isActive ? "#00f5ff" : "#475569",
                          userSelect: "none",
                          textAlign: "right",
                          paddingRight: 18,
                        }}
                      >
                        {lineNo}
                      </span>
                      <span
                        style={{
                          color: isActive ? "#ffffff" : "#cbd5e1",
                          fontWeight: isActive ? 700 : 400,
                          whiteSpace: "pre",
                        }}
                      >
                        {line}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 2. CRYSTAL-CLEAR DATA-FLOW ANIMATION */}
          {isDataFlow && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "space-between" }}>
              <div>
                <div style={{ color: "#00f5ff", fontSize: 16, fontWeight: 800, letterSpacing: 1.5 }}>
                  DATA TRANSFORMATION PIPELINE
                </div>
                <div style={{ color: "#94a3b8", fontSize: 15, marginTop: 4 }}>
                  Follow parameter transformations across architectural boundaries
                </div>
              </div>

              {/* 5-Stage Visual Pipeline */}
              <div style={{ display: "flex", flexDirection: "column", gap: 16, flex: 1, justifyContent: "center" }}>
                {[
                  { stage: 1, title: "1. Raw Client Payload", role: "INPUT", value: '{ "name": "alice" }', color: "#38bdf8" },
                  { stage: 2, title: "2. Gateway Route Handler", role: "VALIDATION", value: "validate name: str", color: "#818cf8" },
                  { stage: 3, title: "3. Domain Service Call", role: "DELEGATION", value: "get_user(name) -> load_user", color: "#a855f7" },
                  { stage: 4, title: "4. Typed Domain Entity", role: "MODEL", value: "User(name='alice')", color: "#10b981" },
                  { stage: 5, title: "5. Serialized API Response", role: "OUTPUT", value: '{ "user": "alice", "status": 200 }', color: "#00f5ff" },
                ].map((st, sIdx) => {
                  const stageThreshold = sIdx * 0.2;
                  const isActive = progress >= stageThreshold && progress < stageThreshold + 0.25;
                  const isDone = progress >= stageThreshold + 0.25;

                  return (
                    <div
                      key={st.stage}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 16,
                        background: isActive
                          ? "rgba(14, 165, 233, 0.2)"
                          : isDone
                          ? "rgba(15, 23, 42, 0.9)"
                          : "rgba(15, 23, 42, 0.4)",
                        border: isActive
                          ? `2px solid ${st.color}`
                          : isDone
                          ? "1px solid rgba(56, 189, 248, 0.3)"
                          : "1px solid rgba(56, 189, 248, 0.1)",
                        borderRadius: 12,
                        padding: "14px 20px",
                        boxShadow: isActive ? `0 0 25px ${st.color}40` : "none",
                        transform: isActive ? "scale(1.02)" : "scale(1)",
                        transition: "all 0.25s ease",
                      }}
                    >
                      <div
                        style={{
                          width: 34,
                          height: 34,
                          borderRadius: "50%",
                          background: isDone ? "#10b981" : isActive ? st.color : "rgba(30, 41, 59, 0.8)",
                          color: isDone || isActive ? "#000" : "#94a3b8",
                          fontWeight: 800,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 15,
                        }}
                      >
                        {isDone ? "✓" : st.stage}
                      </div>

                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ color: isActive ? "#ffffff" : "#cbd5e1", fontSize: 17, fontWeight: 700 }}>
                            {st.title}
                          </span>
                          <span
                            style={{
                              background: `${st.color}20`,
                              border: `1px solid ${st.color}50`,
                              color: st.color,
                              fontSize: 11,
                              fontWeight: 800,
                              padding: "2px 8px",
                              borderRadius: 6,
                            }}
                          >
                            {st.role}
                          </span>
                        </div>
                        <div style={{ color: isActive ? "#38bdf8" : "#64748b", fontFamily: "monospace", fontSize: 14, marginTop: 4 }}>
                          Data State: {st.value}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 3. EXECUTION FLOW STEPPER */}
          {isFlow && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
              <div style={{ color: "#00f5ff", fontSize: 16, fontWeight: 800, letterSpacing: 1.5, marginBottom: 16 }}>
                CAUSAL EXECUTION STEPPER
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: 1, justifyContent: "center" }}>
                {(scene.execution_steps || scene.flow_steps || []).slice(0, 6).map((step: any, idx: number) => {
                  const total = Math.min(6, (scene.execution_steps || scene.flow_steps || []).length);
                  const activeStepIdx = Math.min(total - 1, Math.floor(progress * total));
                  const isCurrent = idx === activeStepIdx;
                  const isPast = idx < activeStepIdx;

                  return (
                    <div
                      key={step.step_number || idx}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 16,
                        background: isCurrent
                          ? "rgba(14, 165, 233, 0.25)"
                          : isPast
                          ? "rgba(15, 23, 42, 0.9)"
                          : "rgba(15, 23, 42, 0.4)",
                        border: isCurrent ? "2px solid #00f5ff" : "1px solid rgba(56, 189, 248, 0.2)",
                        padding: "14px 20px",
                        borderRadius: 12,
                        boxShadow: isCurrent ? "0 0 25px rgba(0, 245, 255, 0.25)" : "none",
                        transform: isCurrent ? "scale(1.02)" : "scale(1)",
                        transition: "all 0.25s ease",
                      }}
                    >
                      <div
                        style={{
                          background: isCurrent ? "#00f5ff" : isPast ? "#10b981" : "#1e293b",
                          color: isCurrent || isPast ? "#000" : "#94a3b8",
                          fontWeight: 800,
                          borderRadius: "50%",
                          width: 34,
                          height: 34,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 15,
                        }}
                      >
                        {isPast ? "✓" : step.step_number || idx + 1}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ color: isCurrent ? "#ffffff" : isPast ? "#cbd5e1" : "#64748b", fontSize: 17, fontWeight: isCurrent ? 700 : 500 }}>
                          {step.description}
                        </div>
                        <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
                          <span style={{ color: "#38bdf8", fontSize: 12, fontWeight: 700 }}>
                            OP: {(step.operation_type || "CALL").toUpperCase()}
                          </span>
                          {step.source_ref && (
                            <span style={{ color: "#94a3b8", fontSize: 12, fontFamily: "monospace" }}>
                              {step.source_ref}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 4. CONNECTED ARCHITECTURE GRAPH */}
          {isArch && (
            <div style={{ position: "relative", width: "100%", height: "100%" }}>
              <div style={{ color: "#00f5ff", fontSize: 16, fontWeight: 800, letterSpacing: 1.5, marginBottom: 12 }}>
                CONNECTED COMPONENT TOPOLOGY
              </div>
              <svg
                style={{
                  position: "absolute",
                  top: 40,
                  left: 0,
                  width: "100%",
                  height: "90%",
                  pointerEvents: "none",
                }}
              >
                <defs>
                  <marker
                    id="remotion-arrow"
                    viewBox="0 0 10 10"
                    refX="6"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 1 L 8 5 L 0 9 z" fill="#00f5ff" />
                  </marker>
                </defs>

                {/* Animated Connections */}
                {edges.map((edge, idx) => {
                  const source = nodeMap.get(edge.source);
                  const target = nodeMap.get(edge.target);
                  if (!source || !target) return null;

                  const x1 = source.x + source.width;
                  const y1 = source.y + source.height / 2;
                  const x2 = target.x;
                  const y2 = target.y + target.height / 2;

                  const pulseX = x1 + (x2 - x1) * progress;
                  const pulseY = y1 + (y2 - y1) * progress;

                  return (
                    <g key={idx}>
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke="rgba(56, 189, 248, 0.4)"
                        strokeWidth={3}
                        strokeDasharray="6 6"
                        strokeDashoffset={-frame * 2}
                        markerEnd="url(#remotion-arrow)"
                      />
                      <circle cx={pulseX} cy={pulseY} r={7} fill="#00f5ff" filter="drop-shadow(0 0 8px #00f5ff)" />
                    </g>
                  );
                })}
              </svg>

              {/* Render Node Cards */}
              {Array.from(nodeMap.values()).map(({ x, y, width, height, node }, idx) => {
                const nodeVisible = progress >= idx * 0.12;
                return (
                  <div
                    key={node.id}
                    style={{
                      position: "absolute",
                      left: x,
                      top: y + 40,
                      width,
                      height,
                      background: nodeVisible ? "rgba(15, 23, 42, 0.95)" : "rgba(15, 23, 42, 0.4)",
                      border: nodeVisible ? "2px solid #00f5ff" : "1px solid rgba(56, 189, 248, 0.2)",
                      borderRadius: 14,
                      padding: "14px 18px",
                      boxSizing: "border-box",
                      boxShadow: nodeVisible ? "0 8px 25px rgba(0, 245, 255, 0.2)" : "none",
                      transform: nodeVisible ? "scale(1)" : "scale(0.95)",
                      transition: "all 0.3s ease",
                    }}
                  >
                    <div
                      style={{
                        color: "#38bdf8",
                        fontSize: 11,
                        fontWeight: 800,
                        letterSpacing: 1,
                        textTransform: "uppercase",
                      }}
                    >
                      {node.role || node.kind || "COMPONENT"}
                    </div>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: "#ffffff",
                        marginTop: 4,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {node.label}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* 5. SUMMARY & ARCHITECTURAL INVARIANTS */}
          {!isCode && !isDataFlow && !isFlow && !isArch && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center", gap: 24 }}>
              <div style={{ color: "#00f5ff", fontSize: 18, fontWeight: 800, letterSpacing: 1 }}>
                VERIFIED ARCHITECTURAL BOUNDARIES
              </div>
              <div
                style={{
                  background: "rgba(15, 23, 42, 0.9)",
                  border: "1px solid rgba(56, 189, 248, 0.3)",
                  borderRadius: 14,
                  padding: 24,
                }}
              >
                <div style={{ color: "#38bdf8", fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                  SYSTEM INVARIANTS
                </div>
                <p style={{ color: "#e2e8f0", fontSize: 17, lineHeight: 1.6, margin: 0 }}>
                  Static syntax, symbol tables, and AST imports establish deterministic call sequences and in-memory data structures across all analyzed files.
                </p>
              </div>

              {scene.limitations && scene.limitations.length > 0 && (
                <div
                  style={{
                    background: "rgba(245, 158, 11, 0.1)",
                    border: "1px solid rgba(245, 158, 11, 0.3)",
                    borderRadius: 14,
                    padding: 24,
                  }}
                >
                  <div style={{ color: "#fbbf24", fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                    DISCLOSED RUNTIME LIMITATIONS
                  </div>
                  {scene.limitations.map((lim, li) => (
                    <div key={li} style={{ color: "#fef3c7", fontSize: 16, lineHeight: 1.5 }}>
                      • {lim}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom Progress Bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "100%",
          height: 6,
          background: "rgba(15, 23, 42, 0.8)",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progress * 100}%`,
            background: "linear-gradient(90deg, #38bdf8 0%, #00f5ff 100%)",
            boxShadow: "0 0 12px #00f5ff",
          }}
        />
      </div>

      {/* Audio Layer */}
      {scene.audio_url && (
        <Audio src={staticFile(scene.audio_url)} />
      )}
    </div>
  );
};

export const RepoFlowComposition: React.FC<RepoFlowCompositionProps> = ({
  scenes,
}) => {
  const { fps } = useVideoConfig();

  return (
    <Series>
      {scenes.map((scene, idx) => {
        const sceneDurationInFrames = Math.max(
          30,
          Math.round(((scene.duration_ms || 6000) / 1000) * fps)
        );

        return (
          <Series.Sequence key={scene.scene_id || idx} durationInFrames={sceneDurationInFrames}>
            <SemanticSceneRenderer
              scene={scene}
              sceneIndex={idx}
              totalScenes={scenes.length}
              durationInFrames={sceneDurationInFrames}
            />
          </Series.Sequence>
        );
      })}
    </Series>
  );
};

export const RepoFlowVideo = RepoFlowComposition;
