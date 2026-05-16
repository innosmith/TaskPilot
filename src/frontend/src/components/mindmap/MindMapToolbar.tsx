import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Save, Share2, ListChecks, Palette, Eye, Users, Lock, Check, ChevronDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../api/client';

interface Project { id: string; name: string; }

interface ToolbarProps {
  title: string;
  visibility: string;
  isDirty: boolean;
  projectId: string | null;
  projectName: string | null;
  onTitleChange: (title: string) => void;
  onVisibilityChange: (v: string, projectId?: string) => void;
  onSave: () => void;
  onToggleStyling: () => void;
  onOpenShare: () => void;
  onOpenConvert: () => void;
}

const VISIBILITY_OPTIONS = [
  { value: 'private', label: 'Privat', icon: Lock, desc: 'Nur für dich sichtbar' },
  { value: 'project', label: 'Projekt', icon: Users, desc: 'Sichtbar für Projekt-Mitglieder' },
  { value: 'shared', label: 'Geteilt', icon: Eye, desc: 'Über Share-Link teilbar' },
];

export function MindMapToolbar({
  title, visibility, isDirty, projectId, projectName,
  onTitleChange, onVisibilityChange,
  onSave, onToggleStyling, onOpenShare, onOpenConvert,
}: ToolbarProps) {
  const navigate = useNavigate();
  const { isOwner } = useAuth();
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleValue, setTitleValue] = useState(title);
  const [showVisMenu, setShowVisMenu] = useState(false);
  const [savedFeedback, setSavedFeedback] = useState(false);
  const [showProjectPicker, setShowProjectPicker] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);

  const confirmTitle = useCallback(() => {
    onTitleChange(titleValue.trim() || 'Unbenannte Mind-Map');
    setEditingTitle(false);
  }, [titleValue, onTitleChange]);

  const handleSave = useCallback(() => {
    onSave();
    setSavedFeedback(true);
    setTimeout(() => setSavedFeedback(false), 2000);
  }, [onSave]);

  const loadProjects = useCallback(async () => {
    if (projectsLoaded) return;
    try {
      const data = await api.get<Project[]>('/api/projects');
      setProjects(data);
      setProjectsLoaded(true);
    } catch {}
  }, [projectsLoaded]);

  const handleVisibilitySelect = useCallback((value: string) => {
    if (value === 'project') {
      loadProjects();
      setShowProjectPicker(true);
      setShowVisMenu(false);
    } else {
      onVisibilityChange(value);
      setShowVisMenu(false);
      setShowProjectPicker(false);
    }
  }, [onVisibilityChange, loadProjects]);

  const handleProjectSelect = useCallback((proj: Project) => {
    onVisibilityChange('project', proj.id);
    setShowProjectPicker(false);
  }, [onVisibilityChange]);

  useEffect(() => {
    if (!showVisMenu && !showProjectPicker) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-testid="visibility-area"]')) {
        setShowVisMenu(false);
        setShowProjectPicker(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showVisMenu, showProjectPicker]);

  const CurrentVisIcon = VISIBILITY_OPTIONS.find(v => v.value === visibility)?.icon || Lock;

  return (
    <div data-testid="mindmap-toolbar" className="flex items-center gap-2 px-4 py-2 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm border-b border-gray-200 dark:border-gray-800 z-10">
      <button
        onClick={() => navigate('/mindmaps')}
        className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        data-testid="mindmap-back-button"
      >
        <ArrowLeft size={18} />
      </button>

      {editingTitle ? (
        <input
          value={titleValue}
          onChange={e => setTitleValue(e.target.value)}
          onBlur={confirmTitle}
          onKeyDown={e => { if (e.key === 'Enter') confirmTitle(); if (e.key === 'Escape') { setTitleValue(title); setEditingTitle(false); } }}
          className="text-lg font-semibold bg-transparent border-b-2 border-indigo-400 outline-none px-1 dark:text-white"
          autoFocus
          data-testid="mindmap-title-input"
        />
      ) : (
        <h1
          onClick={() => { setTitleValue(title); setEditingTitle(true); }}
          className="text-lg font-semibold cursor-text hover:text-indigo-600 dark:text-white dark:hover:text-indigo-400 transition-colors"
          data-testid="mindmap-title"
        >
          {title}
        </h1>
      )}

      {isDirty && (
        <span className="text-xs text-amber-500 font-medium">Ungespeichert</span>
      )}

      <div className="flex-1" />

      {isOwner && (
        <div className="relative" data-testid="visibility-area">
          <button
            onClick={() => { setShowVisMenu(!showVisMenu); setShowProjectPicker(false); }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            data-testid="mindmap-visibility-toggle"
          >
            <CurrentVisIcon size={14} />
            <span>{VISIBILITY_OPTIONS.find(v => v.value === visibility)?.label}</span>
            {visibility === 'project' && projectName && (
              <span className="text-xs text-gray-400 truncate max-w-[120px]">({projectName})</span>
            )}
            <ChevronDown size={12} className="text-gray-400" />
          </button>

          {showVisMenu && (
            <div className="absolute right-0 top-full mt-1 w-56 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 py-1">
              {VISIBILITY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => handleVisibilitySelect(opt.value)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 ${visibility === opt.value ? 'text-indigo-600 dark:text-indigo-400 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                >
                  <opt.icon size={14} />
                  <div className="text-left">
                    <div>{opt.label}</div>
                    <div className="text-xs text-gray-400">{opt.desc}</div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {showProjectPicker && (
            <div className="absolute right-0 top-full mt-1 w-64 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 py-1 max-h-72 overflow-y-auto">
              <div className="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-100 dark:border-gray-800">
                Projekt wählen
              </div>
              {projects.length === 0 && (
                <div className="px-3 py-4 text-sm text-gray-400 text-center">
                  {projectsLoaded ? 'Keine Projekte vorhanden' : 'Lade Projekte...'}
                </div>
              )}
              {projects.map(p => (
                <button
                  key={p.id}
                  onClick={() => handleProjectSelect(p)}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 text-left ${
                    projectId === p.id ? 'text-indigo-600 dark:text-indigo-400 font-medium bg-indigo-50/50 dark:bg-indigo-950/30' : 'text-gray-700 dark:text-gray-300'
                  }`}
                  data-testid={`project-option-${p.id}`}
                >
                  <Users size={14} className="shrink-0" />
                  <span className="truncate">{p.name}</span>
                  {projectId === p.id && <Check size={14} className="ml-auto shrink-0 text-indigo-500" />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <button
        onClick={onToggleStyling}
        className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        title="Design-Einstellungen"
        data-testid="mindmap-styling-toggle"
      >
        <Palette size={18} />
      </button>

      {isOwner && (
        <>
          <button
            onClick={onOpenConvert}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-400 dark:hover:bg-emerald-900/50 transition-colors"
            title="Ausgewählte Knoten als Tasks übernehmen"
            data-testid="mindmap-convert-button"
          >
            <ListChecks size={14} />
            <span className="hidden sm:inline">Als Tasks</span>
          </button>

          <button
            onClick={onOpenShare}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-400 dark:hover:bg-indigo-900/50 transition-colors"
            data-testid="mindmap-share-button"
          >
            <Share2 size={14} />
            <span className="hidden sm:inline">Teilen</span>
          </button>
        </>
      )}

      <button
        onClick={handleSave}
        className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
          savedFeedback
            ? 'bg-emerald-600 text-white'
            : isDirty
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
        }`}
        data-testid="mindmap-save-button"
      >
        {savedFeedback ? (
          <>
            <Check size={14} />
            <span className="hidden sm:inline">Gespeichert</span>
          </>
        ) : (
          <>
            <Save size={14} />
            <span className="hidden sm:inline">Speichern</span>
          </>
        )}
      </button>
    </div>
  );
}
