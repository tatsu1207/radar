'use client';

import { useMemo, useState, useRef } from 'react';
import { Download, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react';

interface Feature {
  type: string;
  name: string;
  label: string;
  family: string;
  start: number;
  end: number;
  strand?: number;
}

interface LinearGenomeMapProps {
  title: string;
  subtitle?: string;
  length: number;
  features: Feature[];
  /** Optional: restrict view to a region */
  regionStart?: number;
  regionEnd?: number;
}

const TRACK_COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  arg:            { fill: '#EF4444', stroke: '#B91C1C', label: 'ARG' },
  virulence:      { fill: '#14B8A6', stroke: '#0D9488', label: 'Virulence' },
  bacmet:         { fill: '#A78BFA', stroke: '#7C3AED', label: 'Biocide/Metal' },
  mobile_element: { fill: '#F59E0B', stroke: '#B45309', label: 'IS Element' },
  integron:       { fill: '#8B5CF6', stroke: '#6D28D9', label: 'Integron' },
  integrase:      { fill: '#A855F7', stroke: '#7E22CE', label: 'Integrase' },
  attc:           { fill: '#60A5FA', stroke: '#2563EB', label: 'attC' },
  relaxase:       { fill: '#06B6D4', stroke: '#0891B2', label: 'Relaxase' },
  orit:           { fill: '#EC4899', stroke: '#BE185D', label: 'oriT' },
  t4ss:           { fill: '#10B981', stroke: '#047857', label: 'T4SS/MPF' },
  replicon:       { fill: '#6366F1', stroke: '#4338CA', label: 'Replicon' },
  prophage:       { fill: '#F472B6', stroke: '#DB2777', label: 'Prophage' },
  gene:           { fill: '#9CA3AF', stroke: '#6B7280', label: 'Gene' },
};

const MARGIN = { top: 40, right: 30, bottom: 60, left: 30 };
const TRACK_HEIGHT = 24;
const ARROW_TIP = 8;
const LABEL_FONT_SIZE = 10;

function formatBp(bp: number): string {
  if (bp >= 1e6) return `${(bp / 1e6).toFixed(2)} Mb`;
  if (bp >= 1e3) return `${(bp / 1e3).toFixed(1)} kb`;
  return `${bp} bp`;
}

function arrowPath(x: number, y: number, w: number, h: number, strand: number): string {
  const tip = Math.min(ARROW_TIP, w * 0.4);
  if (strand >= 0) {
    // Forward arrow →
    return `M ${x} ${y} L ${x + w - tip} ${y} L ${x + w} ${y + h / 2} L ${x + w - tip} ${y + h} L ${x} ${y + h} Z`;
  }
  // Reverse arrow ←
  return `M ${x + tip} ${y} L ${x + w} ${y} L ${x + w} ${y + h} L ${x + tip} ${y + h} L ${x} ${y + h / 2} Z`;
}

