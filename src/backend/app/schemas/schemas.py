import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


# --- Project ---

class ProjectBase(BaseModel):
    name: str
    color: str = "#3B82F6"
    description: str | None = None
    background_url: str | None = None
    status: str = "active"
    priority: int = 0


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None
    background_url: str | None = None
    status: str | None = None
    priority: int | None = None


class BoardColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str | None
    position: float
    is_archive: bool


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProjectWithColumns(ProjectOut):
    board_columns: list[BoardColumnOut] = []


# --- Pipeline ---

class PipelineColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    position: float
    column_type: str


# --- Tag ---

class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    color: str


# --- Checklist ---

class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    text: str
    is_checked: bool
    position: float


class ChecklistItemCreate(BaseModel):
    text: str
    position: float | None = None


class ChecklistItemUpdate(BaseModel):
    text: str | None = None
    is_checked: bool | None = None
    position: float | None = None


# --- Task ---

class TaskBase(BaseModel):
    title: str
    description: str | None = None
    assignee: str = "me"
    due_date: date | None = None
    data_class: str = "internal"
    llm_override: str | None = None
    autonomy_level: str = "L1"
    is_pinned: bool = False
    recurrence_rule: str | None = None


class TaskCreate(TaskBase):
    project_id: uuid.UUID
    board_column_id: uuid.UUID
    board_position: float | None = None
    pipeline_column_id: uuid.UUID | None = None
    pipeline_position: float | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    board_column_id: uuid.UUID | None = None
    board_position: float | None = None
    pipeline_column_id: uuid.UUID | None = None
    pipeline_position: float | None = None
    assignee: str | None = None
    due_date: date | None = None
    data_class: str | None = None
    llm_override: str | None = None
    autonomy_level: str | None = None
    is_completed: bool | None = None
    is_pinned: bool | None = None


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    board_column_id: uuid.UUID
    board_position: float
    pipeline_column_id: uuid.UUID | None
    pipeline_position: float | None
    is_completed: bool
    created_at: datetime
    updated_at: datetime
    tags: list[TagOut] = []
    checklist_items: list[ChecklistItemOut] = []


class TaskCard(BaseModel):
    """Leichtgewichtige Task-Darstellung fuer Board/Pipeline-Ansichten."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    board_column_id: uuid.UUID
    board_position: float
    pipeline_column_id: uuid.UUID | None
    pipeline_position: float | None
    assignee: str
    due_date: date | None
    is_completed: bool
    is_pinned: bool
    tags: list[TagOut] = []
    checklist_total: int = 0
    checklist_done: int = 0


# --- Board ---

class BoardColumnWithTasks(BoardColumnOut):
    tasks: list[TaskCard] = []


class BoardOut(BaseModel):
    project: ProjectOut
    columns: list[BoardColumnWithTasks]


# --- Pipeline ---

class PipelineColumnWithTasks(PipelineColumnOut):
    tasks: list[TaskCard] = []


class PipelineOut(BaseModel):
    columns: list[PipelineColumnWithTasks]


# --- Auth ---

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    display_name: str
    role: str


# --- Board Column Management ---

class BoardColumnCreate(BaseModel):
    name: str
    color: str | None = None
    position: float | None = None
    is_archive: bool = False


class BoardColumnUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    position: float | None = None
    is_archive: bool | None = None
