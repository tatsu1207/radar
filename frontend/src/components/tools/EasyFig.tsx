'use client';

import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

interface EasyFigContig { name: string; length: number }
interface EasyFigFeature { type: 'arg' | 'vf' | 'mge' | 'mrg'; name: string; contig: string; start: number; end: number }
interface EasyFigGenome { sample_name: string; sample_id: string; contigs: EasyFigContig[]; total_length: number; features?: EasyFigFeature[] }
interface EasyFigBlock { query_contig: string; subject_contig: string; identity: number; length: number; query_start: number; query_end: number; subject_start: number; subject_end: number; inverted: boolean }
interface EasyFigAlignment { query_idx: number; subject_idx: number; blocks: EasyFigBlock[] }
interface EasyFigData { genomes: EasyFigGenome[]; alignments: EasyFigAlignment[]; message?: string }

function blockColor(identity: number, inverted: boolean): string {
  if (inverted) {
    if (identity >= 99) return 'rgba(239,68,68,0.5)';
    if (identity >= 95) return 'rgba(239,68,68,0.35)';
    if (identity >= 90) return 'rgba(239,68,68,0.2)';
    return 'rgba(239,68,68,0.1)';
  }
  if (identity >= 99) return 'rgba(59,130,246,0.5)';
  if (identity >= 95) return 'rgba(59,130,246,0.35)';
  if (identity >= 90) return 'rgba(59,130,246,0.2)';
  return 'rgba(59,130,246,0.1)';
}

