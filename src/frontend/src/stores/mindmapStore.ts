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
  side?: 'left' | 'right' | 'auto';
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
  clearNodeAndEdgeStyles: () => void;
  markClean: () => void;
}

function getParentId(nodeId: string, edges: Edge[]): string | null {
  const parentEdge = edges.find(e => e.target === nodeId);
  return parentEdge?.source ?? null;
}

function getChildIds(nodeId: string, edges: Edge[]): string[] {
  return edges.filter(e => e.source === nodeId).map(e => e.target);
}

function getSiblingIds(nodeId: string, nodes: Node<MindMapNodeData>[], edges: Edge[]): string[] {
  const parentId = getParentId(nodeId, edges);
  if (!parentId) return [];
  const childIds = getChildIds(parentId, edges);
  return childIds.filter(id => nodes.some(n => n.id === id));
}

export const useMindmapStore = create<MindmapState>((set, get) => ({
  nodes: [],
  edges: [],
  selectedNodeIds: [],
  isDirty: false,
  currentThemeId: 'clean',

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setCurrentThemeId: (id) => set({ currentThemeId: id }),

  onNodesChange: (changes) => {
    const updated = applyNodeChanges(changes, get().nodes) as Node<MindMapNodeData>[];
    const root = updated.find(n => n.id === 'root');
    let currentEdges = get().edges;
    let edgesChanged = false;
    if (root) {
      for (const node of updated) {
        if (node.id === 'root') continue;
        const parentEdge = currentEdges.find(e => e.target === node.id);
        if (parentEdge?.source === 'root') {
          const newSide = node.position.x < root.position.x ? 'left' : 'right';
          if (node.data?.side !== newSide) {
            node.data = { ...node.data, side: newSide };
            currentEdges = currentEdges.map(e =>
              e.target === node.id && e.source === 'root'
                ? { ...e, sourceHandle: newSide }
                : e
            );
            edgesChanged = true;
          }
        }
      }
    }
    set({
      nodes: updated,
      ...(edgesChanged ? { edges: currentEdges } : {}),
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
    const isRoot = parentId === 'root';

    let side: 'left' | 'right';
    if (isRoot) {
      const existingChildren = edges.filter(e => e.source === 'root');
      const rightCount = existingChildren.filter(e => {
        const child = nodes.find(n => n.id === e.target);
        return child?.data?.side !== 'left';
      }).length;
      const leftCount = existingChildren.length - rightCount;
      side = rightCount <= leftCount ? 'right' : 'left';
    } else {
      side = parent.data?.side === 'left' ? 'left' : 'right';
    }

    const sameParentSameSide = edges
      .filter(e => e.source === parentId)
      .filter(e => {
        const child = nodes.find(n => n.id === e.target);
        return side === 'left' ? child?.data?.side === 'left' : child?.data?.side !== 'left';
      }).length;

    const xOffset = side === 'left' ? -250 : 250;

    const newNode: Node<MindMapNodeData> = {
      id: newId,
      type: 'mindmapNode',
      position: {
        x: parent.position.x + xOffset,
        y: parent.position.y + sameParentSameSide * 80 - 40,
      },
      data: {
        label: '',
        side,
      },
    };

    const newEdge: Edge = {
      id: `e-${parentId}-${newId}`,
      source: parentId,
      target: newId,
      type: 'mindmapEdge',
      ...(isRoot ? { sourceHandle: side } : {}),
    };

    set({
      nodes: [...nodes.map(n => ({ ...n, selected: false })), { ...newNode, selected: true }],
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
    const { nodes, edges, selectedNodeIds } = get();
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
      selectedNodeIds: selectedNodeIds.filter(id => !descendantIds.has(id)),
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

  clearNodeAndEdgeStyles: () => {
    const { nodes, edges } = get();
    set({
      nodes: nodes.map(n => {
        const { color, textColor, fontSize, fontFamily, fontWeight, ...restData } = n.data;
        return { ...n, data: restData as MindMapNodeData };
      }),
      edges: edges.map(e => {
        const { style: _s, ...rest } = e;
        return rest;
      }),
      isDirty: true,
    });
  },

  markClean: () => set({ isDirty: false }),
}));

export { getParentId, getChildIds, getSiblingIds };
