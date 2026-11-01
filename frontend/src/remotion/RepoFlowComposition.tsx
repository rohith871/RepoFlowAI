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
  const entranceOpacity = interpolate(frame, [0, 10], [0, 1], {
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
    const nodeWidth = 220;
    const nodeHeight = 85;
    const startX = 60;
    const startY = 80;
    const gapX = 60;
    const gapY = 50;

    nodes.forEach((n, idx) => {
      let x = n.x ?? (startX + (idx % 3) * (nodeWidth + gapX));
      let y = n.y ?? (startY + Math.floor(idx / 3) * (nodeHeight + gapY));
      map.set(n.id, { x, y, width: nodeWidth, height: nodeHeight, node: n });
    });
    return map;
  }, [nodes]);

  // Code walkthrough active line
  const codeLines = (scene.code_excerpt || "").split("\n").slice(0, 14);
  const startLine = scene.highlight_lines?.[0] || 1;
  const activeLineIndex = Math.min(
    codeLines.length - 1,
    Math.floor(progress * Math.max(1, codeLines.length))
  );

  return (
    <div
      style={{
        width: 1920,
        height: 1080,
        backgroundColor: "#070e1a",
        color: "#f2f6ff",
        fontFamily: "'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif",
        padding: "60px 80px",
        boxSizing: "border-box",
        position: "relative",
        overflow: "hidden",
        opacity: entranceOpacity,
      }}
    >
      {/* Background ambient gradient glow */}
      <div
        style={{
          position: "absolute",
          top: -200,
          right: -100,
          width: 800,
          height: 800,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(20, 80, 130, 0.25) 0%, rgba(7, 14, 26, 0) 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Top Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          borderBottom: "1px solid #1a3854",
          paddingBottom: 18,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span
              style={{
                color: "#64d7ff",
                fontSize: 16,
                fontWeight: 700,
                letterSpacing: 2,
                textTransform: "uppercase",
              }}
            >
              REPOFLOW AI • {(scene.visual_type || scene.kind || "ARCHITECTURE").toUpperCase()}
            </span>
            <span
              style={{
                backgroundColor: "#112a42",
                color: "#8dc6f5",
                fontSize: 13,
                fontWeight: 600,
                padding: "2px 10px",
                borderRadius: 12,
                border: "1px solid #234d75",
              }}
            >
              Scene {sceneIndex + 1} of {totalScenes}
            </span>
          </div>
          <h1
            style={{
              fontSize: 38,
              margin: "6px 0 0 0",
              color: "#ffffff",
              letterSpacing: "-0.5px",
            }}
          >
            {scene.title}
          </h1>
        </div>

        {scene.question_answered && (
          <div
            style={{
              backgroundColor: "rgba(15, 45, 75, 0.8)",
              padding: "10px 20px",
              borderRadius: 8,
              border: "1px solid #2b6899",
              maxWidth: 620,
            }}
          >
            <div style={{ color: "#74c0fc", fontSize: 13, fontWeight: 700, letterSpacing: 0.5 }}>
              CORE QUESTION
            </div>
            <div style={{ fontSize: 17, fontWeight: 500, color: "#e3f0fc", marginTop: 2 }}>
              {scene.question_answered}
            </div>
          </div>
        )}
      </div>

      {/* Main Body Grid */}
      <div style={{ display: "flex", marginTop: 30, gap: 40, height: 720 }}>
        {/* Left Side: Educational Takeaways & Context */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            paddingRight: 10,
          }}
        >
          <div>
            {/* Takeaway / Intuition Banner */}
            {scene.takeaway && (
              <div
                style={{
                  backgroundColor: "rgba(11, 38, 59, 0.9)",
                  borderLeft: "5px solid #64d7ff",
                  padding: "18px 22px",
                  borderRadius: "0 10px 10px 0",
                  marginBottom: 20,
                  boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                }}
              >
                <div style={{ color: "#64d7ff", fontSize: 13, fontWeight: 800, letterSpacing: 1.5 }}>
                  ARCHITECTURAL TAKEAWAY
                </div>
                <div style={{ color: "#ffffff", fontSize: 21, fontWeight: 500, marginTop: 6, lineHeight: 1.4 }}>
                  {scene.takeaway}
                </div>
              </div>
            )}

            {/* Developer Guidance / Invariant Note */}
            {scene.developer_guidance && (
              <div
                style={{
                  backgroundColor: "rgba(16, 32, 48, 0.7)",
                  border: "1px solid #254a6e",
                  borderRadius: 10,
                  padding: "16px 20px",
                  marginBottom: 20,
                }}
              >
                <div style={{ color: "#a5d8ff", fontSize: 13, fontWeight: 700 }}>
                  DEVELOPER MENTAL MODEL
                </div>
                <div style={{ color: "#d0e4f7", fontSize: 18, marginTop: 4, lineHeight: 1.5 }}>
                  {scene.developer_guidance}
                </div>
              </div>
            )}

            {/* Hypothetical Failure Mode Callout */}
            {scene.counterfactual && (
              <div
                style={{
                  backgroundColor: "rgba(45, 26, 8, 0.8)",
                  border: "1px solid #f59f00",
                  borderRadius: 10,
                  padding: "16px 20px",
                  marginBottom: 20,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span
                    style={{
                      backgroundColor: "#f59f00",
                      color: "#000",
                      fontWeight: 800,
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontSize: 12,
                    }}
                  >
                    HYPOTHETICAL
                  </span>
                  <span style={{ color: "#ffd43b", fontSize: 14, fontWeight: 700 }}>
                    BOUNDARY FAILURE MODE
                  </span>
                </div>
                <div style={{ color: "#ffe066", fontSize: 18, lineHeight: 1.45 }}>
                  {scene.counterfactual.replace("[HYPOTHETICAL]", "").trim()}
                </div>
              </div>
            )}

            {/* Interactive Checkpoint Teaser */}
            {scene.checkpoint && (
              <div
                style={{
                  backgroundColor: "rgba(22, 40, 60, 0.8)",
                  border: "1px dashed #64d7ff",
                  borderRadius: 10,
                  padding: "14px 18px",
                  marginBottom: 16,
                }}
              >
                <div style={{ color: "#64d7ff", fontSize: 13, fontWeight: 800 }}>
                  ACTIVE LEARNING CHECKPOINT
                </div>
                <div style={{ color: "#e3f0fc", fontSize: 17, marginTop: 4 }}>
                  {scene.checkpoint.question_text}
                </div>
              </div>
            )}
          </div>

          {/* Bottom Source Anchor Citation */}
          <div
            style={{
              paddingTop: 12,
              borderTop: "1px solid #1a3854",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: 14,
              color: "#749ab8",
            }}
          >
            <span>
              Source anchors:{" "}
              <strong style={{ color: "#9ec5e8" }}>
                {scene.source_refs?.join(", ") || "Verified Repository Analysis"}
              </strong>
            </span>
            <span>30 FPS • Synchronized Animation</span>
          </div>
        </div>

        {/* Right Side: High-Fidelity Visual Representations */}
        <div
          style={{
            flex: 1.35,
            backgroundColor: "#050b14",
            borderRadius: 16,
            border: "2px solid #1c3c5e",
            padding: 24,
            display: "flex",
            flexDirection: "column",
            position: "relative",
            overflow: "hidden",
            boxShadow: "0 10px 40px rgba(0,0,0,0.5)",
          }}
        >
          {/* 1. CODE WALKTHROUGH */}
          {scene.visual_type === "code" && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  borderBottom: "1px solid #1c3c5e",
                  paddingBottom: 10,
                  marginBottom: 14,
                  fontSize: 15,
                  color: "#64d7ff",
                  fontWeight: 600,
                  fontFamily: "monospace",
                }}
              >
                <span>{scene.code_path || "Source File"}</span>
                <span
                  style={{
                    backgroundColor: "#0d2338",
                    padding: "3px 10px",
                    borderRadius: 6,
                    color: "#99ccff",
                  }}
                >
                  Line {startLine + activeLineIndex}
                </span>
              </div>
              <div
                style={{
                  flex: 1,
                  fontFamily: "'Fira Code', 'Consolas', monospace",
                  fontSize: 19,
                  lineHeight: 1.7,
                  overflow: "hidden",
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
                        padding: "2px 8px",
                        borderRadius: 6,
                        backgroundColor: isActive ? "rgba(22, 85, 120, 0.65)" : "transparent",
                        borderLeft: isActive ? "4px solid #64d7ff" : "4px solid transparent",
                        transition: "background-color 0.2s",
                      }}
                    >
                      <span
                        style={{
                          width: 45,
                          color: isActive ? "#64d7ff" : "#3b5873",
                          userSelect: "none",
                          textAlign: "right",
                          paddingRight: 16,
                        }}
                      >
                        {lineNo}
                      </span>
                      <span
                        style={{
                          color: isActive ? "#ffffff" : "#c4d8ed",
                          fontWeight: isActive ? 600 : 400,
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

          {/* 2. CONNECTED ARCHITECTURE DIAGRAM */}
          {scene.visual_type === "architecture" && (
            <div style={{ position: "relative", width: "100%", height: "100%" }}>
              <div style={{ color: "#64d7ff", fontSize: 14, fontWeight: 700, letterSpacing: 1, marginBottom: 10 }}>
                CONNECTED COMPONENT GRAPH
              </div>
              <svg
                style={{
                  position: "absolute",
                  top: 30,
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
                    <path d="M 0 1 L 8 5 L 0 9 z" fill="#64d7ff" />
                  </marker>
                </defs>

                {/* Render Connected Edges */}
                {edges.map((edge, idx) => {
                  const source = nodeMap.get(edge.source);
                  const target = nodeMap.get(edge.target);
                  if (!source || !target) return null;

                  const x1 = source.x + source.width;
                  const y1 = source.y + source.height / 2;
                  const x2 = target.x;
                  const y2 = target.y + target.height / 2;

                  // Active pulse moving along edge
                  const pulseX = x1 + (x2 - x1) * progress;
                  const pulseY = y1 + (y2 - y1) * progress;

                  return (
                    <g key={idx}>
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke="#25557d"
                        strokeWidth={3}
                        markerEnd="url(#remotion-arrow)"
                      />
                      <circle cx={pulseX} cy={pulseY} r={6} fill="#ffd43b" filter="drop-shadow(0 0 4px #ffd43b)" />
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
                      top: y + 30,
                      width,
                      height,
                      backgroundColor: nodeVisible ? "#0e2942" : "rgba(14, 41, 66, 0.4)",
                      border: nodeVisible ? "2px solid #64d7ff" : "1px solid #1a3c5a",
                      borderRadius: 10,
                      padding: "12px 16px",
                      boxSizing: "border-box",
                      transition: "all 0.3s ease",
                      boxShadow: nodeVisible ? "0 4px 14px rgba(100, 215, 255, 0.15)" : "none",
                    }}
                  >
                    <div
                      style={{
                        color: "#64d7ff",
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

          {/* 3. EXECUTION FLOW JOURNEY */}
          {scene.visual_type === "flow" && (
            <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
              <div style={{ color: "#64d7ff", fontSize: 15, fontWeight: 700, letterSpacing: 1, marginBottom: 18 }}>
                EXECUTION FLOW SEQUENCE
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: 1, justifyContent: "center" }}>
                {(scene.flow_steps || []).slice(0, 6).map((step, idx) => {
                  const totalSteps = Math.min(6, (scene.flow_steps || []).length);
                  const activeStepIdx = Math.min(totalSteps - 1, Math.floor(progress * totalSteps));
                  const isCurrent = idx === activeStepIdx;
                  const isPast = idx < activeStepIdx;

                  return (
                    <div
                      key={step.step_number}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 16,
                        backgroundColor: isCurrent ? "#123c5e" : isPast ? "#0a1e30" : "rgba(10, 30, 48, 0.4)",
                        border: isCurrent ? "2px solid #64d7ff" : "1px solid #1c3c5c",
                        padding: "14px 20px",
                        borderRadius: 10,
                        transition: "all 0.25s",
                      }}
                    >
                      <div
                        style={{
                          backgroundColor: isCurrent ? "#64d7ff" : isPast ? "#2b6899" : "#1a3854",
                          color: isCurrent ? "#000" : "#fff",
                          fontWeight: 800,
                          borderRadius: "50%",
                          width: 32,
                          height: 32,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 15,
                        }}
                      >
                        {step.step_number}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ color: isCurrent ? "#ffffff" : isPast ? "#a2c6e6" : "#5d7e9e", fontSize: 18, fontWeight: isCurrent ? 700 : 500 }}>
                          {step.description}
                        </div>
                        <div style={{ color: "#64d7ff", fontSize: 12, marginTop: 2 }}>
                          Operation: {step.operation_type}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 4. DATA TRANSFORMATION BOUNDARY */}
          {scene.visual_type === "data_transformation" && (
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", gap: 36 }}>
              <div style={{ textAlign: "center", color: "#64d7ff", fontSize: 20, fontWeight: 700, letterSpacing: 1 }}>
                DATA BOUNDARY & IN-MEMORY TRANSFORMATION
              </div>
              <div style={{ display: "flex", justifyContent: "space-around", alignItems: "center" }}>
                <div
                  style={{
                    backgroundColor: "#0d263e",
                    border: "2px solid #2e71a1",
                    padding: 24,
                    borderRadius: 12,
                    width: 200,
                    textAlign: "center",
                  }}
                >
                  <div style={{ color: "#74c0fc", fontSize: 13, fontWeight: 700 }}>INPUT</div>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>Client Request</div>
                </div>
                <div style={{ fontSize: 32, color: "#64d7ff" }}>➔</div>
                <div
                  style={{
                    backgroundColor: "#13385c",
                    border: "2px solid #64d7ff",
                    padding: 24,
                    borderRadius: 12,
                    width: 220,
                    textAlign: "center",
                    boxShadow: "0 0 20px rgba(100, 215, 255, 0.2)",
                  }}
                >
                  <div style={{ color: "#a5d8ff", fontSize: 13, fontWeight: 700 }}>DOMAIN ENTITY</div>
                  <div style={{ fontSize: 21, fontWeight: 800, marginTop: 8 }}>Typed Model</div>
                </div>
                <div style={{ fontSize: 32, color: "#64d7ff" }}>➔</div>
                <div
                  style={{
                    backgroundColor: "#0d263e",
                    border: "2px solid #2e71a1",
                    padding: 24,
                    borderRadius: 12,
                    width: 200,
                    textAlign: "center",
                  }}
                >
                  <div style={{ color: "#74c0fc", fontSize: 13, fontWeight: 700 }}>OUTPUT</div>
                  <div style={{ fontSize: 20, fontWeight: 700, marginTop: 8 }}>API Response</div>
                </div>
              </div>
            </div>
          )}

          {/* 5. SUMMARY & INVARIANTS */}
          {scene.visual_type === "summary" && (
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", height: "100%", gap: 24 }}>
              <div style={{ color: "#64d7ff", fontSize: 20, fontWeight: 700, letterSpacing: 1, marginBottom: 8 }}>
                VERIFIED ARCHITECTURAL INVARIANTS
              </div>
              <div
                style={{
                  backgroundColor: "rgba(11, 40, 66, 0.8)",
                  border: "1px solid #1c7ed6",
                  padding: 22,
                  borderRadius: 10,
                }}
              >
                <div style={{ color: "#74c0fc", fontWeight: 700, fontSize: 18 }}>✓ Verified Static Call Chain</div>
                <div style={{ color: "#e3f0fc", fontSize: 16, marginTop: 6, lineHeight: 1.5 }}>
                  The AST establishes deterministic connections between API route handlers, domain helpers, and data models.
                </div>
              </div>
              <div
                style={{
                  backgroundColor: "rgba(45, 26, 8, 0.8)",
                  border: "1px solid #f59f00",
                  padding: 22,
                  borderRadius: 10,
                }}
              >
                <div style={{ color: "#ffd43b", fontWeight: 700, fontSize: 18 }}>⚠ Disclosed Runtime Boundaries</div>
                <div style={{ color: "#ffe066", fontSize: 16, marginTop: 6, lineHeight: 1.5 }}>
                  Static code proves module structure. Runtime database connection pools and external network calls require live telemetry.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Animated Bottom Timeline Bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          width: "100%",
          height: 6,
          backgroundColor: "#11263b",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progress * 100}%`,
            backgroundColor: "#64d7ff",
            boxShadow: "0 0 10px #64d7ff",
          }}
        />
      </div>
    </div>
  );
};

export const RepoFlowVideo: React.FC<RepoFlowCompositionProps> = ({ scenes }) => {
  if (!scenes || scenes.length === 0) {
    return (
      <div
        style={{
          width: 1920,
          height: 1080,
          backgroundColor: "#070e1a",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 32,
        }}
      >
        RepoFlow AI: Preparing Verified Repository Scenes...
      </div>
    );
  }

  return (
    <Series>
      {scenes.map((scene, index) => {
        const durationFrames = Math.max(30, Math.round(((scene.duration_ms || 6000) / 1000) * 30));
        return (
          <Series.Sequence key={scene.scene_id || index} durationInFrames={durationFrames}>
            <SemanticSceneRenderer
              scene={scene}
              sceneIndex={index}
              totalScenes={scenes.length}
              durationInFrames={durationFrames}
            />
            {scene.audio_url && <Audio src={staticFile(scene.audio_url)} />}
          </Series.Sequence>
        );
      })}
    </Series>
  );
};
