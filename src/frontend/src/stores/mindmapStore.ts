import { create } from 'zustand';
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from '@xyflow/react';
import { nanoid } from 'nanoid';

export interface MindMapNodeData {
  label: string;
  notes?: string;
  url?: string;
  color?: string;
  textColor?: string;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string;
  icon?: string;
  isCollapsed?: boolean;
  [key: string]: unknown;
}

interface MindmapState {
  nodes: Node<MindMapNodeData>[];
  edges: Edge[];
  selectedNodeIds: string[];
  isDirty: boolean;
  currentThemeId: string;

  setNodes: (nodes: Node<MindMapNodeData>[]) => void;
  setEdges: (edges: Edge[]) => void;
  setCurrentThemeId: (id: string) => void;
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: OnConnect;

  addChildNode: (parentId: string) => string | null;
  addSiblingNode: (nodeId: string) => string | null;
  updateNodeData: (nodeId: string, data: Partial<MindMapNodeData>) => void;
  deleteNode: (nodeId: string) => void;
  toggleCollapse: (nodeId: string) => void;
  setSelectedNodeIds: (ids: string[]) => void;
  markClean: () => void;
}

const NODE_COLORS = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
  '#14B8A6', '#E11D48',
];

function getColorForDepth(depth: number): string {
  return NODE_COLORS[depth % NODE_COLORS.length];
}

function getNodeDepth(nodeId: string, edges: Edge[], visited = new Set<string>()): number {
  if (visited.has(nodeId)) return 0;
  visited.add(nodeId);
  const parentEdge = edges.find(e => e.target === nodeId);
  if (!parentEdge) return 0;
  return 1 + getNodeDepth(parentEdge.source, edges, visited);
}

export const useMindmapStore = create<MindmapState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeIds: [],
  isDirty: false,
  currentThemeId: 'meister',

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setCurrentThemeId: (id) => set({ currentThemeId: id }),

  onNodesChange: (changes) => {
    set({
      nodes: applyNodeChanges(changes, get().nodes) as Node<MindMapNodeData>[],
      isDirty: true,
    });
  },

  onEdgesChange: (changes) => {
    set({
      edges: applyEdgeChanges(changes, get().edges),
      isDirty: true,
    });
  },

  onConnect: (connection) => {
    set({
      edges: addEdge(connection, get().edges),
      isDirty: true,
    });
  },

  addChildNode: (parentId) => {
    const { nodes, edges } = get();
    const parent = nodes.find(n => n.id === parentId);
    if (!parent) return null;

    const newId = nanoid(8);
    const childCount = edges.filter(e => e.source === parentId).length;
    const depth = getNodeDepth(parentId, edges) + 1;

    const newNode: Node<MindMapNodeData> = {
      id: newId,
      type: 'mindmapNode',
      position: {
        x: parent.position.x + 250,
        y: parent.position.y + childCount * 80 - 40,
      },
      data: {
        label: '',
        color: getColorForDepth(depth),
      },
    };

    const newEdge: Edge = {
      id: `e-${parentId}-${newId}`,
      source: parentId,
      target: newId,
      type: 'mindmapEdge',
      style: { stroke: getColorForDepth(depth), strokeWidth: 2 },
    };

    set({
      nodes: [...nodes, newNode],
      edges: [...edges, newEdge],
      selectedNodeIds: [newId],
      isDirty: true,
    });
    return newId;
  },

  addSiblingNode: (nodeId) => {
    const { edges } = get();
    const parentEdge = edges.find(e => e.target === nodeId);
    if (!parentEdge) return null;
    return get().addChildNode(parentEdge.source);
  },

  updateNodeData: (nodeId, data) => {
    set({
      nodes: get().nodes.map(n =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
      isDirty: true,
    });
  },

  deleteNode: (nodeId) => {
    if (nodeId === 'root') return;
    const { nodes, edges } = get();
    const descendantIds = new Set<string>();
    const findDescendants = (id: string) => {
      edges.filter(e => e.source === id).forEach(e => {
        descendantIds.add(e.target);
        findDescendants(e.target);
      });
    };
    findDescendants(nodeId);
    descendantIds.add(nodeId);

    set({
      nodes: nodes.filter(n => !descendantIds.has(n.id)),
      edges: edges.filter(e => !descendantIds.has(e.source) && !descendantIds.has(e.target)),
      isDirty: true,
    });
  },

  toggleCollapse: (nodeId) => {
    const { nodes } = get();
    set({
      nodes: nodes.map(n =>
        n.id === nodeId
          ? { ...n, data: { ...n.data, isCollapsed: !n.data.isCollapsed } }
          : n
      ),
      isDirty: true,
    });
  },

  setSelectedNodeIds: (ids) => set({ selectedNodeIds: ids }),
  markClean: () => set({ isDirty: false }),
}));
