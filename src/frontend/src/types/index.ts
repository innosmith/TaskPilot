export interface Tag {
  id: string;
  name: string;
  color: string;
}

export interface TaskCard {
  id: string;
  title: string;
  project_id: string;
  board_column_id: string;
  board_position: number;
  pipeline_column_id: string | null;
  pipeline_position: number | null;
  assignee: string;
  due_date: string | null;
  is_completed: boolean;
  is_pinned: boolean;
  recurrence_rule: string | null;
  template_id: string | null;
  tags: Tag[];
  checklist_total: number;
  checklist_done: number;
}

export interface ChecklistItem {
  id: string;
  text: string;
  is_checked: boolean;
  position: number;
}

export interface TaskDetail {
  id: string;
  title: string;
  description: string | null;
  project_id: string;
  board_column_id: string;
  board_position: number;
  pipeline_column_id: string | null;
  pipeline_position: number | null;
  assignee: string;
  due_date: string | null;
  is_completed: boolean;
  is_pinned: boolean;
  data_class: string;
  llm_override: string | null;
  autonomy_level: string;
  recurrence_rule: string | null;
  template_id: string | null;
  calendar_duration_minutes: number | null;
  calendar_preferred_time: string | null;
  needs_review: boolean;
  tags: Tag[];
  checklist_items: ChecklistItem[];
  created_at: string;
  updated_at: string;
}

export interface BoardColumn {
  id: string;
  name: string;
  color: string | null;
  icon_emoji: string | null;
  position: number;
  project_id: string;
}

export interface Project {
  id: string;
  name: string;
  color: string;
  background_url: string | null;
  icon_url: string | null;
  icon_emoji: string | null;
  status: string;
  board_columns: BoardColumn[];
}

export interface BoardData {
  project: Project;
  columns: Array<BoardColumn & { tasks: TaskCard[] }>;
}

export interface PipelineColumn {
  id: string;
  name: string;
  color: string | null;
  icon_emoji: string | null;
  position: number;
  tasks: TaskCard[];
}

export interface PipelineData {
  columns: PipelineColumn[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
}

export interface TaskUpdatePayload {
  title?: string;
  description?: string;
  board_column_id?: string;
  board_position?: number;
  pipeline_column_id?: string | null;
  pipeline_position?: number | null;
  assignee?: string;
  due_date?: string | null;
  is_completed?: boolean;
  is_pinned?: boolean;
  data_class?: string;
  llm_override?: string;
  autonomy_level?: string;
  recurrence_rule?: string | null;
  calendar_duration_minutes?: number | null;
  calendar_preferred_time?: string | null;
} = 'modal' | 'panel' | 'fullscreen';

export interface TaskCreatePayload {
  title: string;
  project_id: string;
  board_column_id: string;
  description?: string;
  pipeline_column_id?: string;
  assignee?: string;
  due_date?: string;
  recurrence_rule?: string;
}

// --- Agent Jobs ---

export interface AgentJob {
  id: string;
  task_id: string | null;
  job_type: string | null;
  status: 'queued' | 'running' | 'awaiting_approval' | 'completed' | 'failed';
  llm_model: string | null;
  tokens_used: number | null;
  cost_usd: number | null;
  output: string | null;
  error_message: string | null;
  metadata_json: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  task_title: string | null;
}

// --- Project Metrics ---

export interface ProjectMetrics {
  id: string;
  name: string;
  color: string;
  status: string;
  total_tasks: number;
  open_tasks: number;
  completed_tasks: number;
  overdue_tasks: number;
  progress_pct: number;
}

// --- Search ---

export interface SearchTaskHit {
  id: string;
  title: string;
  project_id: string;
  project_name: string;
  assignee: string;
  is_completed: boolean;
  due_date: string | null;
}

export interface SearchProjectHit {
  id: string;
  name: string;
  color: string;
  status: string;
}

export interface SearchTagHit {
  id: string;
  name: string;
  color: string;
}

export interface SearchResults {
  tasks: SearchTaskHit[];
  projects: SearchProjectHit[];
  tags: SearchTagHit[];
}
