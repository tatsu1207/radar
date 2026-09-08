'use client';

import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { authPost, SamplePicker, useSamplePicker } from '@/components/tools/shared';

const RANK_DESCRIPTIONS: Record<string, string> = {
  R1: 'Reserve + conjugative plasmid (broad host range)',
  R2: 'Reserve + conjugative plasmid (narrow) or ICE-borne',
  R3: 'Reserve + mobilizable plasmid (with conjugative helper)',
  R4: 'Reserve + mobilizable plasmid (no helper)',
  R5: 'Reserve + chromosomal (non-mobile)',
  R6: 'Watch + conjugative plasmid (broad host range)',
  R7: 'Watch + conjugative plasmid (narrow) or ICE-borne',
  R8: 'Watch + mobilizable plasmid (with conjugative helper)',
  R9: 'Watch + mobilizable plasmid (no helper)',
  R10: 'Watch + chromosomal (non-mobile)',
  R11: 'Access-tier ARG only',
  R12: 'No AMR gene detected',
  NG: 'Not graded (intrinsic/untypeable only)',
};

const RANK_COLORS: Record<string, string> = {
  R1: 'bg-red-900 text-white', R2: 'bg-red-800 text-white', R3: 'bg-red-700 text-white',
  R4: 'bg-red-600 text-white', R5: 'bg-red-500 text-white',
  R6: 'bg-amber-700 text-white', R7: 'bg-amber-600 text-white',
  R8: 'bg-yellow-700 text-white', R9: 'bg-yellow-600 text-white', R10: 'bg-yellow-500 text-gray-900',
  R11: 'bg-green-700 text-white', R12: 'bg-gray-700 text-white', NG: 'bg-gray-600 text-white',
};

interface HazardScore {
  sample_id: string;
  sample_name: string;
  hazard_rank: string | null;
  aware_tier: string | null;
  transmissibility_level: number | null;
  worst_case_arg: string | null;
  worst_case_drug_class: string | null;
  worst_case_location: string | null;
  mdr_flag: boolean | null;
  drug_class_count: number | null;
  vf_category_count: number | null;
}

