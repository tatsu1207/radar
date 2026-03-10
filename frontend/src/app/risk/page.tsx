'use client';

import { useState, useEffect } from 'react';
import { RefreshCw, SlidersHorizontal } from 'lucide-react';
import { listProjects, calculateRisk } from '@/lib/api';
import type { Project, RiskScore } from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

export default function RiskPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [riskScores, setRiskScores] = useState<RiskScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showWeights, setShowWeights] = useState(false);

  // Weights
  const [argWeight, setArgWeight] = useState(0.4);
  const [vfWeight, setVfWeight] = useState(0.3);
  const [mobilityWeight, setMobilityWeight] = useState(0.3);

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
        arg_weight: argWeight,
        vf_weight: vfWeight,
        mobility_weight: mobilityWeight,
      });
      setRiskScores(scores);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to calculate risk');
    } finally {
      setCalculating(false);
    }
  }

  const stats = {
    total: riskScores.length,
    low: riskScores.filter((r) => r.risk_category === 'low').length,
    medium: riskScores.filter((r) => r.risk_category === 'medium').length,
    high: riskScores.filter((r) => r.risk_category === 'high').length,
    critical: riskScores.filter((r) => r.risk_category === 'critical').length,
  };

  const riskColorMap: Record<string, string> = {
    low: 'border-green-600/50',
    medium: 'border-yellow-600/50',
    high: 'border-orange-600/50',
    critical: 'border-red-600/50',
  };

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
          <h1 className="text-2xl font-bold text-white">Risk Assessment</h1>
          <p className="text-gray-400 text-sm mt-1">Evaluate resistance risk across samples</p>
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
            onClick={() => setShowWeights(!showWeights)}
            className="btn-secondary flex items-center gap-2"
          >
            <SlidersHorizontal className="w-4 h-4" />
            Weights
          </button>
          <button
            onClick={handleCalculate}
            disabled={!selectedProject || calculating}
            className="btn-primary flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${calculating ? 'animate-spin' : ''}`} />
            {calculating ? 'Calculating...' : 'Calculate Risk'}
          </button>
        </div>

        {showWeights && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mt-6 pt-6 border-t border-gray-800">
            <div>
              <label className="flex items-center justify-between text-sm text-gray-400 mb-2">
                <span>ARG Weight</span>
                <span className="font-mono text-gray-300">{argWeight.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={argWeight}
                onChange={(e) => setArgWeight(Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-sm text-gray-400 mb-2">
                <span>Virulence Weight</span>
                <span className="font-mono text-gray-300">{vfWeight.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={vfWeight}
                onChange={(e) => setVfWeight(Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-sm text-gray-400 mb-2">
                <span>Mobility Weight</span>
                <span className="font-mono text-gray-300">{mobilityWeight.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={mobilityWeight}
                onChange={(e) => setMobilityWeight(Number(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>
            <div className="sm:col-span-3">
              <p className="text-xs text-gray-500">
                Total weight: {(argWeight + vfWeight + mobilityWeight).toFixed(2)} (should sum to 1.0 for normalized scores)
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Summary stats */}
      {riskScores.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold text-white">{stats.total}</p>
            <p className="text-xs text-gray-400">Total</p>
          </div>
          <div className="card text-center border-green-600/30">
            <p className="text-2xl font-bold text-green-400">{stats.low}</p>
            <p className="text-xs text-gray-400">Low</p>
          </div>
          <div className="card text-center border-yellow-600/30">
            <p className="text-2xl font-bold text-yellow-400">{stats.medium}</p>
            <p className="text-xs text-gray-400">Medium</p>
          </div>
          <div className="card text-center border-orange-600/30">
            <p className="text-2xl font-bold text-orange-400">{stats.high}</p>
            <p className="text-xs text-gray-400">High</p>
          </div>
          <div className="card text-center border-red-600/30">
            <p className="text-2xl font-bold text-red-400">{stats.critical}</p>
            <p className="text-xs text-gray-400">Critical</p>
          </div>
        </div>
      )}

      {/* Sample cards */}
      {!selectedProject ? (
        <div className="card text-center py-16">
          <p className="text-gray-500">Select a project and calculate risk to view results.</p>
        </div>
      ) : riskScores.length === 0 ? (
        <div className="card text-center py-16">
          <p className="text-gray-500">No risk scores yet. Click "Calculate Risk" to assess samples.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {riskScores
            .sort((a, b) => b.composite_score - a.composite_score)
            .map((score) => (
              <div
                key={score.sample_id}
                className={`card border ${riskColorMap[score.risk_category] || 'border-gray-800'}`}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-100">{score.sample_name}</h3>
                  <StatusBadge status={score.risk_category} type="risk" />
                </div>
                <div className="text-center my-4">
                  <p className="text-3xl font-bold text-white">{score.composite_score.toFixed(3)}</p>
                  <p className="text-xs text-gray-500">Composite Score</p>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2 bg-gray-800/50 rounded-lg">
                    <p className="text-sm font-semibold text-gray-200">{score.arg_score.toFixed(2)}</p>
                    <p className="text-[10px] text-gray-500">ARG</p>
                  </div>
                  <div className="p-2 bg-gray-800/50 rounded-lg">
                    <p className="text-sm font-semibold text-gray-200">{score.vf_score.toFixed(2)}</p>
                    <p className="text-[10px] text-gray-500">VF</p>
                  </div>
                  <div className="p-2 bg-gray-800/50 rounded-lg">
                    <p className="text-sm font-semibold text-gray-200">{score.mobility_score.toFixed(2)}</p>
                    <p className="text-[10px] text-gray-500">Mobility</p>
                  </div>
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