export default function LinearGenomeMap({
  title, subtitle, length, features, regionStart, regionEnd,
}: LinearGenomeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewStart, setViewStart] = useState(regionStart ?? 0);
  const [viewEnd, setViewEnd] = useState(regionEnd ?? length);
  const [hoveredFeature, setHoveredFeature] = useState<Feature | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragViewStart, setDragViewStart] = useState(0);

  const svgWidth = 900;
  const plotWidth = svgWidth - MARGIN.left - MARGIN.right;
  const viewSpan = viewEnd - viewStart;

  // Separate mobile_element features (rendered as background bands) from gene features (rendered as arrows)
  const bgFeatures = useMemo(() => features.filter((f) => f.type === 'mobile_element'), [features]);
  const geneFeatures = useMemo(() => features.filter((f) => f.type !== 'mobile_element'), [features]);

  // Assign gene features to rows to avoid overlaps
  const { rows, svgHeight } = useMemo(() => {
    const visibleFeatures = geneFeatures
      .filter((f) => f.end > viewStart && f.start < viewEnd)
      .sort((a, b) => a.start - b.start);

    const rowEnds: number[] = [];
    const assigned: { feature: Feature; row: number }[] = [];

    for (const f of visibleFeatures) {
      const fxStart = ((f.start - viewStart) / viewSpan) * plotWidth;
      const fxEnd = ((f.end - viewStart) / viewSpan) * plotWidth;
      const neededEnd = fxEnd;

      let placed = false;
      for (let r = 0; r < rowEnds.length; r++) {
        if (fxStart >= rowEnds[r] + 1) {
          rowEnds[r] = neededEnd;
          assigned.push({ feature: f, row: r });
          placed = true;
          break;
        }
      }
      if (!placed) {
        assigned.push({ feature: f, row: rowEnds.length });
        rowEnds.push(neededEnd);
      }
    }

    const numRows = Math.max(rowEnds.length, 1);
    const height = MARGIN.top + numRows * (TRACK_HEIGHT + 20) + MARGIN.bottom;
    return { rows: assigned, svgHeight: height };
  }, [geneFeatures, viewStart, viewEnd, viewSpan, plotWidth]);

  // Tick marks
  const ticks = useMemo(() => {
    const result: { pos: number; label: string }[] = [];
    const range = viewEnd - viewStart;
    let step = 1000;
    if (range > 200000) step = 50000;
    else if (range > 100000) step = 25000;
    else if (range > 50000) step = 10000;
    else if (range > 20000) step = 5000;
    else if (range > 5000) step = 2000;

    const start = Math.ceil(viewStart / step) * step;
    for (let pos = start; pos <= viewEnd; pos += step) {
      result.push({
        pos,
        label: pos >= 1000 ? `${(pos / 1000).toFixed(pos % 1000 === 0 ? 0 : 1)}k` : `${pos}`,
      });
    }
    return result;
  }, [viewStart, viewEnd]);

  const presentTypes = useMemo(() => Array.from(new Set(features.map((f) => f.type))), [features]);

  // Zoom
  const zoomIn = () => {
    const mid = (viewStart + viewEnd) / 2;
    const span = (viewEnd - viewStart) / 2;
    setViewStart(Math.max(0, mid - span / 2));
    setViewEnd(Math.min(length, mid + span / 2));
  };
  const zoomOut = () => {
    const mid = (viewStart + viewEnd) / 2;
    const span = (viewEnd - viewStart) * 2;
    setViewStart(Math.max(0, mid - span / 2));
    setViewEnd(Math.min(length, mid + span / 2));
  };
  const resetView = () => {
    setViewStart(regionStart ?? 0);
    setViewEnd(regionEnd ?? length);
  };

  // Pan via drag
  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    setIsDragging(true);
    setDragStartX(e.clientX);
    setDragViewStart(viewStart);
  };
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    const dx = e.clientX - dragStartX;
    const bpPerPx = viewSpan / plotWidth;
    const shift = -dx * bpPerPx;
    const newStart = Math.max(0, Math.min(length - viewSpan, dragViewStart + shift));
    setViewStart(newStart);
    setViewEnd(newStart + viewSpan);
  };
  const handleMouseUp = () => setIsDragging(false);

  // Scroll zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = (e.target as SVGElement).closest('svg')?.getBoundingClientRect();
    if (!rect) return;
    const mouseX = e.clientX - rect.left - MARGIN.left;
    const frac = Math.max(0, Math.min(1, mouseX / plotWidth));
    const mousePos = viewStart + frac * viewSpan;

    const factor = e.deltaY > 0 ? 1.3 : 1 / 1.3;
    const newSpan = Math.max(500, Math.min(length, viewSpan * factor));
    const newStart = Math.max(0, mousePos - frac * newSpan);
    const newEnd = Math.min(length, newStart + newSpan);
    setViewStart(newStart);
    setViewEnd(newEnd);
  };

  // Export SVG
  const handleExport = () => {
    // Select the main map SVG (not legend SVGs) by data attribute
    const svgEl = containerRef.current?.querySelector('svg[data-genome-map]') as SVGSVGElement | null;
    if (!svgEl) return;

    // Clone and add standalone attributes for proper rendering outside browser
    const clone = svgEl.cloneNode(true) as SVGSVGElement;
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', String(svgWidth));
    clone.setAttribute('height', String(svgHeight));

    // Add white background rect as first child
    const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bgRect.setAttribute('width', '100%');
    bgRect.setAttribute('height', '100%');
    bgRect.setAttribute('fill', 'white');
    clone.insertBefore(bgRect, clone.firstChild);

    const serializer = new XMLSerializer();
    const svgStr = '<?xml version="1.0" encoding="UTF-8"?>\n' + serializer.serializeToString(clone);
    const blob = new Blob([svgStr], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/\s+/g, '_')}_map.svg`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const bpToX = (bp: number) => MARGIN.left + ((bp - viewStart) / viewSpan) * plotWidth;

  return (
    <div className="card" ref={containerRef}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-base font-semibold text-gray-100">{title}</h3>
          {subtitle && <p className="text-xs text-gray-400">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={zoomIn} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300" title="Zoom in">
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button onClick={zoomOut} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300" title="Zoom out">
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button onClick={resetView} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300" title="Reset view">
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleExport} className="p-1.5 bg-gray-800 rounded hover:bg-gray-700 text-gray-300 ml-1" title="Export SVG">
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-2">
        {presentTypes.map((type) => {
          const c = TRACK_COLORS[type] || TRACK_COLORS.gene;
          return (
            <span key={type} className="inline-flex items-center gap-1 text-xs">
              <svg width={14} height={10}><path d={arrowPath(0, 0, 14, 10, 1)} fill={c.fill} stroke={c.stroke} strokeWidth={0.5} /></svg>
              <span className="text-gray-400">{c.label}</span>
            </span>
          );
        })}
      </div>

      {/* Tooltip */}
      <div className="mb-2 h-7">
        {hoveredFeature && (
          <div className="px-3 py-1.5 bg-gray-800/90 border border-gray-700 rounded text-xs inline-block">
            <span className="font-medium text-gray-100">{hoveredFeature.name}</span>
            <span className="text-gray-400 ml-2">{TRACK_COLORS[hoveredFeature.type]?.label || hoveredFeature.type}</span>
            {hoveredFeature.family && hoveredFeature.family !== hoveredFeature.name && (
              <span className="text-gray-500 ml-2">{hoveredFeature.family} family</span>
            )}
            {hoveredFeature.label && hoveredFeature.label !== hoveredFeature.name && !hoveredFeature.label.includes(hoveredFeature.name) && (
              <span className="text-gray-500 ml-2">{hoveredFeature.label}</span>
            )}
            <span className="text-gray-500 ml-2 font-mono">{hoveredFeature.start.toLocaleString()}-{hoveredFeature.end.toLocaleString()}</span>
          </div>
        )}
      </div>

      {/* SVG */}
      <svg
        data-genome-map="true"
        width="100%" viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="border border-gray-800 rounded-lg bg-white cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => { handleMouseUp(); setHoveredFeature(null); }}
        onWheel={handleWheel}
      >
        {/* Scale bar / axis */}
        <line x1={MARGIN.left} y1={MARGIN.top - 8} x2={MARGIN.left + plotWidth} y2={MARGIN.top - 8}
          stroke="#9CA3AF" strokeWidth={1} />
        {ticks.map((t, i) => {
          const x = bpToX(t.pos);
          if (x < MARGIN.left || x > MARGIN.left + plotWidth) return null;
          return (
            <g key={i}>
              <line x1={x} y1={MARGIN.top - 12} x2={x} y2={MARGIN.top - 4} stroke="#9CA3AF" strokeWidth={0.5} />
              <text x={x} y={MARGIN.top - 16} textAnchor="middle" fill="#6B7280" fontSize={8} fontFamily="monospace">{t.label}</text>
            </g>
          );
        })}

        {/* Backbone line per row */}
        {Array.from({ length: Math.max(1, rows.reduce((m, r) => Math.max(m, r.row + 1), 0)) }).map((_, r) => {
          const y = MARGIN.top + r * (TRACK_HEIGHT + 20) + TRACK_HEIGHT / 2;
          return <line key={r} x1={MARGIN.left} y1={y} x2={MARGIN.left + plotWidth} y2={y} stroke="#E5E7EB" strokeWidth={1} />;
        })}

        {/* Mobile element background bands */}
        {bgFeatures.filter((f) => f.end > viewStart && f.start < viewEnd).map((f, i) => {
          const x1 = Math.max(MARGIN.left, bpToX(f.start));
          const x2 = Math.min(MARGIN.left + plotWidth, bpToX(f.end));
          const w = Math.max(3, x2 - x1);
          const c = TRACK_COLORS[f.type] || TRACK_COLORS.gene;
          const numRows2 = Math.max(1, rows.reduce((m, r) => Math.max(m, r.row + 1), 0));
          const bandH = numRows2 * (TRACK_HEIGHT + 20);
          const isHov = hoveredFeature === f;
          return (
            <g key={`bg-${i}`}
              onMouseEnter={() => setHoveredFeature(f)}
              onMouseLeave={() => setHoveredFeature(null)}
              className="cursor-pointer"
            >
              <rect x={x1} y={MARGIN.top - 4} width={w} height={bandH + 8}
                fill={c.fill} opacity={isHov ? 0.18 : 0.1} rx={3}
                stroke={c.stroke} strokeWidth={isHov ? 1.5 : 0.5} strokeDasharray={isHov ? '' : '4 2'} />
              <text x={x1 + w / 2} y={MARGIN.top + bandH + 14}
                textAnchor="middle" fill={c.fill} fontSize={9} fontWeight="bold" fontFamily="sans-serif"
                pointerEvents="none">{f.name}</text>
            </g>
          );
        })}

        {/* Gene features as arrows */}
        {rows.map(({ feature: f, row }, i) => {
          const x1 = Math.max(MARGIN.left, bpToX(f.start));
          const x2 = Math.min(MARGIN.left + plotWidth, bpToX(f.end));
          const w = Math.max(3, x2 - x1);
          const y = MARGIN.top + row * (TRACK_HEIGHT + 20);
          const c = TRACK_COLORS[f.type] || TRACK_COLORS.gene;
          const strand = f.strand ?? 1;
          const isHovered = hoveredFeature === f;

          return (
            <g key={i}
              onMouseEnter={() => setHoveredFeature(f)}
              onMouseLeave={() => setHoveredFeature(null)}
              className="cursor-pointer"
            >
              <path
                d={arrowPath(x1, y, w, TRACK_HEIGHT, strand)}
                fill={c.fill}
                stroke={isHovered ? '#000' : c.stroke}
                strokeWidth={isHovered ? 1.5 : 0.8}
                opacity={isHovered ? 1 : 0.9}
              />
              {/* Label */}
              {w > 15 && (
                <text
                  x={x1 + w / 2}
                  y={y + TRACK_HEIGHT / 2 + 1}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#FFFFFF"
                  fontSize={Math.min(LABEL_FONT_SIZE, w * 0.3)}
                  fontWeight="bold"
                  fontFamily="sans-serif"
                  pointerEvents="none"
                >
                  {f.name.length * 5.5 < w ? f.name : f.name.slice(0, Math.floor(w / 5.5))}
                </text>
              )}
              {/* Label below for small features */}
              {w <= 15 && (
                <text
                  x={x1 + w / 2}
                  y={y + TRACK_HEIGHT + 10}
                  textAnchor="middle"
                  fill="#374151"
                  fontSize={7}
                  fontFamily="sans-serif"
                  pointerEvents="none"
                >
                  {f.name}
                </text>
              )}
            </g>
          );
        })}

        {/* View range label */}
        <text x={svgWidth / 2} y={svgHeight - 10} textAnchor="middle" fill="#9CA3AF" fontSize={9} fontFamily="monospace">
          {formatBp(viewStart)} — {formatBp(viewEnd)} ({formatBp(viewSpan)})
        </text>
      </svg>
      <p className="text-[10px] text-gray-600 mt-1">Scroll to zoom, drag to pan. Export as SVG for publication.</p>
    </div>
  );
}
