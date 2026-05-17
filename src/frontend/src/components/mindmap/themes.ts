export interface MindMapTheme {
  id: string;
  name: string;
  background: string;
  nodeColors: string[];
  textColors: string[];
  fontFamily: string;
  nodeShape: 'rounded' | 'pill' | 'rectangle';
  borderRadius: string;
  edgeType: 'bezier' | 'step' | 'straight';
  edgeColors: string[];
  fontSize: { root: number; child: number; leaf: number };
  borderStyle: string;
  shadowStyle: string;
  edgeWidth: number;
  edgeOpacity: number;
  edgeDashArray: string;
}

export const THEMES: MindMapTheme[] = [
  {
    id: 'clean',
    name: 'Clean',
    background: '#FFFFFF',
    nodeColors: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899'],
    textColors: ['#FFFFFF', '#FFFFFF', '#1A1A1A', '#FFFFFF', '#FFFFFF', '#FFFFFF'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '12px',
    edgeType: 'bezier',
    edgeColors: ['#60A5FA', '#34D399', '#FBBF24', '#F87171', '#A78BFA', '#F472B6'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 2px 8px rgba(0,0,0,0.08)',
    edgeWidth: 2,
    edgeOpacity: 0.85,
    edgeDashArray: '',
  },
  {
    id: 'vivid',
    name: 'Vivid',
    background: '#FAFAFA',
    nodeColors: ['#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#F4A261', '#264653'],
    textColors: ['#FFFFFF', '#FFFFFF', '#FFFFFF', '#1A1A1A', '#1A1A1A', '#FFFFFF'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '14px',
    edgeType: 'bezier',
    edgeColors: ['#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#F4A261', '#264653'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 4px 16px rgba(0,0,0,0.12)',
    edgeWidth: 3,
    edgeOpacity: 0.9,
    edgeDashArray: '',
  },
  {
    id: 'ocean',
    name: 'Ozean',
    background: '#F0F4FA',
    nodeColors: ['#1B4965', '#2B6A8E', '#5FA8D3', '#62B6CB', '#BEE9E8', '#CAE9FF'],
    textColors: ['#FFFFFF', '#FFFFFF', '#FFFFFF', '#1A2A3A', '#1A2A3A', '#1A2A3A'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '14px',
    edgeType: 'bezier',
    edgeColors: ['#1B4965', '#2B6A8E', '#5FA8D3', '#62B6CB', '#8DD0C7', '#A8D8EA'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 3px 12px rgba(27,73,101,0.12)',
    edgeWidth: 2,
    edgeOpacity: 0.6,
    edgeDashArray: '',
  },
  {
    id: 'dark',
    name: 'Dark',
    background: '#0F172A',
    nodeColors: ['#F72585', '#B5179E', '#7209B7', '#560BAD', '#480CA8', '#3A0CA3'],
    textColors: ['#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '8px',
    edgeType: 'straight',
    edgeColors: ['#F72585', '#B5179E', '#7209B7', '#4CC9F0', '#4895EF', '#4361EE'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 0 24px rgba(247,37,133,0.25)',
    edgeWidth: 2.5,
    edgeOpacity: 0.8,
    edgeDashArray: '',
  },
  {
    id: 'pastel',
    name: 'Pastell',
    background: '#FEFCF9',
    nodeColors: ['#B8D4E3', '#D4B5D0', '#B8C9A3', '#E8C8A0', '#C4A5A5', '#A8C8C8'],
    textColors: ['#2D3748', '#2D3748', '#2D3748', '#2D3748', '#2D3748', '#2D3748'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'pill',
    borderRadius: '9999px',
    edgeType: 'bezier',
    edgeColors: ['#9BBFD4', '#C49DBF', '#9FB88A', '#D4B388', '#B08E8E', '#90B5B5'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 2px 10px rgba(0,0,0,0.05)',
    edgeWidth: 2,
    edgeOpacity: 0.5,
    edgeDashArray: '',
  },
  {
    id: 'earth',
    name: 'Erde',
    background: '#F5F2ED',
    nodeColors: ['#5F7161', '#6D8B74', '#A4B494', '#D0B49F', '#AB6B51', '#8B635C'],
    textColors: ['#FFFFFF', '#FFFFFF', '#2C2C2C', '#2C2C2C', '#FFFFFF', '#FFFFFF'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '16px',
    edgeType: 'bezier',
    edgeColors: ['#5F7161', '#6D8B74', '#A4B494', '#D0B49F', '#AB6B51', '#8B635C'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 3px 12px rgba(95,113,97,0.12)',
    edgeWidth: 2.5,
    edgeOpacity: 0.6,
    edgeDashArray: '',
  },
  {
    id: 'sunset',
    name: 'Sunset',
    background: '#FFF9F5',
    nodeColors: ['#D62828', '#F77F00', '#FCBF49', '#EAE2B7', '#BC4749', '#E76F51'],
    textColors: ['#FFFFFF', '#FFFFFF', '#2C1810', '#2C1810', '#FFFFFF', '#FFFFFF'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'pill',
    borderRadius: '9999px',
    edgeType: 'bezier',
    edgeColors: ['#D62828', '#F77F00', '#FCBF49', '#D4C99E', '#BC4749', '#E76F51'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: 'none',
    shadowStyle: '0 4px 14px rgba(214,40,40,0.1)',
    edgeWidth: 2.5,
    edgeOpacity: 0.65,
    edgeDashArray: '',
  },
  {
    id: 'mono',
    name: 'Mono',
    background: '#FFFFFF',
    nodeColors: ['#374151', '#6B7280', '#9CA3AF', '#4B5563', '#6B7280', '#374151'],
    textColors: ['#1F2937', '#1F2937', '#1F2937', '#1F2937', '#1F2937', '#1F2937'],
    fontFamily: "Inter, system-ui, sans-serif",
    nodeShape: 'rounded',
    borderRadius: '8px',
    edgeType: 'straight',
    edgeColors: ['#374151', '#6B7280', '#9CA3AF', '#4B5563', '#6B7280', '#374151'],
    fontSize: { root: 18, child: 14, leaf: 13 },
    borderStyle: '2px dashed',
    shadowStyle: 'none',
    edgeWidth: 1.5,
    edgeOpacity: 0.7,
    edgeDashArray: '6 4',
  },
];

export const DEFAULT_THEME_ID = 'clean';

export function getThemeById(id: string): MindMapTheme {
  return THEMES.find(t => t.id === id) || THEMES[0];
}
