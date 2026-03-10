'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Play, RefreshCw, Terminal, Square, Cpu, ChevronRight, CheckCircle, XCircle, Clock, Loader2, Ban } from 'lucide-react';
import { listProjects, listSamples, startAnalysis, getJobs, getJob, cancelJob, runStep } from '@/lib/api';
import type { AnalysisJob, Project, Sample } from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';
import Modal from '@/components/Modal';

const PIPELINE_STEPS = [
  { tool: 'bbduk', label: 'Trimming (BBDuk)', description: 'Adapter trimming & quality filtering' },
  { tool: 'unicycler', label: 'Assembly (Unicycler)', description: 'Genome assembly from reads' },
  { tool: 'quast', label: 'QUAST', description: 'Assembly quality metrics' },
  { tool: 'busco', label: 'BUSCO', description: 'Assembly completeness check' },
  { tool: 'amrfinderplus', label: 'AMRFinderPlus', description: 'Antimicrobial resistance gene detection' },
  { tool: 'mob_recon', label: 'MOB-recon', description: 'Plasmid reconstruction & typing' },
  { tool: 'mefinder', label: 'MobileElementFinder', description: 'Mobile genetic element detection' },
  { tool: 'phenotype_prediction', label: 'Phenotype Prediction', description: 'Predict antibiotic susceptibility' },
  { tool: 'risk_scoring', label: 'Risk Scoring', description: 'Composite risk assessment' },
];

function StepIcon({ status }: { status?: string }) {
  switch (status) {
    case 'complete':
      return <CheckCircle className="w-5 h-5 text-green-400" />;
    case 'running':
      return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />;
    case 'failed':
      return <XCircle className="w-5 h-5 text-red-400" />;
    case 'cancelled':
      return <Ban className="w-5 h-5 text-yellow-400" />;
    case 'pending':
      return <Clock className="w-5 h-5 text-gray-400 animate-pulse" />;
    default:
      return <div className="w-5 h-5 rounded-full border-2 border-gray-600" />;
  }
}

