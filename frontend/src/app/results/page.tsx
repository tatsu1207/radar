'use client';

import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import { listProjects, getHeatmap, exportCSV } from '@/lib/api';
import type { Project, HeatmapData } from '@/lib/api';
import Heatmap from '@/components/Heatmap';

export default function ResultsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [heatmapData, setHeatmapData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedProject) {
      setHeatmapData(null);
      return;
    }
    setHeatmapLoading(true);
    getHeatmap(selectedProject)
      .then(setHeatmapData)
      .catch(() => setHeatmapData(null))
      .finally(() => setHeatmapLoading(false));
  }, [selectedProject]);

  async function handleExport() {
    if (!selectedProject) return;
    try {
      const blob = await exportCSV(selectedProject);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `radar_results_project_${selectedProject}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  }

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
          <h1 className="text-2xl font-bold text-white">Results</h1>
          <p className="text-gray-400 text-sm mt-1">Visualize resistance analysis results across samples</p>
        </div>
        {selectedProject && (
          <button onClick={handleExport} className="btn-secondary flex items-center gap-2">
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        )}
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      <div className="card mb-6">
        <div className="max-w-sm">
          <label className="block text-sm text-gray-400 mb-1">Select Project</label>
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            className="input w-full"
          >
            <option value="">Select a project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
      </div>

      {!selectedProject ? (
        <div className="card text-center py-16">
          <p className="text-gray-500">Select a project to view the resistome heatmap.</p>
        </div>
      ) : heatmapLoading ? (
        <div className="card flex items-center justify-center py-16">
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      ) : (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-6">Resistome Heatmap</h2>
          <p className="text-sm text-gray-400 mb-4">
            Samples (rows) vs Drug Classes (columns). Color intensity indicates ARG count per class.
          </p>
          {heatmapData ? (
            <Heatmap data={heatmapData} />
          ) : (
            <div className="text-center py-12 text-gray-500">
              No heatmap data available. Run analyses on project samples first.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
