'use client';

import { useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

interface PangenomeStats { total_genes: number; core: number; accessory: number; unique: number; n_samples: number }
interface PangenomeFeature { start: number; end: number; hash: string; strand: number; type: string; name: string | null; n_samples: number }
interface PangenomeRingSegment { start: number; end: number; present: boolean }
interface PangenomeRing { name: string; sample_id: string; gene_count: number; shared_with_ref: number; segments: PangenomeRingSegment[] }
interface PangenomeFreq { count: number; genes: number }
interface PangenomeData {
  reference: { name: string; sample_id: string; total_length: number; gene_count: number };
  samples: { name: string; sample_id: string; gene_count: number }[];
  stats: PangenomeStats;
  rings: { reference_features: PangenomeFeature[]; sample_rings: PangenomeRing[]; total_length: number };
  gene_frequency: PangenomeFreq[];
  error?: string;
}

const PAN_COLORS: Record<string, string> = {
  core: '#3B82F6',
  accessory: '#9CA3AF',
  arg: '#EF4444',
  vf: '#FB923C',
};

export default function PangenomeTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<PangenomeData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredGene, setHoveredGene] = useState<PangenomeFeature | null>(null);
  const [zoom, setZoom] = useState(1.0);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/pangenome', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      const d = await res.json();
      if (d.error) { setError(d.error); return; }
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  function renderCircularMap() {
    if (!data) return null;
    const { rings, reference } = data;
    const { reference_features, sample_rings, total_length } = rings;

    const nRings = sample_rings.length;
    const size = Math.max(700, 500 + nRings * 50);
    const cx = size / 2;
    const cy = size / 2;
    const refRadius = 160;
    const ringWidth = 18;
    const ringGap = 6;

    function toAngle(pos: number): number {
      return (pos / total_length) * 360 - 90;
    }

    function arcPath(r: number, startAngle: number, endAngle: number): string {
      const s = (startAngle * Math.PI) / 180;
      const e = (endAngle * Math.PI) / 180;
      const x1 = cx + r * Math.cos(s);
      const y1 = cy + r * Math.sin(s);
      const x2 = cx + r * Math.cos(e);
      const y2 = cy + r * Math.sin(e);
      const large = endAngle - startAngle > 180 ? 1 : 0;
      return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
    }

    // Merge adjacent features of same type into blocks for performance
    function mergeFeatures(feats: PangenomeFeature[]): { start: number; end: number; type: string; name: string | null; n_samples: number }[] {
      if (feats.length === 0) return [];
      const merged: { start: number; end: number; type: string; name: string | null; n_samples: number }[] = [];
      let cur = { start: feats[0].start, end: feats[0].end, type: feats[0].type, name: feats[0].name, n_samples: feats[0].n_samples };
      for (let i = 1; i < feats.length; i++) {
        const f = feats[i];
        // Merge if same type (except ARG/VF which stay individual) and close together
        if (f.type === cur.type && f.type !== 'arg' && f.type !== 'vf' && f.start - cur.end < total_length * 0.002) {
          cur.end = f.end;
        } else {
          merged.push(cur);
          cur = { start: f.start, end: f.end, type: f.type, name: f.name, n_samples: f.n_samples };
        }
      }
      merged.push(cur);
      return merged;
    }

    // Merge consecutive present segments for sample rings
    function mergeSegments(segs: PangenomeRingSegment[]): { start: number; end: number }[] {
      const present = segs.filter((s) => s.present);
      if (present.length === 0) return [];
      const merged: { start: number; end: number }[] = [];
      let cur = { start: present[0].start, end: present[0].end };
      for (let i = 1; i < present.length; i++) {
        if (present[i].start - cur.end < total_length * 0.002) {
          cur.end = present[i].end;
        } else {
          merged.push(cur);
          cur = { start: present[i].start, end: present[i].end };
        }
      }
      merged.push(cur);
      return merged;
    }

    const mergedRef = mergeFeatures(reference_features);
    const mergedRings = sample_rings.map((ring) => ({ ...ring, mergedSegs: mergeSegments(ring.segments) }));

    return (
      <svg id="pangenome-svg" width={size} height={size} className="rounded-lg" style={{ background: '#0F172A' }}>
        {/* Reference ring (innermost) */}
        <circle cx={cx} cy={cy} r={refRadius} fill="none" stroke="#374151" strokeWidth={ringWidth} />
        {mergedRef.map((feat, i) => {
          const a1 = toAngle(feat.start);
          const a2 = toAngle(feat.end);
          if (a2 - a1 < 0.05) return null;
          const color = PAN_COLORS[feat.type] || PAN_COLORS.accessory;
          const isSpecial = feat.type === 'arg' || feat.type === 'vf';
          return (
            <path key={`ref-${i}`} d={arcPath(refRadius, a1, a2)}
              stroke={color} strokeWidth={isSpecial ? ringWidth + 2 : ringWidth - 1} fill="none" opacity={isSpecial ? 1 : 0.8}
              {...(isSpecial ? {
                onMouseEnter: () => setHoveredGene(feat as any),
                onMouseLeave: () => setHoveredGene(null),
                style: { cursor: 'pointer' },
              } : {})}
            >
              {isSpecial && <title>{feat.name} ({feat.type.toUpperCase()})</title>}
            </path>
          );
        })}

        {/* Sample rings (outer) */}
        {mergedRings.map((ring, rIdx) => {
          const r = refRadius + (rIdx + 1) * (ringWidth + ringGap);
          return (
            <g key={ring.sample_id}>
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1F2937" strokeWidth={ringWidth} />
              {ring.mergedSegs.map((seg, sIdx) => {
                const a1 = toAngle(seg.start);
                const a2 = toAngle(seg.end);
                if (a2 - a1 < 0.05) return null;
                return (
                  <path key={`r${rIdx}-s${sIdx}`} d={arcPath(r, a1, a2)}
                    stroke="#3B82F6" strokeWidth={ringWidth - 1} fill="none" opacity={0.6} />
                );
              })}
              {/* Ring label — small colored tick at top + name listed in legend below */}
            </g>
          );
        })}

        {/* Center text */}
        <text x={cx} y={cy - 14} textAnchor="middle" fill="#FFFFFF" fontSize="14" fontWeight="bold">
          {reference.name} (ref)
        </text>
        <text x={cx} y={cy + 4} textAnchor="middle" fill="#CBD5E1" fontSize="12">
          {reference.gene_count} genes
        </text>
        <text x={cx} y={cy + 20} textAnchor="middle" fill="#CBD5E1" fontSize="12">
          {(reference.total_length / 1e6).toFixed(2)} Mb
        </text>

        {/* Ring labels — stacked at top-right outside the outermost ring */}
        {sample_rings.map((ring, rIdx) => {
          const labelY = 24 + rIdx * 18;
          return (
            <g key={`label-${rIdx}`}>
              {/* Color indicator matching the ring */}
              <rect x={size - 140} y={labelY - 6} width={12} height={12} rx={2} fill="#3B82F6" opacity={0.7} />
              <text x={size - 124} y={labelY + 3} fill="#F1F5F9" fontSize="12" textAnchor="start">
                {ring.name}
              </text>
            </g>
          );
        })}
      </svg>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Circular pangenome map (BRIG-style). Reference genome = inner ring, each additional isolate = outer ring.
        Colored by gene type: <span className="text-blue-400">core</span>, <span className="text-gray-400">accessory</span>,
        <span className="text-red-400"> ARG</span>, <span className="text-orange-400">virulence</span>.
        Gaps in outer rings = missing genes.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length < 2 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Computing...' : `Run Pangenome (${picker.selectedIds.length} selected)`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {data && (
        <>
          {/* Stats cards */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <div className="card text-center">
              <p className="text-xl font-bold text-white">{data.stats.total_genes}</p>
              <p className="text-xs text-gray-400">Total Genes</p>
            </div>
            <div className="card text-center">
              <p className="text-xl font-bold text-blue-400">{data.stats.core}</p>
              <p className="text-xs text-gray-400">Core ({(data.stats.core / data.stats.total_genes * 100).toFixed(0)}%)</p>
            </div>
            <div className="card text-center">
              <p className="text-xl font-bold text-gray-400">{data.stats.accessory}</p>
              <p className="text-xs text-gray-400">Accessory</p>
            </div>
            <div className="card text-center">
              <p className="text-xl font-bold text-yellow-400">{data.stats.unique}</p>
              <p className="text-xs text-gray-400">Unique</p>
            </div>
            <div className="card text-center">
              <p className="text-xl font-bold text-gray-300">{data.stats.n_samples}</p>
              <p className="text-xs text-gray-400">Samples</p>
            </div>
          </div>

          {/* Circular map + hover detail */}
          <div className="card">
            <div className="flex items-start gap-6">
              <div className="flex-shrink-0 relative">
                <div className="absolute top-2 left-2 z-10 flex flex-col gap-1">
                  <button onClick={() => setZoom((z) => Math.min(z + 0.25, 3))} className="w-7 h-7 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-bold border border-gray-700">+</button>
                  <button onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))} className="w-7 h-7 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-bold border border-gray-700">−</button>
                  <button onClick={() => setZoom(1)} className="w-7 h-7 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 text-[9px] border border-gray-700">1:1</button>
                  <button onClick={() => {
                    const svg = document.querySelector('#pangenome-svg');
                    if (!svg) return;
                    const serializer = new XMLSerializer();
                    const svgStr = serializer.serializeToString(svg);
                    const blob = new Blob([svgStr], { type: 'image/svg+xml' });
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = 'pangenome.svg';
                    a.click();
                    URL.revokeObjectURL(a.href);
                  }} className="w-7 h-7 rounded bg-gray-800 hover:bg-gray-700 text-gray-400 border border-gray-700 flex items-center justify-center" title="Download SVG">
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </div>
                <div className="overflow-hidden relative" style={{ maxWidth: '750px', maxHeight: '750px', cursor: zoom > 1 ? 'grab' : 'default' }}
                  onMouseDown={(e) => {
                    if (zoom <= 1) return;
                    e.preventDefault();
                    const el = e.currentTarget;
                    const inner = el.firstElementChild as HTMLElement;
                    if (!inner) return;
                    el.style.cursor = 'grabbing';
                    const startX = e.clientX;
                    const startY = e.clientY;
                    const currentTransform = inner.style.transform;
                    const match = currentTransform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/);
                    const tx0 = match ? parseFloat(match[1]) : 0;
                    const ty0 = match ? parseFloat(match[2]) : 0;
                    const onMove = (ev: MouseEvent) => {
                      const dx = ev.clientX - startX;
                      const dy = ev.clientY - startY;
                      inner.style.transform = `translate(${tx0 + dx}px, ${ty0 + dy}px) scale(${zoom})`;
                    };
                    const onUp = () => {
                      el.style.cursor = 'grab';
                      window.removeEventListener('mousemove', onMove);
                      window.removeEventListener('mouseup', onUp);
                    };
                    window.addEventListener('mousemove', onMove);
                    window.addEventListener('mouseup', onUp);
                  }}>
                  <div style={{ transform: `scale(${zoom})`, transformOrigin: 'center center', transition: 'transform 0.15s' }}>
                    {renderCircularMap()}
                  </div>
                </div>
              </div>
              <div className="flex-1 space-y-4">
                {/* Legend */}
                <div>
                  <h3 className="text-xs font-semibold text-gray-300 mb-2">Legend</h3>
                  <div className="space-y-1 text-xs">
                    <div className="flex items-center gap-2"><span className="w-3 h-3 rounded" style={{ background: '#3B82F6' }} /> Core gene (all samples)</div>
                    <div className="flex items-center gap-2"><span className="w-3 h-3 rounded" style={{ background: '#9CA3AF' }} /> Accessory gene</div>
                    <div className="flex items-center gap-2"><span className="w-3 h-3 rounded" style={{ background: '#EF4444' }} /> Resistance gene (ARG)</div>
                    <div className="flex items-center gap-2"><span className="w-3 h-3 rounded" style={{ background: '#FB923C' }} /> Virulence factor</div>
                    <div className="flex items-center gap-2"><span className="w-3 h-1 bg-gray-700 rounded" /> Gap = gene absent</div>
                  </div>
                </div>

                {/* Hovered gene detail */}
                {hoveredGene && (
                  <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
                    <p className="text-sm text-gray-200 font-medium">{hoveredGene.name || 'CDS'}</p>
                    <p className="text-xs text-gray-400">
                      Type: <span className={hoveredGene.type === 'arg' ? 'text-red-400' : hoveredGene.type === 'vf' ? 'text-orange-400' : 'text-blue-400'}>{hoveredGene.type}</span>
                    </p>
                    <p className="text-xs text-gray-400">Present in: {hoveredGene.n_samples}/{data.stats.n_samples} samples</p>
                    <p className="text-xs text-gray-500">Position: {hoveredGene.start}-{hoveredGene.end}</p>
                  </div>
                )}

                {/* Sample comparison table */}
                <div>
                  <h3 className="text-xs font-semibold text-gray-300 mb-2">Sample Comparison</h3>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-800">
                        <th className="text-left px-2 py-1 text-gray-400">Sample</th>
                        <th className="text-center px-2 py-1 text-gray-400">Genes</th>
                        <th className="text-center px-2 py-1 text-gray-400">Shared w/ Ref</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-gray-800/30">
                        <td className="px-2 py-1 text-gray-200 font-medium">{data.reference.name} (ref)</td>
                        <td className="px-2 py-1 text-center text-gray-300">{data.reference.gene_count}</td>
                        <td className="px-2 py-1 text-center text-gray-300">—</td>
                      </tr>
                      {data.rings.sample_rings.map((r) => (
                        <tr key={r.sample_id} className="border-b border-gray-800/30">
                          <td className="px-2 py-1 text-gray-200">{r.name}</td>
                          <td className="px-2 py-1 text-center text-gray-300">{r.gene_count}</td>
                          <td className="px-2 py-1 text-center text-gray-300">{r.shared_with_ref} ({(r.shared_with_ref / data.reference.gene_count * 100).toFixed(0)}%)</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Gene frequency chart */}
                <div>
                  <h3 className="text-xs font-semibold text-gray-300 mb-2">Gene Frequency</h3>
                  <div className="flex items-end gap-1 h-20">
                    {data.gene_frequency.map((f) => {
                      const maxGenes = Math.max(...data.gene_frequency.map((x) => x.genes));
                      const h = (f.genes / maxGenes) * 100;
                      return (
                        <div key={f.count} className="flex flex-col items-center flex-1" title={`${f.genes} genes in ${f.count} sample(s)`}>
                          <div className={`w-full rounded-t ${f.count === data.stats.n_samples ? 'bg-blue-500' : f.count === 1 ? 'bg-yellow-500' : 'bg-gray-500'}`}
                            style={{ height: `${h}%`, minHeight: '2px' }} />
                          <span className="text-[9px] text-gray-500 mt-0.5">{f.count}</span>
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-[9px] text-gray-600 text-center mt-1">Samples containing gene →</p>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {picker.selectedIds.length >= 2 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Run Pangenome&quot; to compute core/accessory genome.</div>
      )}
    </div>
  );
}