export default function AnalysisPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [projects, setProjects] = useState<Project[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedProject, setSelectedProject] = useState<string>(searchParams.get('project') || '');
  const [selectedSample, setSelectedSample] = useState<string>(searchParams.get('sample') || '');
  const [threads, setThreads] = useState<number>(parseInt(searchParams.get('threads') || '4') || 4);
  const [starting, setStarting] = useState(false);
  const [runningStep, setRunningStep] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<string | null>(null);

  const [selectedJob, setSelectedJob] = useState<AnalysisJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  function updateURL(project: string, sample: string, t: number) {
    const params = new URLSearchParams();
    if (project) params.set('project', project);
    if (sample) params.set('sample', sample);
    if (t !== 4) params.set('threads', String(t));
    const qs = params.toString();
    router.replace(`/analysis${qs ? '?' + qs : ''}`, { scroll: false });
  }

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedProject) {
      listSamples(selectedProject).then(setSamples).catch(() => setSamples([]));
    } else {
      setSamples([]);
      setSelectedSample('');
    }
  }, [selectedProject]);

  const refreshJobs = useCallback(async () => {
    if (!selectedSample) return;
    try {
      const j = await getJobs(selectedSample);
      setJobs(j);
    } catch {
      // ignore
    }
  }, [selectedSample]);

  useEffect(() => {
    if (selectedSample) {
      refreshJobs();
    } else {
      setJobs([]);
    }
  }, [selectedSample, refreshJobs]);

  // Auto-poll jobs when any are pending/running
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');
    if (hasActive) {
      pollRef.current = setInterval(refreshJobs, 3000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobs, refreshJobs]);

  // Auto-poll selected job log
  useEffect(() => {
    if (selectedJob && (selectedJob.status === 'pending' || selectedJob.status === 'running')) {
      const pollLog = async () => {
        try {
          const updated = await getJob(selectedJob.id);
          setSelectedJob(updated);
        } catch {
          // ignore
        }
      };
      logPollRef.current = setInterval(pollLog, 2000);
    }
    return () => {
      if (logPollRef.current) clearInterval(logPollRef.current);
    };
  }, [selectedJob?.id, selectedJob?.status]);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [selectedJob?.log]);

  function handleProjectChange(val: string) {
    setSelectedProject(val);
    setSelectedSample('');
    updateURL(val, '', threads);
  }

  function handleSampleChange(val: string) {
    setSelectedSample(val);
    updateURL(selectedProject, val, threads);
  }

  function handleThreadsChange(val: number) {
    setThreads(val);
    updateURL(selectedProject, selectedSample, val);
  }

  // Get the latest job for each tool (most recent by started_at)
  function getLatestJobForTool(tool: string): AnalysisJob | undefined {
    const toolJobs = jobs.filter((j) => j.tool === tool);
    if (toolJobs.length === 0) return undefined;
    return toolJobs.sort((a, b) =>
      new Date(b.started_at || 0).getTime() - new Date(a.started_at || 0).getTime()
    )[0];
  }

  // Get the pipeline master job
  const pipelineJob = jobs
    .filter((j) => j.tool === 'pipeline')
    .sort((a, b) => new Date(b.started_at || 0).getTime() - new Date(a.started_at || 0).getTime())[0];

  const pipelineRunning = pipelineJob && (pipelineJob.status === 'pending' || pipelineJob.status === 'running');

  async function handleStartAll() {
    if (!selectedSample) return;
    setStarting(true);
    setError(null);
    try {
      await startAnalysis(selectedSample, threads);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start analysis');
    } finally {
      setStarting(false);
    }
  }

  async function handleRunStep(tool: string) {
    if (!selectedSample) return;
    setRunningStep(tool);
    setError(null);
    try {
      await runStep(selectedSample, tool, threads);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to start ${tool}`);
    } finally {
      setRunningStep(null);
    }
  }

  async function handleCancel(jobId: string) {
    setCancelling(jobId);
    try {
      await cancelJob(jobId);
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel job');
    } finally {
      setCancelling(null);
    }
  }

  async function handleCancelPipeline() {
    if (!pipelineJob) return;
    await handleCancel(pipelineJob.id);
  }

  async function viewLogs(jobId: string) {
    try {
      const job = await getJob(jobId);
      setSelectedJob(job);
    } catch {
      const localJob = jobs.find((j) => j.id === jobId);
      if (localJob) setSelectedJob(localJob);
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
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Analysis</h1>
        <p className="text-gray-400 text-sm mt-1">Run the full pipeline or individual steps on a sample</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {/* Sample selection & controls */}
      <div className="card mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Project</label>
            <select
              value={selectedProject}
              onChange={(e) => handleProjectChange(e.target.value)}
              className="input w-full"
            >
              <option value="">Select project...</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Sample</label>
            <select
              value={selectedSample}
              onChange={(e) => handleSampleChange(e.target.value)}
              className="input w-full"
              disabled={!selectedProject}
            >
              <option value="">Select sample...</option>
              {samples.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5" /> CPU Threads
            </label>
            <input
              type="number"
              min={1}
              max={128}
              value={threads}
              onChange={(e) => handleThreadsChange(Math.max(1, Math.min(128, parseInt(e.target.value) || 4)))}
              className="input w-full"
            />
          </div>
          <div className="flex gap-2">
            {pipelineRunning ? (
              <button
                onClick={handleCancelPipeline}
                className="btn-danger flex items-center gap-2"
              >
                <Square className="w-4 h-4" />
                Cancel Pipeline
              </button>
            ) : (
              <button
                onClick={handleStartAll}
                disabled={starting || !selectedSample}
                className="btn-primary flex items-center gap-2"
              >
                <Play className="w-4 h-4" />
                {starting ? 'Starting...' : 'Run All Steps'}
              </button>
            )}
            <button onClick={refreshJobs} className="btn-secondary flex items-center gap-2" disabled={!selectedSample}>
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Pipeline Steps */}
      {selectedSample && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-100">Pipeline Steps</h2>
            {pipelineJob && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Pipeline:</span>
                <StatusBadge status={pipelineJob.status} />
                {pipelineJob.tool === 'pipeline' && (
                  <button
                    onClick={() => viewLogs(pipelineJob.id)}
                    className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200 transition-colors"
                    title="View pipeline log"
                  >
                    <Terminal className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="space-y-1">
            {PIPELINE_STEPS.map((step, index) => {
              const job = getLatestJobForTool(step.tool);
              const status = job?.status;
              const isActive = status === 'pending' || status === 'running';
              const assemblyDone = getLatestJobForTool('unicycler')?.status === 'complete';
              const needsAssembly = index >= 2; // quast, busco, and everything after need assembly
              const canStart = !pipelineRunning && !isActive && status !== 'complete'
                && (!needsAssembly || assemblyDone);

              return (
                <div key={step.tool}>
                  <div
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                      job ? 'cursor-pointer hover:bg-gray-800/70' : ''
                    } ${isActive ? 'bg-gray-800/50' : ''}`}
                    onClick={() => job && viewLogs(job.id)}
                  >
                    {/* Step number & icon */}
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <span className="text-xs text-gray-600 font-mono w-4 text-right">{index + 1}</span>
                      <StepIcon status={status} />
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${status === 'complete' ? 'text-green-300' : status === 'failed' ? 'text-red-300' : 'text-gray-200'}`}>
                          {step.label}
                        </p>
                        <p className="text-xs text-gray-500 truncate">{step.description}</p>
                      </div>
                    </div>

                    {/* Time info */}
                    <div className="hidden sm:block text-xs text-gray-500 min-w-[140px] text-right">
                      {job?.started_at && (
                        <span>{new Date(job.started_at).toLocaleTimeString()}</span>
                      )}
                      {job?.finished_at && job?.started_at && (
                        <span className="ml-1 text-gray-600">
                          ({Math.round((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000)}s)
                        </span>
                      )}
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-1 min-w-[70px] justify-end" onClick={(e) => e.stopPropagation()}>
                      {isActive ? (
                        <button
                          onClick={() => handleCancel(job!.id)}
                          disabled={cancelling === job!.id}
                          className="px-2 py-1 text-xs rounded bg-red-900/40 hover:bg-red-900/70 text-red-300 transition-colors flex items-center gap-1"
                        >
                          <Square className="w-3 h-3" />
                          Cancel
                        </button>
                      ) : canStart ? (
                        <button
                          onClick={() => handleRunStep(step.tool)}
                          disabled={runningStep === step.tool}
                          className="px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors flex items-center gap-1"
                        >
                          <Play className="w-3 h-3" />
                          {runningStep === step.tool ? '...' : 'Run'}
                        </button>
                      ) : null}
                    </div>
                  </div>

                  {/* Connector line between steps */}
                  {index < PIPELINE_STEPS.length - 1 && (
                    <div className="ml-[38px] h-1 border-l border-gray-700/50" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Log Viewer Modal */}
      <Modal
        isOpen={!!selectedJob}
        onClose={() => setSelectedJob(null)}
        title={`${selectedJob?.tool} - Logs`}
        maxWidth="max-w-3xl"
      >
        {selectedJob && (
          <div>
            <div className="flex items-center gap-4 mb-4">
              <StatusBadge status={selectedJob.status} />
              {selectedJob.threads && (
                <span className="text-xs text-gray-500">{selectedJob.threads} threads</span>
              )}
              {(selectedJob.status === 'pending' || selectedJob.status === 'running') && (
                <>
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Auto-refreshing...
                  </span>
                  <button
                    onClick={() => handleCancel(selectedJob.id)}
                    disabled={cancelling === selectedJob.id}
                    className="btn-danger text-xs flex items-center gap-1 ml-auto"
                  >
                    <Square className="w-3 h-3" />
                    {cancelling === selectedJob.id ? 'Cancelling...' : 'Cancel'}
                  </button>
                </>
              )}
            </div>
            <div className="bg-gray-950 rounded-lg p-4 font-mono text-xs text-gray-300 max-h-96 overflow-y-auto whitespace-pre-wrap">
              {selectedJob.log || 'No logs available.'}
              <div ref={logEndRef} />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
