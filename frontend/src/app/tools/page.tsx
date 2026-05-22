'use client';

import { useState, useRef, useMemo, useCallback, useEffect } from 'react';
import { Upload, RotateCcw, Download, ZoomIn, ZoomOut, FileText } from 'lucide-react';

interface Feature {
  name: string;
  type: string;
  start: number;
  end: number;
  strand: number;
  color: string;
}

// Predefined color palette for feature types
const TYPE_COLORS: Record<string, string> = {
  arg: '#EF4444', resistance: '#EF4444', amr: '#EF4444',
  is: '#F59E0B', mobile_element: '#F59E0B', insertion: '#F59E0B', transposon: '#F59E0B',
  integron: '#8B5CF6', integrase: '#A855F7',
  prophage: '#EC4899', phage: '#EC4899',
  trna: '#10B981', rrna: '#06B6D4',
  cds: '#6366F1', gene: '#6366F1',
  replicon: '#6366F1', orit: '#EC4899',
  relaxase: '#06B6D4', t4ss: '#10B981', mpf: '#10B981',
  crispr: '#F472B6', defense: '#D946EF',
  virulence: '#FB923C',
};

function getColor(type: string): string {
  const lower = type.toLowerCase();
  for (const [key, color] of Object.entries(TYPE_COLORS)) {
    if (lower.includes(key)) return color;
  }
  // Hash-based color for unknown types
  let hash = 0;
  for (let i = 0; i < type.length; i++) hash = type.charCodeAt(i) + ((hash << 5) - hash);
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 60%, 55%)`;
}

function parseTSV(text: string): { features: Feature[]; seqLength: number; errors: string[] } {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return { features: [], seqLength: 0, errors: ['File must have a header and at least one data row'] };

  const header = lines[0].split('\t').map((h) => h.trim().toLowerCase());
  const errors: string[] = [];

  // Find columns
  const nameCol = header.findIndex((h) => ['name', 'gene', 'feature', 'label', 'id'].includes(h));
  const typeCol = header.findIndex((h) => ['type', 'feature_type', 'category', 'class'].includes(h));
  const startCol = header.findIndex((h) => ['start', 'begin', 'pos_beg', 'start_pos'].includes(h));
  const endCol = header.findIndex((h) => ['end', 'stop', 'pos_end', 'end_pos'].includes(h));
  const strandCol = header.findIndex((h) => ['strand', 'direction', 'orientation'].includes(h));
  const colorCol = header.findIndex((h) => ['color', 'colour'].includes(h));

  if (startCol === -1 || endCol === -1) {
    return { features: [], seqLength: 0, errors: ['TSV must have "start" and "end" columns'] };
  }

  const features: Feature[] = [];
  let maxEnd = 0;

  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split('\t').map((c) => c.trim());
    if (cols.length <= Math.max(startCol, endCol)) continue;

    const start = parseInt(cols[startCol]);
    const end = parseInt(cols[endCol]);
    if (isNaN(start) || isNaN(end)) {
      errors.push(`Line ${i + 1}: invalid start/end`);
      continue;
    }

    const name = nameCol >= 0 ? cols[nameCol] : `feature_${i}`;
    const type = typeCol >= 0 ? cols[typeCol] : 'gene';
    const strandStr = strandCol >= 0 ? cols[strandCol] : '1';
    const strand = strandStr === '-1' || strandStr === '-' || strandStr === 'minus' || strandStr === 'reverse' ? -1 : 1;
    const color = colorCol >= 0 && cols[colorCol] ? cols[colorCol] : getColor(type);

    maxEnd = Math.max(maxEnd, end);
    features.push({ name, type, start: Math.min(start, end), end: Math.max(start, end), strand, color });
  }

  return { features: features.sort((a, b) => a.start - b.start), seqLength: maxEnd, errors };
}

// ─── Linear Drawing ───
function LinearMap({ features, seqLength, title }: { features: Feature[]; seqLength: number; title: string }) {
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(seqLength);
  const [hovered, setHovered] = useState<Feature | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragViewStart, setDragViewStart] = useState(0);

  const W = 1000;
  const MARGIN = { left: 30, right: 30, top: 35, bottom: 50 };
  const plotW = W - MARGIN.left - MARGIN.right;
  const TRACK_H = 22;
  const viewSpan = viewEnd - viewStart;
  const bpToX = (bp: number) => MARGIN.left + ((bp - viewStart) / viewSpan) * plotW;

  // Row assignment
  const rows = useMemo(() => {
    const visible = features.filter((f) => f.end > viewStart && f.start < viewEnd).sort((a, b) => a.start - b.start);
    const rowEnds: number[] = [];
    const assigned: { f: Feature; row: number }[] = [];
    for (const f of visible) {
      const x1 = bpToX(f.start);
      const x2 = bpToX(f.end);
      const needed = Math.max(x2, x1 + f.name.length * 5.5 + 10);
      let placed = false;
      for (let r = 0; r < rowEnds.length; r++) {
        if (x1 >= rowEnds[r] + 3) { rowEnds[r] = needed; assigned.push({ f, row: r }); placed = true; break; }
      }
      if (!placed) { assigned.push({ f, row: rowEnds.length }); rowEnds.push(needed); }
    }
    return { items: assigned, count: Math.max(rowEnds.length, 1) };
  }, [features, viewStart, viewEnd]);

  const svgH = MARGIN.top + rows.count * (TRACK_H + 16) + MARGIN.bottom;

  // Ticks
  const ticks = useMemo(() => {
    const range = viewEnd - viewStart;
    let step = 1000;
    if (range > 200000) step = 50000;
    else if (range > 100000) step = 25000;
    else if (range > 50000) step = 10000;
    else if (range > 20000) step = 5000;
    else if (range > 5000) step = 2000;
    const result: { pos: number; label: string }[] = [];
    const s = Math.ceil(viewStart / step) * step;
    for (let p = s; p <= viewEnd; p += step) {
      result.push({ pos: p, label: p >= 1000 ? `${(p / 1000).toFixed(p % 1000 === 0 ? 0 : 1)}k` : `${p}` });
    }
    return result;
  }, [viewStart, viewEnd]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = (e.target as SVGElement).closest('svg')?.getBoundingClientRect();
    if (!rect) return;
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left - MARGIN.left) / plotW));
    const mousePos = viewStart + frac * viewSpan;
    const factor = e.deltaY > 0 ? 1.3 : 1 / 1.3;
    const newSpan = Math.max(200, Math.min(seqLength, viewSpan * factor));
    setViewStart(Math.max(0, mousePos - frac * newSpan));
    setViewEnd(Math.min(seqLength, Math.max(0, mousePos - frac * newSpan) + newSpan));
  };

  const arrowPath = (x: number, y: number, w: number, h: number, strand: number) => {
    const tip = Math.min(7, w * 0.4);
    return strand >= 0
      ? `M ${x} ${y} L ${x + w - tip} ${y} L ${x + w} ${y + h / 2} L ${x + w - tip} ${y + h} L ${x} ${y + h} Z`
      : `M ${x + tip} ${y} L ${x + w} ${y} L ${x + w} ${y + h} L ${x + tip} ${y + h} L ${x} ${y + h / 2} Z`;
  };

  const handleExport = () => {
    const svg = document.getElementById('linear-map-svg');
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${title || 'genome_map'}.svg`; a.click();
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button onClick={() => { const mid = (viewStart+viewEnd)/2, s = viewSpan/2; setViewStart(Math.max(0,mid-s/2)); setViewEnd(Math.min(seqLength,mid+s/2)); }} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300"><ZoomIn className="w-4 h-4" /></button>
        <button onClick={() => { const mid = (viewStart+viewEnd)/2, s = viewSpan*2; setViewStart(Math.max(0,mid-s/2)); setViewEnd(Math.min(seqLength,mid+s/2)); }} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300"><ZoomOut className="w-4 h-4" /></button>
        <button onClick={() => { setViewStart(0); setViewEnd(seqLength); }} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300"><RotateCcw className="w-4 h-4" /></button>
        <button onClick={handleExport} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300"><Download className="w-4 h-4" /></button>
        <span className="text-xs text-gray-500 ml-2">Scroll to zoom, drag to pan</span>
      </div>
      {hovered && (
        <div className="mb-2 px-3 py-1.5 bg-gray-800/90 border border-gray-700 rounded text-xs inline-block">
          <span className="font-medium text-gray-100">{hovered.name}</span>
          <span className="text-gray-400 ml-2">{hovered.type}</span>
          <span className="text-gray-500 ml-2 font-mono">{hovered.start.toLocaleString()}-{hovered.end.toLocaleString()}</span>
        </div>
      )}
      <svg id="linear-map-svg" width="100%" viewBox={`0 0 ${W} ${svgH}`}
        className="border border-gray-800 rounded-lg bg-white cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onMouseDown={(e) => { setIsDragging(true); setDragStartX(e.clientX); setDragViewStart(viewStart); }}
        onMouseMove={(e) => { if (!isDragging) return; const dx = e.clientX - dragStartX; const shift = -dx * (viewSpan / plotW); const ns = Math.max(0, Math.min(seqLength - viewSpan, dragViewStart + shift)); setViewStart(ns); setViewEnd(ns + viewSpan); }}
        onMouseUp={() => setIsDragging(false)}
        onMouseLeave={() => { setIsDragging(false); setHovered(null); }}
      >
        <line x1={MARGIN.left} y1={MARGIN.top - 6} x2={MARGIN.left + plotW} y2={MARGIN.top - 6} stroke="#9CA3AF" strokeWidth={1} />
        {ticks.map((t, i) => { const x = bpToX(t.pos); return x >= MARGIN.left && x <= MARGIN.left + plotW ? (
          <g key={i}><line x1={x} y1={MARGIN.top - 10} x2={x} y2={MARGIN.top - 2} stroke="#9CA3AF" strokeWidth={0.5} /><text x={x} y={MARGIN.top - 14} textAnchor="middle" fill="#6B7280" fontSize={8} fontFamily="monospace">{t.label}</text></g>
        ) : null; })}
        {Array.from({ length: rows.count }).map((_, r) => (
          <line key={r} x1={MARGIN.left} y1={MARGIN.top + r * (TRACK_H + 16) + TRACK_H / 2} x2={MARGIN.left + plotW} y2={MARGIN.top + r * (TRACK_H + 16) + TRACK_H / 2} stroke="#E5E7EB" strokeWidth={1} />
        ))}
        {rows.items.map(({ f, row }, i) => {
          const x1 = Math.max(MARGIN.left, bpToX(f.start));
          const x2 = Math.min(MARGIN.left + plotW, bpToX(f.end));
          const w = Math.max(3, x2 - x1);
          const y = MARGIN.top + row * (TRACK_H + 16);
          return (
            <g key={i} onMouseEnter={() => setHovered(f)} onMouseLeave={() => setHovered(null)} className="cursor-pointer">
              <path d={arrowPath(x1, y, w, TRACK_H, f.strand)} fill={f.color} stroke={hovered === f ? '#000' : '#0002'} strokeWidth={hovered === f ? 1.5 : 0.5} opacity={0.9} />
              {w > 18 && <text x={x1 + w / 2} y={y + TRACK_H / 2 + 1} textAnchor="middle" dominantBaseline="middle" fill="#fff" fontSize={Math.min(10, w * 0.28)} fontWeight="bold" fontFamily="sans-serif" pointerEvents="none">{f.name.length * 5.5 < w ? f.name : f.name.slice(0, Math.floor(w / 5.5))}</text>}
            </g>
          );
        })}
        <text x={W / 2} y={svgH - 10} textAnchor="middle" fill="#9CA3AF" fontSize={9} fontFamily="monospace">
          {viewStart >= 1000 ? `${(viewStart/1000).toFixed(1)}k` : viewStart} — {viewEnd >= 1000 ? `${(viewEnd/1000).toFixed(1)}k` : viewEnd} ({viewSpan >= 1000 ? `${(viewSpan/1000).toFixed(1)} kb` : `${viewSpan} bp`})
        </text>
      </svg>
    </div>
  );
}

