export interface VisualNode {
  id: string;
  label: string;
  kind?: string;
  role?: string;
  subsystem?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
}

export interface VisualEdge {
  id?: string;
  source: string;
  target: string;
  type?: string;
  label?: string;
  why_it_exists?: string;
  status?: string;
}

export interface Boundary {
  boundary_id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SemanticSceneProps {
  scene_id: string;
  title: string;
  kind: string;
  visual_type: string;
  objective?: string;
  question_answered?: string;
  narration: string;
  takeaway?: string;
  developer_guidance?: string;
  counterfactual?: string;
  code_excerpt?: string;
  code_path?: string;
  highlight_line?: number;
  highlight_lines?: number[];
  visual_nodes?: VisualNode[];
  visual_edges?: VisualEdge[];
  flow_nodes?: string[];
  execution_steps?: Array<{
    step_number: number;
    component_name: string;
    description: string;
    operation_type: string;
    source_ref?: string;
  }>;
  flow_steps?: Array<{ step_number: number; description: string; operation_type: string }>;
  boundaries?: Boundary[];
  source_refs?: string[];
  invariants?: string[];
  limitations?: string[];
  duration_ms: number;
  audio_url?: string | null;
  checkpoint?: {
    checkpoint_id: string;
    question_text: string;
    options: Array<{ id: string; text: string; is_correct: boolean; explanation: string }>;
  };
}

export interface RepoFlowCompositionProps {
  lesson_id: string;
  title: string;
  repository_id: string;
  scenes: SemanticSceneProps[];
  captions?: Array<{ text: string; start_ms: number; end_ms: number }>;
  chapters?: Array<{ title: string; start_ms: number; end_ms: number; scene_id: string }>;
}
