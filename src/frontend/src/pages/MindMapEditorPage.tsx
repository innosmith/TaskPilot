import { useCallback, useEffect, useRef, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  ReactFlowProvider,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useReactFlow,
  type Node,
} from '@xyflow/react';
import { api } from '../api/client';
import { useMindmapStore, getParentId, getChildIds, getSiblingIds } from '../stores/mindmapStore';
import type { MindMapNodeData } from '../stores/mindmapStore';
import { MindMapNode } from '../components/mindmap/MindMapNode';
import { MindMapEdge } from '../components/mindmap/MindMapEdge';
import { MindMapToolbar } from '../components/mindmap/MindMapToolbar';
import { StylingPanel } from '../components/mindmap/StylingPanel';
import { DEFAULT_THEME_ID, getThemeById } from '../components/mindmap/themes';
import { ConvertToTasksDialog } from '../components/mindmap/ConvertToTasksDialog';
import { ShareDialog } from '../components/mindmap/ShareDialog';
import { NodeContextMenu } from '../components/mindmap/NodeContextMenu';
import type { MindmapDetail } from '../types';

const nodeTypes = { mindmapNode: MindMapNode };
const edgeTypes = { mindmapEdge: MindMapEdge };

function MindMapEditorInner() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { fitView } = useReactFlow();

  const {
    nodes, edges, isDirty,
    setNodes, setEdges, onNodesChange, onEdgesChange, onConnect,
    addChildNode, addSiblingNode, deleteNode, updateNodeData,
    setSelectedNodeIds, selectedNodeIds, markClean,
    setCurrentThemeId: setStoreThemeId, clearNodeAndEdgeStyles,
  } = useMindmapStore();

  const [title, setTitle] = useState('');
  const [visibility, setVisibility] = useState('private');
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState<string | null>(null);
  const [backgroundUrl, setBackgroundUrl] = useState<string | null>(null);
  const [currentThemeId, setCurrentThemeId] = useState(DEFAULT_THEME_ID);
  const currentTheme = useMemo(() => getThemeById(currentThemeId), [currentThemeId]);
  const [loading, setLoading] = useState(true);
  const [showStyling, setShowStyling] = useState(false);
  const [showConvert, setShowConvert] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ nodeId: string; x: number; y: number } | null>(null);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef<string>('');

  const selectedNodeColor = useMemo(() => {
    if (selectedNodeIds.length !== 1) return null;
    const node = nodes.find(n => n.id === selectedNodeIds[0]);
    return (node?.data as any)?.color || null;
  }, [selectedNodeIds, nodes]);

  const rootLabel = useMemo(() => {
    const root = nodes.find(n => n.id === 'root');
    return (root?.data as any)?.label || '';
  }, [nodes]);

  useEffect(() => {
    if (!rootLabel || loading) return;
    if (rootLabel !== title && rootLabel !== 'Neuer Knoten') {
      setTitle(rootLabel);
      if (id) {
        api.patch(`/api/mindmaps/${id}`, { title: rootLabel }).catch(() => {});
      }
    }
  }, [rootLabel]);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.get<MindmapDetail>(`/api/mindmaps/${id}`)
      .then(async (data) => {
        setTitle(data.title);
        setVisibility(data.visibility);
        setProjectId(data.project_id || null);
        setBackgroundUrl(data.background_url || data.background_color || null);
        if (data.settings?.theme) {
          setCurrentThemeId(data.settings.theme);
          setStoreThemeId(data.settings.theme);
        }
        const loadedNodes = (data.flow_data.nodes || []).map((n: any) => ({
          ...n,
          type: n.type || 'mindmapNode',
          selected: false,
          data: {
            label: n.data?.label || 'Neuer Knoten',
            notes: n.data?.notes,
            url: n.data?.url,
            isCollapsed: n.data?.isCollapsed,
            side: n.data?.side,
            icon: n.data?.icon,
          },
        }));
        const rootNode = loadedNodes.find((n: any) => n.id === 'root');
        if (rootNode) rootNode.data.label = data.title;

        const loadedEdges = (data.flow_data.edges || []).map((e: any) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type || 'mindmapEdge',
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
        }));

        setNodes(loadedNodes);
        setEdges(loadedEdges);
        markClean();
        lastSavedRef.current = JSON.stringify(data.flow_data);
        setTimeout(() => fitView({ padding: 0.2 }), 100);

        if (data.project_id) {
          try {
            const proj = await api.get<{ id: string; name: string }>(`/api/projects/${data.project_id}`);
            setProjectName(proj.name);
          } catch {
            setProjectName(null);
          }
        }
      })
      .catch(() => navigate('/mindmaps'))
      .finally(() => setLoading(false));
  }, [id, setNodes, setEdges, markClean, fitView, navigate]);

  const saveNow = useCallback(async () => {
    if (!id) return;
    const viewport = { x: 0, y: 0, zoom: 1 };
    const flowData = { nodes, edges, viewport };
    const serialized = JSON.stringify(flowData);
    if (serialized === lastSavedRef.current) return;

    try {
      await api.patch(`/api/mindmaps/${id}`, { flow_data: flowData });
      lastSavedRef.current = serialized;
      markClean();
    } catch {
      // Fehler wird durch API-Client gehandelt
    }
  }, [id, nodes, edges, markClean]);

  useEffect(() => {
    if (!isDirty || !id) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(saveNow, 1500);
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [isDirty, nodes, edges, saveNow, id]);

  const selectSingleNode = useCallback((targetId: string) => {
    setSelectedNodeIds([targetId]);
  }, [setSelectedNodeIds]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;

      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveNow();
        return;
      }
      if (e.key === 'Tab' && selectedNodeIds.length === 1 && !isInput) {
        e.preventDefault();
        const newId = addChildNode(selectedNodeIds[0]);
        if (newId) {
          setTimeout(() => {
            const nodeEl = document.querySelector(`[data-testid="mindmap-node-${newId}"] input`);
            if (nodeEl) (nodeEl as HTMLElement).focus();
          }, 50);
        }
        return;
      }
      if (e.key === 'Enter' && selectedNodeIds.length === 1 && !isInput && !e.shiftKey) {
        e.preventDefault();
        const newId = addSiblingNode(selectedNodeIds[0]);
        if (newId) {
          setTimeout(() => {
            const nodeEl = document.querySelector(`[data-testid="mindmap-node-${newId}"] input`);
            if (nodeEl) (nodeEl as HTMLElement).focus();
          }, 50);
        }
        return;
      }
      if ((e.key === 'Backspace' || e.key === 'Delete') && selectedNodeIds.length >= 1 && !isInput) {
        e.preventDefault();
        selectedNodeIds.forEach(nid => deleteNode(nid));
        return;
      }
      if (e.key === 'F2' && selectedNodeIds.length === 1 && !isInput) {
        e.preventDefault();
        const nodeEl = document.querySelector(`[data-testid="mindmap-node-${selectedNodeIds[0]}"]`);
        if (nodeEl) {
          const label = nodeEl.querySelector('.cursor-text');
          if (label) (label as HTMLElement).dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        }
        return;
      }

      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) && !isInput) {
        if (selectedNodeIds.length !== 1) return;
        e.preventDefault();
        e.stopPropagation();
        const currentId = selectedNodeIds[0];
        const { nodes: sNodes, edges: sEdges } = useMindmapStore.getState();
        const currentNode = sNodes.find(n => n.id === currentId);
        if (!currentNode) return;

        const isOnLeft = (currentNode.data as MindMapNodeData)?.side === 'left';
        let targetId: string | null = null;

        if (e.key === 'ArrowLeft') {
          if (isOnLeft || currentId === 'root') {
            const children = getChildIds(currentId, sEdges);
            const leftChildren = children.filter(cid => {
              const cn = sNodes.find(n => n.id === cid);
              return (cn?.data as MindMapNodeData)?.side === 'left';
            });
            targetId = leftChildren[0] || children[0] || null;
          } else {
            targetId = getParentId(currentId, sEdges);
          }
        } else if (e.key === 'ArrowRight') {
          if (!isOnLeft || currentId === 'root') {
            const children = getChildIds(currentId, sEdges);
            const rightChildren = children.filter(cid => {
              const cn = sNodes.find(n => n.id === cid);
              return (cn?.data as MindMapNodeData)?.side !== 'left';
            });
            targetId = rightChildren[0] || children[0] || null;
          } else {
            targetId = getParentId(currentId, sEdges);
          }
        } else {
          const siblings = getSiblingIds(currentId, sNodes, sEdges);
          const idx = siblings.indexOf(currentId);
          if (idx !== -1) {
            const nextIdx = e.key === 'ArrowUp' ? idx - 1 : idx + 1;
            if (nextIdx >= 0 && nextIdx < siblings.length) {
              targetId = siblings[nextIdx];
            }
          }
        }

        if (targetId) selectSingleNode(targetId);
      }
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [selectedNodeIds, addChildNode, addSiblingNode, deleteNode, saveNow, selectSingleNode]);

  const handleTitleChange = useCallback(async (newTitle: string) => {
    setTitle(newTitle);
    updateNodeData('root', { label: newTitle });
    if (id) {
      try { await api.patch(`/api/mindmaps/${id}`, { title: newTitle }); } catch {}
    }
  }, [id, updateNodeData]);

  const handleVisibilityChange = useCallback(async (v: string, newProjectId?: string) => {
    setVisibility(v);
    if (id) {
      const patch: Record<string, any> = { visibility: v };
      if (newProjectId) {
        patch.project_id = newProjectId;
        setProjectId(newProjectId);
        try {
          const proj = await api.get<{ id: string; name: string }>(`/api/projects/${newProjectId}`);
          setProjectName(proj.name);
        } catch {
          setProjectName(null);
        }
      }
      try { await api.patch(`/api/mindmaps/${id}`, patch); } catch {}
    }
  }, [id]);

  const handleBackgroundChange = useCallback(async (url: string | null, _type: string | null) => {
    setBackgroundUrl(url);
    if (id) {
      try { await api.patch(`/api/mindmaps/${id}`, { background_url: url, background_color: null }); } catch {}
    }
  }, [id]);

  const handleThemeChange = useCallback(async (themeId: string) => {
    setCurrentThemeId(themeId);
    setStoreThemeId(themeId);
    clearNodeAndEdgeStyles();
    if (id) {
      try { await api.patch(`/api/mindmaps/${id}`, { settings: { theme: themeId } }); } catch {}
    }
  }, [id, setStoreThemeId, clearNodeAndEdgeStyles]);

  const handleNodeColorChange = useCallback((color: string) => {
    selectedNodeIds.forEach(nid => updateNodeData(nid, { color }));
  }, [selectedNodeIds, updateNodeData]);

  const handleNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (_event.shiftKey && selectedNodeIds.length >= 1) {
      const lastSelected = selectedNodeIds[selectedNodeIds.length - 1];
      const lastParentEdge = edges.find(e => e.target === lastSelected);
      const clickedParentEdge = edges.find(e => e.target === node.id);

      let targetIds: string[];
      if (lastParentEdge && clickedParentEdge && lastParentEdge.source === clickedParentEdge.source) {
        const siblings = edges
          .filter(e => e.source === lastParentEdge.source)
          .map(e => e.target);
        const idxA = siblings.indexOf(lastSelected);
        const idxB = siblings.indexOf(node.id);
        if (idxA !== -1 && idxB !== -1) {
          const from = Math.min(idxA, idxB);
          const to = Math.max(idxA, idxB);
          const rangeIds = siblings.slice(from, to + 1);
          targetIds = Array.from(new Set([...selectedNodeIds, ...rangeIds]));
        } else {
          targetIds = [...selectedNodeIds, node.id];
        }
      } else {
        targetIds = [...selectedNodeIds, node.id];
      }
      setSelectedNodeIds(Array.from(new Set(targetIds)));
    } else if (_event.metaKey || _event.ctrlKey) {
      if (selectedNodeIds.includes(node.id)) {
        setSelectedNodeIds(selectedNodeIds.filter(nid => nid !== node.id));
      } else {
        setSelectedNodeIds([...selectedNodeIds, node.id]);
      }
    } else {
      setSelectedNodeIds([node.id]);
    }
  }, [selectedNodeIds, edges, setSelectedNodeIds]);

  const handleNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    setContextMenu({ nodeId: node.id, x: event.clientX, y: event.clientY });
  }, []);

  const handlePaneClick = useCallback(() => {
    setContextMenu(null);
    setSelectedNodeIds([]);
  }, [setSelectedNodeIds]);

  const handleContextMenuColorChange = useCallback((nodeId: string) => {
    setSelectedNodeIds([nodeId]);
    setShowStyling(true);
  }, [setSelectedNodeIds]);

  const handleAddNote = useCallback((nodeId: string) => {
    const note = prompt('Notiz eingeben:');
    if (note !== null) updateNodeData(nodeId, { notes: note });
  }, [updateNodeData]);

  const reactFlowStyle = useMemo(() => {
    const style: React.CSSProperties = {};
    if (backgroundUrl) {
      if (backgroundUrl.startsWith('gradient:')) {
        style.background = backgroundUrl.replace('gradient:', '');
      } else if (backgroundUrl.startsWith('#') || backgroundUrl.startsWith('rgb')) {
        style.backgroundColor = backgroundUrl;
      } else {
        style.backgroundImage = `url(${backgroundUrl})`;
        style.backgroundSize = 'cover';
        style.backgroundPosition = 'center';
      }
    } else {
      style.backgroundColor = currentTheme.background;
    }
    return style;
  }, [backgroundUrl, currentTheme]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" data-testid="mindmap-editor">
      <MindMapToolbar
        title={title}
        visibility={visibility}
        isDirty={isDirty}
        projectId={projectId}
        projectName={projectName}
        onTitleChange={handleTitleChange}
        onVisibilityChange={handleVisibilityChange}
        onSave={saveNow}
        onToggleStyling={() => setShowStyling(v => !v)}
        onOpenShare={() => setShowShare(true)}
        onOpenConvert={() => setShowConvert(true)}
      />

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={handleNodeClick}
            onNodeContextMenu={handleNodeContextMenu}
            onPaneClick={handlePaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            colorMode="light"
            nodesFocusable={false}
            multiSelectionKeyCode="Meta"
            deleteKeyCode={null}
            style={reactFlowStyle}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#94A3B8" className="opacity-30" />
            <Controls
              showInteractive={false}
              className="!rounded-xl !border-gray-200 !shadow-lg dark:!border-gray-700 dark:!bg-gray-900"
            />
            <MiniMap
              nodeColor={() => currentTheme.nodeColors[0]}
              className="!rounded-xl !border-gray-200 !shadow-lg dark:!border-gray-700 dark:!bg-gray-900"
              maskColor="rgba(0,0,0,0.08)"
            />
          </ReactFlow>

          {contextMenu && (
            <NodeContextMenu
              nodeId={contextMenu.nodeId}
              x={contextMenu.x}
              y={contextMenu.y}
              onClose={() => setContextMenu(null)}
              onColorChange={handleContextMenuColorChange}
              onAddNote={handleAddNote}
            />
          )}
        </div>

        <StylingPanel
          open={showStyling}
          onClose={() => setShowStyling(false)}
          currentThemeId={currentThemeId}
          onThemeChange={handleThemeChange}
          backgroundUrl={backgroundUrl}
          onBackgroundChange={handleBackgroundChange}
          selectedNodeColor={selectedNodeColor}
          onNodeColorChange={handleNodeColorChange}
        />
      </div>

      <ConvertToTasksDialog
        mindmapId={id || ''}
        open={showConvert}
        onClose={() => setShowConvert(false)}
        onSaveFirst={saveNow}
      />

      <ShareDialog
        mindmapId={id || ''}
        title={title}
        open={showShare}
        onClose={() => setShowShare(false)}
      />
    </div>
  );
}

export function MindMapEditorPage() {
  return (
    <ReactFlowProvider>
      <MindMapEditorInner />
    </ReactFlowProvider>
  );
}

export default MindMapEditorPage;