export default function HazardRankingTool() {
  const picker = useSamplePicker();
  const [scores, setScores] = useState<HazardScore[]>([]);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSample, setExpandedSample] = useState<string | null>(null);

  async function handleCalculate() {
    if (picker.selectedIds.length === 0) return;
    setCalculating(true);
    setError(null);
    try {
      const res = await authPost('/api/tools/risk', { sample_ids: picker.selectedIds });
      if (!res.ok) throw new Error(await res.text());
      setScores(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to calculate risk');
    } finally {
      setCalculating(false);
    }
  }

  function buildExplanation(s: HazardScore): string {
    const rank = s.hazard_rank || 'NG';
    const parts: string[] = [];

    if (rank === 'R12') {
      parts.push('No AMR genes were detected in this isolate.');
      return parts.join(' ');
    }
    if (rank === 'NG') {
      parts.push('AMR genes were detected but none mapped to a WHO AWaRe tier. These may be intrinsic species-core genes that were excluded from ranking.');
      return parts.join(' ');
    }

    // AWaRe tier explanation
    if (s.aware_tier && s.worst_case_arg) {
      parts.push(`The worst-case ARG is ${s.worst_case_arg} (${s.worst_case_drug_class || 'unknown class'}), which maps to the WHO AWaRe "${s.aware_tier}" tier.`);
    }

    // Transmissibility explanation
    if (s.worst_case_location) {
      const loc = s.worst_case_location;
      if (loc.includes('conjugative-broad')) {
        parts.push(`This gene is carried on a conjugative plasmid with broad host range (transmissibility level 5), meaning it can transfer across genera.`);
      } else if (loc.includes('conjugative-narrow')) {
        parts.push(`This gene is on a conjugative plasmid with narrow host range (level 4), transferable within the same genus.`);
      } else if (loc.includes('ICE')) {
        parts.push(`This gene is within an integrative conjugative element (ICE) (level 4), which can excise and transfer chromosomally.`);
      } else if (loc.includes('mobilizable+helper')) {
        parts.push(`This gene is on a mobilizable plasmid with a conjugative helper plasmid present (level 3), enabling indirect transfer.`);
      } else if (loc.includes('mobilizable')) {
        parts.push(`This gene is on a mobilizable plasmid without a helper (level 2), with limited transfer potential.`);
      } else if (loc === 'chromosome') {
        parts.push(`This gene is chromosomal (level 1), with no detected mobile element context.`);
      }
    }

    // MDR
    if (s.mdr_flag) {
      parts.push(`This isolate is MDR (multi-drug resistant), with resistance genes spanning ${s.drug_class_count} distinct antimicrobial classes.`);
    }

    // VF
    if (s.vf_category_count && s.vf_category_count > 0) {
      parts.push(`${s.vf_category_count} virulence factor categor${s.vf_category_count === 1 ? 'y was' : 'ies were'} detected.`);
    }

    return parts.join(' ');
  }

  const highRisk = scores.filter((r) => r.hazard_rank && ['R1', 'R2', 'R3'].includes(r.hazard_rank)).length;
  const mdrCount = scores.filter((r) => r.mdr_flag).length;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Assess isolate-level AMR hazard based on the WHO AWaRe classification and ARG transmissibility context.
        Ranks R1 (highest risk) through R12 (no ARGs detected). Select isolates to score.
      </p>

      <SamplePicker samples={picker.allSamples} selected={picker.selected} onToggle={picker.toggle} onSelectAll={picker.selectAll} onDeselectAll={picker.deselectAll} loading={picker.loading} />

      <button onClick={handleCalculate} disabled={picker.selectedIds.length === 0 || calculating} className="btn-primary flex items-center gap-2 text-sm">
        <RefreshCw className={`w-4 h-4 ${calculating ? 'animate-spin' : ''}`} />
        {calculating ? 'Loading...' : `Show Risk (${picker.selectedIds.length})`}
      </button>

      {error && <div className="p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>}

      {/* Summary cards */}
      {scores.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="card text-center">
            <p className="text-2xl font-bold text-white">{scores.length}</p>
            <p className="text-xs text-gray-400">Total Samples</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-red-400">{highRisk}</p>
            <p className="text-xs text-gray-400">Critical (R1-R3)</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-yellow-400">{mdrCount}</p>
            <p className="text-xs text-gray-400">MDR</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-blue-400">{scores.length > 0 ? ((highRisk / scores.length) * 100).toFixed(0) : '0'}%</p>
            <p className="text-xs text-gray-400">Critical Rate</p>
          </div>
        </div>
      )}

      {/* Results */}
      {scores.length > 0 && (
        <div className="card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left text-gray-400 text-xs uppercase tracking-wider">
                  <th className="px-3 py-2">Sample</th>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">AWaRe Tier</th>
                  <th className="px-3 py-2">Worst-Case ARG</th>
                  <th className="px-3 py-2">Drug Class</th>
                  <th className="px-3 py-2">Location</th>
                  <th className="px-3 py-2">MDR</th>
                </tr>
              </thead>
              <tbody>
                {scores
                  .sort((a, b) => {
                    const aKey = a.hazard_rank === 'NG' ? 13 : parseInt((a.hazard_rank || 'R99').replace('R', ''), 10);
                    const bKey = b.hazard_rank === 'NG' ? 13 : parseInt((b.hazard_rank || 'R99').replace('R', ''), 10);
                    return aKey - bKey;
                  })
                  .map((s) => {
                    const rank = s.hazard_rank || 'NG';
                    const isExpanded = expandedSample === s.sample_id;
                    return (
                      <tr key={s.sample_id} className="border-b border-gray-800/50 cursor-pointer hover:bg-gray-800/30" onClick={() => setExpandedSample(isExpanded ? null : s.sample_id)}>
                        <td className="px-3 py-2.5 font-medium text-gray-200">{s.sample_name}</td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>
                            {rank}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={s.aware_tier === 'Reserve' ? 'text-red-400 font-semibold' : s.aware_tier === 'Watch' ? 'text-yellow-400' : s.aware_tier === 'Access' ? 'text-green-400' : 'text-gray-500'}>
                            {s.aware_tier || '-'}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-gray-300 text-xs">{s.worst_case_arg || '-'}</td>
                        <td className="px-3 py-2.5 text-gray-400 text-xs">{s.worst_case_drug_class || '-'}</td>
                        <td className="px-3 py-2.5 text-gray-400 text-xs">{s.worst_case_location || '-'}</td>
                        <td className="px-3 py-2.5">
                          {s.mdr_flag ? <span className="text-orange-400 font-semibold">MDR ({s.drug_class_count})</span> : <span className="text-gray-600">-</span>}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>

          {/* Expanded explanation panel */}
          {expandedSample && (() => {
            const s = scores.find((sc) => sc.sample_id === expandedSample);
            if (!s) return null;
            const rank = s.hazard_rank || 'NG';
            return (
              <div className="mt-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <div className="flex items-center gap-3 mb-3">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded text-sm font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>{rank}</span>
                  <span className="text-gray-200 font-medium">{s.sample_name}</span>
                  <span className="text-gray-500 text-xs">{RANK_DESCRIPTIONS[rank]}</span>
                </div>
                <p className="text-sm text-gray-300 leading-relaxed">{buildExplanation(s)}</p>
              </div>
            );
          })()}

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-semibold">Rank Legend (click a row for explanation)</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5 text-xs text-gray-500">
              {Object.entries(RANK_DESCRIPTIONS).map(([rank, desc]) => (
                <div key={rank} className="flex items-center gap-2">
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${RANK_COLORS[rank] || 'bg-gray-700 text-white'}`}>{rank}</span>
                  <span>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {scores.length === 0 && picker.selectedIds.length > 0 && !calculating && (
        <div className="card text-center py-8 text-gray-500">Click &quot;Show Risk&quot; to view hazard ranks for selected isolates.</div>
      )}
    </div>
  );
}