export default function EasyFigTool() {
  const picker = useSamplePicker();
  const [data, setData] = useState<EasyFigData | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredBlock, setHoveredBlock] = useState<EasyFigBlock | null>(null);
  const [minLength, setMinLength] = useState(1000);

  async function runAnalysis() {
    if (picker.selectedIds.length < 2 || picker.selectedIds.length > 4) return;
    setComputing(true);
    setError(null);
    setData(null);
    try {
      const res = await authPost('/api/tools/easyfig', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      const d: EasyFigData = await res.json();
      if (d.message) setError(d.message);
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setComputing(false);
    }
  }

  const svgWidth = 900;
  const genomeHeight = 20;
  const gapHeight = 80;
  const marginLeft = 100;
  const marginRight = 20;
  const drawWidth = svgWidth - marginLeft - marginRight;

  function renderDiagram() {
    if (!data || data.genomes.length < 2) return null;

    const maxLen = Math.max(...data.genomes.map((g) => g.total_length));
    const scale = (pos: number) => (pos / maxLen) * drawWidth;

    const totalHeight = data.genomes.length * genomeHeight + (data.genomes.length - 1) * gapHeight + 60;

    return (
      <svg width={svgWidth} height={totalHeight} className="rounded-lg" style={{ background: '#0F172A' }}>
        {data.genomes.map((genome, gIdx) => {
          const y = 30 + gIdx * (genomeHeight + gapHeight);
          let offset = 0;
          return (
            <g key={gIdx}>
              {/* Label */}
              <text x={5} y={y + genomeHeight / 2 + 4} fill="#D1D5DB" fontSize="11" fontWeight="500">{genome.sample_name}</text>
              {/* Genome bar (contigs) */}
              {genome.contigs.map((contig, cIdx) => {
                const x = marginLeft + scale(offset);
                const w = Math.max(1, scale(contig.length));
                offset += contig.length;
                return (
                  <rect key={cIdx} x={x} y={y} width={w} height={genomeHeight} fill="#374151" stroke="#4B5563" strokeWidth={0.5} rx={2}>
                    <title>{contig.name}: {(contig.length / 1000).toFixed(0)} kb</title>
                  </rect>
                );
              })}
              {/* Gene features (ARGs, VFs, MGEs, MRGs) */}
              {genome.features && (() => {
                const contigOffsets: Record<string, number> = {};
                let off = 0;
                for (const c of genome.contigs) { contigOffsets[c.name] = off; off += c.length; }
                const featureColors: Record<string, string> = { arg: '#EF4444', vf: '#FB923C', mge: '#A855F7', mrg: '#06B6D4' };
                return genome.features.map((feat, fIdx) => {
                  const cOff = contigOffsets[feat.contig];
                  if (cOff === undefined) return null;
                  const fx = marginLeft + scale(cOff + feat.start);
                  const fw = Math.max(2, scale(feat.end - feat.start));
                  return (
                    <rect key={`f-${fIdx}`} x={fx} y={y - 1} width={fw} height={genomeHeight + 2}
                      fill={featureColors[feat.type] || '#9CA3AF'} opacity={0.9} rx={1}>
                      <title>{feat.name} ({feat.type.toUpperCase()})</title>
                    </rect>
                  );
                });
              })()}
              {/* Length label */}
              <text x={marginLeft + scale(genome.total_length) + 5} y={y + genomeHeight / 2 + 4} fill="#9CA3AF" fontSize="9">
                {(genome.total_length / 1e6).toFixed(2)} Mb
              </text>
            </g>
          );
        })}

        {/* Alignment ribbons */}
        {data.alignments.map((aln, aIdx) => {
          const y1 = 30 + aln.query_idx * (genomeHeight + gapHeight) + genomeHeight;
          const y2 = 30 + aln.subject_idx * (genomeHeight + gapHeight);

          // Build contig offset maps
          const queryOffsets: Record<string, number> = {};
          let off = 0;
          for (const c of data.genomes[aln.query_idx].contigs) { queryOffsets[c.name] = off; off += c.length; }
          const subjectOffsets: Record<string, number> = {};
          off = 0;
          for (const c of data.genomes[aln.subject_idx].contigs) { subjectOffsets[c.name] = off; off += c.length; }

          return aln.blocks
            .filter((b) => b.length >= minLength)
            .map((block, bIdx) => {
              const qOff = queryOffsets[block.query_contig] ?? 0;
              const sOff = subjectOffsets[block.subject_contig] ?? 0;
              const qx1 = marginLeft + scale(qOff + block.query_start);
              const qx2 = marginLeft + scale(qOff + block.query_end);
              const sx1 = marginLeft + scale(sOff + block.subject_start);
              const sx2 = marginLeft + scale(sOff + block.subject_end);
              const color = blockColor(block.identity, block.inverted);
              const isHovered = hoveredBlock === block;

              return (
                <polygon
                  key={`${aIdx}-${bIdx}`}
                  points={`${qx1},${y1} ${qx2},${y1} ${sx2},${y2} ${sx1},${y2}`}
                  fill={color}
                  stroke={isHovered ? '#60A5FA' : 'none'}
                  strokeWidth={isHovered ? 1.5 : 0}
                  opacity={isHovered ? 1 : 0.8}
                  onMouseEnter={() => setHoveredBlock(block)}
                  onMouseLeave={() => setHoveredBlock(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <title>{`${block.identity}% identity, ${(block.length / 1000).toFixed(1)} kb${block.inverted ? ' (inverted)' : ''}`}</title>
                </polygon>
              );
            });
        })}
      </svg>
    );
  }

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        EasyFig-style synteny visualization. BLASTn alignments between genomes shown as colored ribbons.
        Blue = forward alignment, red = inverted. Darker = higher identity.
        Select 2-4 isolates.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={runAnalysis} disabled={picker.selectedIds.length < 2 || picker.selectedIds.length > 4 || computing} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${computing ? 'animate-spin' : ''}`} />
        {computing ? 'Computing...' : `Run EasyFig (${picker.selectedIds.length} selected, max 4)`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {data && data.genomes.length >= 2 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-100">Synteny Diagram</h2>
            <div className="flex items-center gap-3">
              <label className="text-xs text-gray-400">Min block: </label>
              <select value={minLength} onChange={(e) => setMinLength(Number(e.target.value))} className="input text-xs py-1 px-2">
                <option value={500}>500 bp</option>
                <option value={1000}>1 kb</option>
                <option value={5000}>5 kb</option>
                <option value={10000}>10 kb</option>
                <option value={50000}>50 kb</option>
              </select>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-gray-400">
            <span className="font-medium text-gray-300">Alignment:</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(59,130,246,0.5)' }} /> Forward (&ge;99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(59,130,246,0.25)' }} /> Forward (90-99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(239,68,68,0.5)' }} /> Inverted (&ge;99%)</span>
            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded" style={{ background: 'rgba(239,68,68,0.25)' }} /> Inverted (90-99%)</span>
            <span className="ml-2 font-medium text-gray-300">Genes:</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#EF4444' }} /> ARG</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#FB923C' }} /> Virulence</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#A855F7' }} /> MGE</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: '#06B6D4' }} /> MRG</span>
          </div>

          <div className="overflow-x-auto">
            {renderDiagram()}
          </div>

          {hoveredBlock && (
            <div className="mt-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700 text-sm">
              <span className="text-gray-400">Identity: </span>
              <span className="text-white font-mono">{hoveredBlock.identity}%</span>
              <span className="text-gray-400 ml-3">Length: </span>
              <span className="text-white font-mono">{(hoveredBlock.length / 1000).toFixed(1)} kb</span>
              <span className="text-gray-400 ml-3">Query: </span>
              <span className="text-gray-300">{hoveredBlock.query_contig}:{hoveredBlock.query_start}-{hoveredBlock.query_end}</span>
              <span className="text-gray-400 ml-3">Subject: </span>
              <span className="text-gray-300">{hoveredBlock.subject_contig}:{hoveredBlock.subject_start}-{hoveredBlock.subject_end}</span>
              {hoveredBlock.inverted && <span className="ml-3 px-2 py-0.5 bg-red-600/30 text-red-300 rounded text-xs">Inverted</span>}
            </div>
          )}

          {/* Stats */}
          <div className="mt-4 pt-3 border-t border-gray-800 text-xs text-gray-500">
            {data.alignments.map((aln, i) => {
              const filtered = aln.blocks.filter((b) => b.length >= minLength);
              const totalAligned = filtered.reduce((sum, b) => sum + b.length, 0);
              const inverted = filtered.filter((b) => b.inverted).length;
              return (
                <p key={i}>
                  {data.genomes[aln.query_idx].sample_name} vs {data.genomes[aln.subject_idx].sample_name}: {filtered.length} blocks, {(totalAligned / 1e6).toFixed(2)} Mb aligned, {inverted} inverted
                </p>
              );
            })}
          </div>
        </div>
      )}

      {picker.selectedIds.length >= 2 && picker.selectedIds.length <= 4 && !data && !computing && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Run EasyFig&quot; to generate synteny diagram.</div>
      )}
      {picker.selectedIds.length > 4 && (
        <div className="p-4 bg-yellow-600/20 border border-yellow-600/50 rounded-lg text-yellow-300 text-sm">Maximum 4 isolates for EasyFig visualization. Please deselect some.</div>
      )}
    </div>
  );
}