// ─── Circular Drawing ───
function CircularMap({ features, seqLength, title }: { features: Feature[]; seqLength: number; title: string }) {
  const [hovered, setHovered] = useState<Feature | null>(null);
  const SVG = 550;
  const CX = SVG / 2;
  const R = 200;
  const RING_W = 16;

  const polar = (deg: number, r: number): [number, number] => {
    const rad = ((deg - 90) * Math.PI) / 180;
    return [CX + r * Math.cos(rad), CX + r * Math.sin(rad)];
  };

  const arcPath = (sa: number, ea: number, ri: number, ro: number) => {
    let span = ea - sa;
    if (span < 1) { const mid = (sa + ea) / 2; sa = mid - 0.5; ea = mid + 0.5; span = 1; }
    const la = span > 180 ? 1 : 0;
    const [x1o, y1o] = polar(sa, ro); const [x2o, y2o] = polar(ea, ro);
    const [x1i, y1i] = polar(ea, ri); const [x2i, y2i] = polar(sa, ri);
    return `M ${x1o} ${y1o} A ${ro} ${ro} 0 ${la} 1 ${x2o} ${y2o} L ${x1i} ${y1i} A ${ri} ${ri} 0 ${la} 0 ${x2i} ${y2i} Z`;
  };

  // Assign tracks by type
  const typeOrder = useMemo(() => Array.from(new Set(features.map((f) => f.type))), [features]);
  const trackR = (typeIdx: number) => {
    if (typeIdx % 2 === 0) return R - RING_W / 2 - 3 - (Math.floor(typeIdx / 2)) * 18;
    return R + RING_W / 2 + 3 + (Math.floor(typeIdx / 2)) * 18;
  };

  // Ticks
  const ticks = useMemo(() => {
    const step = seqLength < 20000 ? 5000 : seqLength < 100000 ? 10000 : 25000;
    const result: { angle: number; label: string }[] = [];
    for (let p = 0; p < seqLength; p += step) {
      result.push({ angle: (p / seqLength) * 360, label: p >= 1000 ? `${Math.round(p / 1000)}k` : `${p}` });
    }
    return result;
  }, [seqLength]);

  const handleExport = () => {
    const svg = document.getElementById('circular-map-svg');
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${title || 'circular_map'}.svg`; a.click();
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button onClick={handleExport} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300"><Download className="w-4 h-4" /></button>
        <span className="text-xs text-gray-500">Hover for details. Export as SVG.</span>
      </div>
      {hovered && (
        <div className="mb-2 px-3 py-1.5 bg-gray-800/90 border border-gray-700 rounded text-xs inline-block">
          <span className="font-medium text-gray-100">{hovered.name}</span>
          <span className="text-gray-400 ml-2">{hovered.type}</span>
          <span className="text-gray-500 ml-2 font-mono">{hovered.start.toLocaleString()}-{hovered.end.toLocaleString()}</span>
        </div>
      )}
      <svg id="circular-map-svg" viewBox={`0 0 ${SVG} ${SVG}`} className="w-full max-w-[550px] border border-gray-800 rounded-lg bg-white">
        <circle cx={CX} cy={CX} r={R} fill="none" stroke="#D1D5DB" strokeWidth={RING_W} opacity={0.4} />
        {ticks.map((t, i) => {
          const [x1, y1] = polar(t.angle, R - RING_W / 2 - 2);
          const [x2, y2] = polar(t.angle, R + RING_W / 2 + 2);
          const [lx, ly] = polar(t.angle, R + RING_W / 2 + Math.max(...typeOrder.map((_, idx) => idx % 2 === 1 ? Math.floor(idx / 2) * 18 + 20 : 0), 14));
          return (
            <g key={i}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#9CA3AF" strokeWidth={0.5} />
              <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fill="#6B7280" fontSize={7} fontFamily="monospace">{t.label}</text>
            </g>
          );
        })}
        {features.map((f, i) => {
          const sa = (f.start / seqLength) * 360;
          const ea = (f.end / seqLength) * 360;
          const typeIdx = typeOrder.indexOf(f.type);
          const ri = trackR(typeIdx);
          const ro = ri + 14;
          return (
            <g key={i} onMouseEnter={() => setHovered(f)} onMouseLeave={() => setHovered(null)} className="cursor-pointer">
              <path d={arcPath(sa, ea, ri, ro)} fill={f.color} stroke={hovered === f ? '#000' : '#0001'} strokeWidth={hovered === f ? 1.5 : 0.3} opacity={0.9} />
            </g>
          );
        })}
        <text x={CX} y={CX - 8} textAnchor="middle" fill="#111827" fontSize={14} fontWeight="bold">{title || 'Map'}</text>
        <text x={CX} y={CX + 10} textAnchor="middle" fill="#6B7280" fontSize={10}>
          {seqLength >= 1e6 ? `${(seqLength / 1e6).toFixed(2)} Mb` : seqLength >= 1e3 ? `${(seqLength / 1e3).toFixed(1)} kb` : `${seqLength} bp`}
        </text>
      </svg>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-3">
        {typeOrder.map((type) => (
          <span key={type} className="inline-flex items-center gap-1 text-xs">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: getColor(type) }} />
            <span className="text-gray-400">{type}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Main Page ───
export default function ToolsPage() {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [seqLength, setSeqLength] = useState(0);
  const [mode, setMode] = useState<'linear' | 'circular'>('linear');
  const [title, setTitle] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [rawPreview, setRawPreview] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setTitle(file.name.replace(/\.(tsv|txt|csv)$/i, ''));
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      setRawPreview(text.split('\n').slice(0, 6).join('\n'));
      const { features: f, seqLength: sl, errors: errs } = parseTSV(text);
      setFeatures(f);
      setSeqLength(sl);
      setErrors(errs);
    };
    reader.readAsText(file);
  }, []);

  const handlePaste = useCallback((text: string) => {
    setRawPreview(text.split('\n').slice(0, 6).join('\n'));
    const { features: f, seqLength: sl, errors: errs } = parseTSV(text);
    setFeatures(f);
    setSeqLength(sl);
    setErrors(errs);
    if (!title) setTitle('pasted_data');
  }, [title]);

  const typeCount = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of features) counts[f.type] = (counts[f.type] || 0) + 1;
    return counts;
  }, [features]);

  const [toolTab, setToolTab] = useState<'map' | 'sra' | 'phenotype'>('map');

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-2">Tools</h1>
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1">
          <button onClick={() => setToolTab('map')} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === 'map' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
            Genome Map
          </button>
          <button onClick={() => setToolTab('phenotype')} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === 'phenotype' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
            Phenotype Prediction
          </button>
          <button onClick={() => setToolTab('sra')} className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${toolTab === 'sra' ? 'border-blue-500 text-blue-400' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
            SRA Submission
          </button>
        </div>
      </div>

      {toolTab === 'phenotype' && <PhenotypePredictionTool />}
      {toolTab === 'sra' && <SRASubmissionTool />}

      {toolTab === 'map' && <>
      <p className="text-gray-400 text-sm mb-6">Upload a TSV file with genomic features to draw a linear or circular map. Export as SVG for publication.</p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Upload card */}
        <div className="card lg:col-span-1">
          <h2 className="text-sm font-semibold text-gray-100 mb-3">Input</h2>

          <div
            className="border-2 border-dashed border-gray-700 rounded-lg p-6 text-center hover:border-blue-500/50 transition-colors cursor-pointer mb-4"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) { const inp = fileRef.current; if (inp) { const dt = new DataTransfer(); dt.items.add(f); inp.files = dt.files; inp.dispatchEvent(new Event('change', { bubbles: true })); } } }}
          >
            <Upload className="w-8 h-8 text-gray-500 mx-auto mb-2" />
            <p className="text-sm text-gray-400">Drop TSV file or click to browse</p>
            <p className="text-xs text-gray-600 mt-1">Required columns: start, end. Optional: name, type, strand, color</p>
          </div>
          <input ref={fileRef} type="file" accept=".tsv,.txt,.csv" onChange={handleFile} className="hidden" />

          <div className="mb-4">
            <label className="text-xs text-gray-400 block mb-1">Or paste TSV data:</label>
            <textarea
              rows={4}
              placeholder={"name\ttype\tstart\tend\tstrand\nblaCTX-M-15\tARG\t3428\t4306\t1\nISEcp1\tIS\t1000\t3400\t1"}
              className="input w-full text-xs font-mono"
              onBlur={(e) => { if (e.target.value.trim()) handlePaste(e.target.value); }}
            />
          </div>

          <div className="flex items-center gap-3 mb-4">
            <label className="text-xs text-gray-400">Title:</label>
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} className="input flex-1 text-sm" placeholder="Map title" />
          </div>

          <div className="flex items-center gap-3 mb-4">
            <label className="text-xs text-gray-400">Sequence length:</label>
            <input type="number" value={seqLength} onChange={(e) => setSeqLength(Math.max(0, parseInt(e.target.value) || 0))} className="input w-32 text-sm" />
          </div>

          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setMode('linear')}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'linear' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >Linear</button>
            <button
              onClick={() => setMode('circular')}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'circular' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
            >Circular</button>
          </div>

          {features.length > 0 && (
            <div className="text-xs text-gray-400 space-y-1">
              <p>{features.length} features loaded</p>
              {Object.entries(typeCount).map(([t, c]) => (
                <span key={t} className="inline-flex items-center gap-1 mr-3">
                  <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: getColor(t) }} />
                  {t}: {c}
                </span>
              ))}
            </div>
          )}

          {errors.length > 0 && (
            <div className="mt-3 p-2 bg-red-600/10 border border-red-600/30 rounded text-xs text-red-300">
              {errors.slice(0, 5).map((e, i) => <p key={i}>{e}</p>)}
              {errors.length > 5 && <p>...and {errors.length - 5} more errors</p>}
            </div>
          )}
        </div>

        {/* Map display */}
        <div className="lg:col-span-2">
          {features.length === 0 ? (
            <div className="card h-full flex items-center justify-center">
              <div className="text-center text-gray-500">
                <p className="text-lg mb-2">No features loaded</p>
                <p className="text-sm">Upload a TSV file or paste data to generate a map.</p>
                <div className="mt-4 p-4 bg-gray-800/50 rounded-lg text-left text-xs font-mono text-gray-400 max-w-md mx-auto">
                  <p className="text-gray-300 mb-1"># Example TSV format:</p>
                  <p>name{'\t'}type{'\t'}start{'\t'}end{'\t'}strand</p>
                  <p>blaCTX-M-15{'\t'}ARG{'\t'}3428{'\t'}4306{'\t'}1</p>
                  <p>ISEcp1{'\t'}IS{'\t'}1000{'\t'}3400{'\t'}1</p>
                  <p>intI1{'\t'}integrase{'\t'}5000{'\t'}6020{'\t'}1</p>
                  <p>tet(A){'\t'}ARG{'\t'}8200{'\t'}9400{'\t'}-1</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              {mode === 'linear' ? (
                <LinearMap features={features} seqLength={seqLength} title={title} />
              ) : (
                <CircularMap features={features} seqLength={seqLength} title={title} />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Preview table */}
      {features.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-100 mb-3">Features ({features.length})</h2>
          <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-900">
                <tr className="border-b border-gray-800">
                  <th className="text-left py-1.5 px-2 text-gray-400">Color</th>
                  <th className="text-left py-1.5 px-2 text-gray-400">Name</th>
                  <th className="text-left py-1.5 px-2 text-gray-400">Type</th>
                  <th className="text-right py-1.5 px-2 text-gray-400">Start</th>
                  <th className="text-right py-1.5 px-2 text-gray-400">End</th>
                  <th className="text-center py-1.5 px-2 text-gray-400">Strand</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {features.map((f, i) => (
                  <tr key={i} className="hover:bg-gray-800/30">
                    <td className="py-1 px-2"><span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: f.color }} /></td>
                    <td className="py-1 px-2 font-medium text-gray-200">{f.name}</td>
                    <td className="py-1 px-2 text-gray-400">{f.type}</td>
                    <td className="py-1 px-2 text-right font-mono text-gray-400">{f.start.toLocaleString()}</td>
                    <td className="py-1 px-2 text-right font-mono text-gray-400">{f.end.toLocaleString()}</td>
                    <td className="py-1 px-2 text-center text-gray-400">{f.strand === 1 ? '→' : '←'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </>}
    </div>
  );
}

// ─── Phenotype Prediction Tool ───
interface MLPrediction {
  id: string;
  antibiotic: string;
  drug_class: string;
  prediction: string;
  probability: number;
  confidence: string;
  key_genes: string[];
  key_mutations: string[];
}

interface MLPredictionResponse {
  species: string | null;
  mlst_st: string | null;
  n_antibiotics: number;
  n_resistant: number;
  n_susceptible: number;
  predictions: MLPrediction[];
}

function PhenotypePredictionTool() {
  const [samples, setSamples] = useState<{ id: string; name: string; status: string }[]>([]);
  const [selectedSample, setSelectedSample] = useState('');
  const [data, setData] = useState<MLPredictionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [predLoading, setPredLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'resistant' | 'susceptible'>('all');

  useEffect(() => {
    fetch('/api/pipeline/status')
      .then((r) => r.json())
      .then((d: { sample_id: string; sample_name: string; status: string }[]) => {
        const completed = d.filter((s) => s.status === 'complete');
        setSamples(completed.map((s) => ({ id: s.sample_id, name: s.sample_name, status: s.status })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function loadPredictions(sampleId: string) {
    setSelectedSample(sampleId);
    setData(null);
    setError(null);
    if (!sampleId) return;
    setPredLoading(true);
    try {
      const res = await fetch(`/api/samples/${sampleId}/ml-predictions`);
      if (!res.ok) throw new Error(await res.text());
      const d: MLPredictionResponse = await res.json();
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load predictions');
    } finally {
      setPredLoading(false);
    }
  }

  const filtered = data?.predictions.filter((p) => {
    if (filter === 'resistant') return p.prediction === 'Resistant';
    if (filter === 'susceptible') return p.prediction === 'Susceptible';
    return true;
  }) || [];

  if (loading) return <div className="flex items-center justify-center h-32"><div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        ML-based phenotype prediction using pre-trained Random Forest models. Select a completed sample to view per-antibiotic resistance predictions.
      </p>

      <div className="card">
        <div className="flex items-center gap-4">
          <label className="text-sm text-gray-300 font-medium whitespace-nowrap">Sample:</label>
          <select
            value={selectedSample}
            onChange={(e) => loadPredictions(e.target.value)}
            className="input flex-1 text-sm"
          >
            <option value="">Select a completed sample...</option>
            {samples.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
      </div>

      {predLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {data && data.predictions.length === 0 && (
        <div className="card text-center py-8 text-gray-500">
          No predictions available. This species may not be supported (Salmonella, E. coli, Klebsiella, S. aureus, A. baumannii), or the pipeline may not have completed annotation.
        </div>
      )}

      {data && data.predictions.length > 0 && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="card text-center">
              <p className="text-xs text-gray-400">Species</p>
              <p className="text-sm font-medium text-gray-100 mt-1">{data.species || 'Unknown'}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">MLST</p>
              <p className="text-sm font-medium text-gray-100 mt-1">ST{data.mlst_st || '?'}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">Resistant</p>
              <p className="text-2xl font-bold text-red-400 mt-1">{data.n_resistant}</p>
            </div>
            <div className="card text-center">
              <p className="text-xs text-gray-400">Susceptible</p>
              <p className="text-2xl font-bold text-green-400 mt-1">{data.n_susceptible}</p>
            </div>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2">
            {(['all', 'resistant', 'susceptible'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  filter === f ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {f === 'all' ? `All (${data.predictions.length})` : f === 'resistant' ? `Resistant (${data.n_resistant})` : `Susceptible (${data.n_susceptible})`}
              </button>
            ))}
          </div>

          {/* Predictions table */}
          <div className="card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Antibiotic</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Drug Class</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium">Prediction</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium">Probability</th>
                    <th className="text-center py-2 px-3 text-gray-400 font-medium">Confidence</th>
                    <th className="text-left py-2 px-3 text-gray-400 font-medium">Key Genes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {filtered.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-800/30">
                      <td className="py-2 px-3 font-medium text-gray-200 capitalize">
                        {p.antibiotic.replace(/_/g, ' ')}
                      </td>
                      <td className="py-2 px-3 text-gray-400 text-xs">{p.drug_class}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          p.prediction === 'Resistant'
                            ? 'bg-red-600/20 text-red-400 border border-red-500/30'
                            : 'bg-green-600/20 text-green-400 border border-green-500/30'
                        }`}>
                          {p.prediction === 'Resistant' ? 'R' : 'S'}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <div className="w-16 bg-gray-800 rounded-full h-1.5">
                            <div
                              className={`h-1.5 rounded-full ${p.prediction === 'Resistant' ? 'bg-red-500' : 'bg-green-500'}`}
                              style={{ width: `${Math.round(p.probability * 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-400 font-mono w-10">
                            {(p.probability * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`text-xs ${
                          p.confidence === 'High' ? 'text-green-400' : p.confidence === 'Moderate' ? 'text-yellow-400' : 'text-gray-500'
                        }`}>
                          {p.confidence}
                        </span>
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex flex-wrap gap-1">
                          {p.key_genes.map((g, i) => (
                            <span key={i} className="px-1.5 py-0.5 bg-gray-800 rounded text-xs text-gray-300 font-mono">{g}</span>
                          ))}
                          {p.key_mutations.map((m, i) => (
                            <span key={`m${i}`} className="px-1.5 py-0.5 bg-orange-900/30 rounded text-xs text-orange-300 font-mono">{m}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ─── SRA Submission Preparation Tool ───
interface SRASample {
  sample_id: string;
  sample_name: string;
  organism: string;
  collection_date: string;
  geo_loc_name: string;
  isolation_source: string;
  library_strategy: string;
  library_source: string;
  library_selection: string;
  library_layout: string;
  platform: string;
  instrument_model: string;
  filetype: string;
  filenames: string[];
  filename1: string;
  filename2: string;
}

const INSTRUMENT_OPTIONS: Record<string, string[]> = {
  ILLUMINA: ['Illumina MiSeq', 'Illumina HiSeq 2500', 'Illumina HiSeq 4000', 'Illumina NovaSeq 6000', 'NextSeq 500', 'NextSeq 2000', 'Illumina iSeq 100'],
  OXFORD_NANOPORE: ['MinION', 'GridION', 'PromethION', 'Flongle'],
  PACBIO_SMRT: ['PacBio RS II', 'Sequel', 'Sequel II', 'Sequel IIe', 'Revio'],
};

function SRASubmissionTool() {
  const [samples, setSamples] = useState<SRASample[]>([]);
  const [loading, setLoading] = useState(true);
  const [bioproject, setBioproject] = useState('');
  const [edited, setEdited] = useState<Record<string, Partial<SRASample>>>({});

  useEffect(() => {
    fetch('/api/sra-submission')
      .then((r) => r.json())
      .then((d) => { setSamples(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const getVal = (s: SRASample, field: keyof SRASample): string => {
    const override = edited[s.sample_id]?.[field];
    if (override !== undefined) return String(override);
    return String(s[field] || '');
  };

  const setVal = (sampleId: string, field: keyof SRASample, value: string) => {
    setEdited((prev) => ({
      ...prev,
      [sampleId]: { ...prev[sampleId], [field]: value },
    }));
  };

  const downloadBioSampleTSV = () => {
    const headers = ['sample_name', 'organism', 'collection_date', 'geo_loc_name', 'isolation_source', 'sample_type'];
    const rows = samples.map((s) => [
      getVal(s, 'sample_name'),
      getVal(s, 'organism'),
      getVal(s, 'collection_date') || 'missing',
      getVal(s, 'geo_loc_name') || 'missing',
      getVal(s, 'isolation_source') || 'missing',
      'whole genome sequencing',
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'biosample_attributes.tsv'; a.click();
  };

  const downloadSRAMetadataTSV = () => {
    const headers = ['bioproject_accession', 'biosample_accession', 'library_ID', 'title',
      'library_strategy', 'library_source', 'library_selection', 'library_layout',
      'platform', 'instrument_model', 'design_description', 'filetype', 'filename', 'filename2'];
    const rows = samples.map((s) => {
      const org = getVal(s, 'organism');
      const layout = getVal(s, 'library_layout');
      return [
        bioproject,
        '',  // biosample_accession — filled after BioSample submission
        getVal(s, 'sample_name'),
        `Whole genome sequencing of ${org || 'bacterial isolate'} ${getVal(s, 'sample_name')}`,
        getVal(s, 'library_strategy'),
        getVal(s, 'library_source'),
        getVal(s, 'library_selection'),
        layout,
        getVal(s, 'platform'),
        getVal(s, 'instrument_model'),
        `${org || 'Bacterial'} genomic DNA library`,
        getVal(s, 'filetype'),
        getVal(s, 'filename1'),
        layout === 'paired' ? getVal(s, 'filename2') : '',
      ];
    });
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'sra_metadata.tsv'; a.click();
  };

  if (loading) return <div className="flex items-center justify-center h-32"><div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Prepare BioSample and SRA metadata files for NCBI submission. Edit fields below, then download the TSV templates.
      </p>

      {samples.length === 0 ? (
        <div className="card text-center py-8 text-gray-500">No samples with FASTQ files found. Upload sequencing data first.</div>
      ) : (
        <>
          {/* BioProject */}
          <div className="card">
            <div className="flex items-center gap-4">
              <label className="text-sm text-gray-300 font-medium whitespace-nowrap">BioProject Accession:</label>
              <input type="text" value={bioproject} onChange={(e) => setBioproject(e.target.value)}
                placeholder="PRJNA000000 (leave blank if creating new)" className="input flex-1 text-sm" />
            </div>
          </div>

          {/* Download buttons */}
          <div className="flex gap-3">
            <button onClick={downloadBioSampleTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download BioSample TSV
            </button>
            <button onClick={downloadSRAMetadataTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download SRA Metadata TSV
            </button>
          </div>

          {/* Editable table */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">Sample Metadata ({samples.length} samples)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Sample</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Organism</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Collection Date</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Location</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Isolation Source</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Layout</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Platform</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Instrument</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Files</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {samples.map((s) => {
                    const plat = getVal(s, 'platform');
                    return (
                      <tr key={s.sample_id} className="hover:bg-gray-800/20">
                        <td className="py-2 px-2 font-medium text-gray-200 whitespace-nowrap">{s.sample_name}</td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'organism')} onChange={(e) => setVal(s.sample_id, 'organism', e.target.value)}
                            className="input text-xs w-40 py-1 px-2" placeholder="Organism" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'collection_date')} onChange={(e) => setVal(s.sample_id, 'collection_date', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="YYYY-MM-DD" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'geo_loc_name')} onChange={(e) => setVal(s.sample_id, 'geo_loc_name', e.target.value)}
                            className="input text-xs w-32 py-1 px-2" placeholder="Country: Region" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'isolation_source')} onChange={(e) => setVal(s.sample_id, 'isolation_source', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="e.g. blood" />
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'library_layout')} onChange={(e) => setVal(s.sample_id, 'library_layout', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="paired">paired</option>
                            <option value="single">single</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={plat} onChange={(e) => setVal(s.sample_id, 'platform', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="ILLUMINA">ILLUMINA</option>
                            <option value="OXFORD_NANOPORE">OXFORD_NANOPORE</option>
                            <option value="PACBIO_SMRT">PACBIO_SMRT</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'instrument_model')} onChange={(e) => setVal(s.sample_id, 'instrument_model', e.target.value)}
                            className="input text-xs py-1 px-2">
                            {(INSTRUMENT_OPTIONS[plat] || INSTRUMENT_OPTIONS.ILLUMINA).map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-2 text-gray-400 whitespace-nowrap">
                          {s.filenames.slice(0, 2).map((f, i) => (
                            <div key={i} className="truncate max-w-[150px]" title={f}>{f}</div>
                          ))}
                          {s.filenames.length > 2 && <div className="text-gray-600">+{s.filenames.length - 2} more</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Instructions */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">SRA Submission Steps</h2>
            <ol className="list-decimal list-inside space-y-2 text-sm text-gray-400">
              <li>Create a <strong className="text-gray-200">BioProject</strong> at <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">NCBI Submission Portal</a> (if you don't have one)</li>
              <li>Download and submit the <strong className="text-gray-200">BioSample TSV</strong> — this registers your samples and gives you BioSample accessions</li>
              <li>Enter your BioProject accession above, then download the <strong className="text-gray-200">SRA Metadata TSV</strong></li>
              <li>Fill in the BioSample accessions in the SRA metadata file</li>
              <li>Upload your FASTQ files and the SRA metadata to the <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">SRA submission wizard</a></li>
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
