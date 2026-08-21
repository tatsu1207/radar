'use client';

import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { listProjects, calculateRisk } from '@/lib/api';
import type { Project, RiskScore } from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

const RANK_DESCRIPTIONS: Record<string, string> = {
  R1: 'Reserve + conjugative plasmid (broad)',
  R2: 'Reserve + conjugative plasmid (narrow) / ICE',
  R3: 'Reserve + mobilizable plasmid (with helper)',
  R4: 'Reserve + mobilizable plasmid (no helper)',
  R5: 'Reserve + non-mobile / chromosome',
  R6: 'Watch + conjugative plasmid (broad)',
  R7: 'Watch + conjugative plasmid (narrow) / ICE',
  R8: 'Watch + mobilizable plasmid (with helper)',
  R9: 'Watch + mobilizable plasmid (no helper)',
  R10: 'Watch + non-mobile / chromosome',
  R11: 'Access-tier ARG only',
  R12: 'No ARG detected',
  NG: 'Not graded (intrinsic only)',
};

function rankSortKey(rank: string | null): number {
  if (!rank) return 99;
  if (rank === 'NG') return 13;
  const n = parseInt(rank.replace('R', ''), 10);
  return isNaN(n) ? 99 : n;
}

export default function RiskPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [riskScores, setRiskScores] = useState<RiskScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleCalculate() {
    if (!selectedProject) return;
    setCalculating(true);
    setError(null);
    try {
      const scores = await calculateRisk(selectedProject, {
        arg_weight: 0.4,
        vf_weight: 0.3,
        mobility_weight: 0.3,
      });
      setRiskScores(scores);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to calculate risk');
    } finally {
      setCalculating(false);
    }
  }

  const highRisk = riskScores.filter((r) =>
    r.hazard_rank && ['R1', 'R2', 'R3'].includes(r.hazard_rank)
  ).length;
  const mdrCount = riskScores.filter((r) => r.mdr_flag).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Hazard Ranking</h1>
          <p className="text-gray-400 text-sm mt-1">
            AMR hazard ranks based on clinical importance (AWaRe tier) and transmissibility
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {/* Controls */}
      <div className="card mb-6">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm text-gray-400 mb-1">Project</label>
            <select
              value={selectedProject}
              onChange={(e) => {
                setSelectedProject(e.target.value);
                setRiskScores([]);
              }}
              className="input w-full"
            >
              <option value="">Select a project...</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleCalculate}
            disabled={!selectedProject || calculating}
            className="btn-primary flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${calculating ? 'animate-spin' : ''}`} />
            {calculating ? 'Calculating...' : 'Calculate Risk'}
          </button>
        </div>
      </div>

      {/* Summary stats */}
      {riskScores.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold text-white">{riskScores.length}</p>
            <p className="text-xs text-gray-400">Total Samples</p>
          </div>
          <div className="card text-center border-red-600/30">
            <p className="text-2xl font-bold text-red-400">{highRisk}</p>
            <p className="text-xs text-gray-400">High-Risk (R1-R3)</p>
          </div>
          <div className="card text-center border-yellow-600/30">
            <p className="text-2xl font-bold text-yellow-400">{mdrCount}</p>
            <p className="text-xs text-gray-400">MDR</p>
          </div>
          <div className="card text-center border-blue-600/30">
            <p className="text-2xl font-bold text-blue-400">
              {riskScores.length > 0
                ? ((highRisk / riskScores.length) * 100).toFixed(1)
                : '0'}%
            </p>
            <p className="text-xs text-gray-400">High-Risk Rate</p>
          </div>
        </div>
      )}

      {/* Results table */}
      {!selectedProject ? (
        <div className="card text-center py-16">
          <p className="text-gray-500">Select a project and calculate risk to view results.</p>
        </div>
      ) : riskScores.length === 0 ? (
        <div className="card text-center py-16">
          <p className="text-gray-500">No risk scores yet. Click &quot;Calculate Risk&quot; to assess samples.</p>
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left text-gray-400 text-xs uppercase tracking-wider">
                <th className="px-3 py-2">Sample</th>
                <th className="px-3 py-2">Rank</th>
                <th className="px-3 py-2">AWaRe Tier</th>
                <th className="px-3 py-2">Trans. Level</th>
                <th className="px-3 py-2">Worst-Case ARG</th>
                <th className="px-3 py-2">Location</th>
                <th className="px-3 py-2">MDR</th>
                <th className="px-3 py-2">Classes</th>
                <th className="px-3 py-2">VF Categories</th>
              </tr>
            </thead>
            <tbody>
              {riskScores
                .sort((a, b) => rankSortKey(a.hazard_rank) - rankSortKey(b.hazard_rank))
                .map((score) => (
                  <tr key={score.sample_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-3 py-2 font-medium text-gray-200">{score.sample_name}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={score.hazard_rank || 'NG'} type="hazard" />
                    </td>
                    <td className="px-3 py-2">
                      <span className={
                        score.aware_tier === 'Reserve' ? 'text-red-400 font-semibold' :
                        score.aware_tier === 'Watch' ? 'text-yellow-400' :
                        score.aware_tier === 'Access' ? 'text-green-400' :
                        'text-gray-500'
                      }>
                        {score.aware_tier || '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-300">{score.transmissibility_level ?? '-'}</td>
                    <td className="px-3 py-2 font-mono text-gray-300 text-xs">{score.worst_case_arg || '-'}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{score.worst_case_location || '-'}</td>
                    <td className="px-3 py-2">
                      {score.mdr_flag ? (
                        <span className="text-orange-400 font-semibold">MDR</span>
                      ) : (
                        <span className="text-gray-600">-</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-gray-300">{score.drug_class_count ?? '-'}</td>
                    <td className="px-3 py-2 text-gray-300">{score.vf_category_count ?? '-'}</td>
                  </tr>
                ))}
            </tbody>
          </table>

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-semibold">Hazard Rank Legend</p>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1 text-xs text-gray-500">
              {Object.entries(RANK_DESCRIPTIONS).map(([rank, desc]) => (
                <div key={rank} className="flex items-center gap-2">
                  <StatusBadge status={rank} type="hazard" />
                  <span>{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
