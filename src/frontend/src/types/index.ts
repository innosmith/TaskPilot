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
  tags: Tag[];
  checklist_total: number;
  checklist_done: number;
}

export interface ChecklistItem {
  id: string;
  task_id: string;
  title: string;
  is_done: boolean;
  position: number;
}

export interface TaskDetail extends TaskCard {
  description: string | null;
  checklist_items: ChecklistItem[];
  created_at: string;
  updated_at: string;
}

export interface BoardColumn {
  id: string;
  name: string;
  position: number;
  project_id: string;
}

export interface Project {
  id: string;
  name: string;
  color: string;
  background_url: string | null;
  board_columns: BoardColumn[];
}

export interface BoardData {
  project: Project;
  columns: Array<BoardColumn & { tasks: TaskCard[] }>;
}

export interface PipelineColumn {
  id: string;
  name: string;
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
}

export interface TaskCreatePayload {
  title: string;
  project_id: string;
  board_column_id: string;
  description?: string;
  pipeline_column_id?: string;
  assignee?: string;
  due_date?: string;
}
