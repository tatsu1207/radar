'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Play, RefreshCw } from 'lucide-react';
import {
  getProject,
  listSamples,
  getComparativeJobs,
  startPangenome,
  startSNPTree,
  startMashtree,
  getLatestPangenome,
  getLatestSNPTree,
  getLatestMashtree,
} from '@/lib/api';
import type {
  Project,
  Sample,
  ComparativeJob,
  PangenomeResult,
  SNPTreeResult,
  MashtreeResultData,
} from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

export default function ComparativeAnalysisPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [jobs, setJobs] = useState<ComparativeJob[]>([]);
  const [pangenome, setPangenome] = useState<PangenomeResult | null>(null);
  const [snpTree, setSnpTree] = useState<SNPTreeResult | null>(null);
  const [mashtree, setMashtree] = useState<MashtreeResultData | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const completedSamples = samples.filter(s => s.status === 'complete');

  const loadData = useCallback(async () => {
    try {
      const [proj, sampleList, jobList] = await Promise.all([
        getProject(projectId),
        listSamples(projectId),
        getComparativeJobs(projectId).catch(() => []),
      ]);
      setProject(proj);
      setSamples(sampleList);
      setJobs(jobList);

      // Load latest results
      getLatestPangenome(projectId).then(setPangenome).catch(() => {});
      getLatestSNPTree(projectId).then(setSnpTree).catch(() => {});
      getLatestMashtree(projectId).then(setMashtree).catch(() => {});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { loadData(); }, [loadData]);

  // Poll for running jobs
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running' || j.status === 'pending');
    if (!hasRunning) return;
    const timer = setInterval(() => loadData(), 5000);
    return () => clearInterval(timer);
  }, [jobs, loadData]);

  async function handleStart(type: 'pangenome' | 'snp-tree' | 'mashtree') {
    setRunning(type);
    setError(null);
    try {
      if (type === 'pangenome') await startPangenome(projectId);
      else if (type === 'snp-tree') await startSNPTree(projectId);
      else if (type === 'mashtree') await startMashtree(projectId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to start ${type}`);
    } finally {
      setRunning(null);
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
      <Link
        href={`/projects/${projectId}`}
        className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Project
      </Link>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Comparative Analysis</h1>
          <p className="text-gray-400 text-sm mt-1">
            {project?.name} — {completedSamples.length} completed samples available
          </p>
        </div>
        <button onClick={loadData} className="btn-secondary flex items-center gap-2">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {completedSamples.length < 2 && (
        <div className="mb-6 p-4 bg-yellow-600/20 border border-yellow-600/50 rounded-lg text-yellow-300 text-sm">
          At least 2 completed samples are required for comparative analyses. Currently {completedSamples.length} sample(s) completed.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Pan-genome */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">Pan-Genome (Panaroo)</h2>
          <p className="text-gray-400 text-sm mb-4">Gene presence/absence matrix across all isolates.</p>
          {pangenome ? (
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Core genes</span>
                <span className="text-green-400 font-medium">{pangenome.core_genes}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Soft-core</span>
                <span className="text-blue-400">{pangenome.soft_core_genes}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Shell</span>
                <span className="text-yellow-400">{pangenome.shell_genes}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Cloud</span>
                <span className="text-gray-400">{pangenome.cloud_genes}</span>
              </div>
              <div className="flex justify-between text-sm border-t border-gray-700 pt-2">
                <span className="text-gray-300 font-medium">Total</span>
                <span className="text-white font-medium">{pangenome.total_genes}</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm mb-4">No results yet.</p>
          )}
          <button
            onClick={() => handleStart('pangenome')}
            disabled={completedSamples.length < 2 || running === 'pangenome'}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {running === 'pangenome' ? (
              <><div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Running...</>
            ) : (
              <><Play className="w-4 h-4" /> {pangenome ? 'Re-run' : 'Run'} Pan-Genome</>
            )}
          </button>
        </div>

        {/* SNP Tree */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">SNP Phylogeny (Snippy)</h2>
          <p className="text-gray-400 text-sm mb-4">Core-genome SNP tree with optional recombination filtering.</p>
          {snpTree ? (
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Core SNPs</span>
                <span className="text-blue-400 font-medium">{snpTree.core_snp_count?.toLocaleString()}</span>
              </div>
              {snpTree.newick_recomb_filtered_path && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-400">Gubbins filtered</span>
                  <span className="text-green-400">Yes</span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-500 text-sm mb-4">No results yet.</p>
          )}
          <button
            onClick={() => handleStart('snp-tree')}
            disabled={completedSamples.length < 2 || running === 'snp-tree'}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {running === 'snp-tree' ? (
              <><div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Running...</>
            ) : (
              <><Play className="w-4 h-4" /> {snpTree ? 'Re-run' : 'Run'} SNP Tree</>
            )}
          </button>
        </div>

        {/* Mashtree */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">Distance Tree (Mashtree)</h2>
          <p className="text-gray-400 text-sm mb-4">Rapid MinHash-based phylogenomic tree.</p>
          {mashtree ? (
            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Status</span>
                <span className="text-green-400">Complete</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm mb-4">No results yet.</p>
          )}
          <button
            onClick={() => handleStart('mashtree')}
            disabled={completedSamples.length < 3 || running === 'mashtree'}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {running === 'mashtree' ? (
              <><div className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Running...</>
            ) : (
              <><Play className="w-4 h-4" /> {mashtree ? 'Re-run' : 'Run'} Mashtree</>
            )}
          </button>
        </div>
      </div>

      {/* Job history */}
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Analysis History</h2>
        {jobs.length === 0 ? (
          <p className="text-gray-500 text-center py-8">No comparative analyses run yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="table-header">Analysis</th>
                  <th className="table-header">Status</th>
                  <th className="table-header">Samples</th>
                  <th className="table-header">Started</th>
                  <th className="table-header">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-800/50">
                    <td className="table-cell font-medium text-gray-200">
                      {job.analysis_type === 'pangenome' ? 'Pan-Genome'
                        : job.analysis_type === 'snp_tree' ? 'SNP Phylogeny'
                        : job.analysis_type === 'mashtree' ? 'Mashtree'
                        : job.analysis_type}
                    </td>
                    <td className="table-cell"><StatusBadge status={job.status} /></td>
                    <td className="table-cell">{job.sample_ids?.length ?? '-'}</td>
                    <td className="table-cell text-sm">{job.started_at ? new Date(job.started_at).toLocaleString() : '-'}</td>
                    <td className="table-cell text-sm">{job.finished_at ? new Date(job.finished_at).toLocaleString() : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
