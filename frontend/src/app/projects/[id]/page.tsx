'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { Pencil, Trash2, ArrowLeft, FolderOpen, GitBranch } from 'lucide-react';
import Link from 'next/link';
import { getProject, updateProject, deleteProject, listSamples, getProjectJobs, deleteSample } from '@/lib/api';
import type { Project, Sample, AnalysisJob } from '@/lib/api';
import SampleTable from '@/components/SampleTable';
import Modal from '@/components/Modal';

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit modal
  const [showEdit, setShowEdit] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [saving, setSaving] = useState(false);

  // Delete project confirm
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Delete sample confirm
  const [deletingSampleId, setDeletingSampleId] = useState<string | null>(null);
  const [deletingSample, setDeletingSample] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [proj, samps, allJobs] = await Promise.all([
        getProject(projectId),
        listSamples(projectId),
        getProjectJobs(projectId).catch(() => [] as AnalysisJob[]),
      ]);
      setProject(proj);
      setSamples(samps);
      setJobs(allJobs);
      setEditName(proj.name);
      setEditDesc(proj.description);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load project');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-poll if any jobs are active
  useEffect(() => {
    const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');
    if (hasActive) {
      pollRef.current = setInterval(async () => {
        const allJobs = await getProjectJobs(projectId).catch(() => [] as AnalysisJob[]);
        setJobs(allJobs);
      }, 5000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobs, projectId]);

  async function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateProject(projectId, { name: editName, description: editDesc });
      setProject(updated);
      setShowEdit(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update project');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteProject(projectId);
      router.push('/projects');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project');
      setDeleting(false);
    }
  }

  async function handleDeleteSample() {
    if (!deletingSampleId) return;
    setDeletingSample(true);
    try {
      await deleteSample(deletingSampleId);
      setDeletingSampleId(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete sample');
    } finally {
      setDeletingSample(false);
    }
  }

  const deletingSampleName = samples.find((s) => s.id === deletingSampleId)?.name;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-400">Project not found</p>
        <Link href="/" className="text-blue-400 hover:text-blue-300 mt-2 inline-block">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div>
      <Link href="/" className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-4">
        <ArrowLeft className="w-4 h-4" />
        Back to Projects
      </Link>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Project Header */}
      <div className="card mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">{project.name}</h1>
            <p className="text-gray-400">{project.description || 'No description'}</p>
            <p className="text-xs text-gray-500 mt-2">
              Created {new Date(project.created_at).toLocaleDateString()} | {samples.length} sample{samples.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowEdit(true)} className="btn-secondary flex items-center gap-2 text-sm">
              <Pencil className="w-4 h-4" />
              Edit
            </button>
            <button onClick={() => setShowDelete(true)} className="btn-danger flex items-center gap-2 text-sm">
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* Samples */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-100">Samples</h2>
          <div className="flex items-center gap-2">
            <Link href={`/projects/${projectId}/comparative`} className="btn-secondary flex items-center gap-2 text-sm">
              <GitBranch className="w-4 h-4" />
              Comparative Analysis
            </Link>
            <Link href={`/projects/${projectId}/files`} className="btn-primary flex items-center gap-2 text-sm">
              <FolderOpen className="w-4 h-4" />
              File Manager
            </Link>
          </div>
        </div>
        <SampleTable
          samples={samples}
          jobs={jobs}
          onDeleteSample={(id) => setDeletingSampleId(id)}
        />
        <p className="mt-3 text-xs text-gray-500">
          Naming: <code className="text-blue-400">SAMPLE_R1.fastq.gz</code> / <code className="text-blue-400">SAMPLE_R2.fastq.gz</code> for Illumina, <code className="text-blue-400">SAMPLE.fastq.gz</code> for long reads
        </p>
      </div>

      {/* Heatmap placeholder */}
      {samples.length > 0 && (
        <div className="card mt-6">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Resistome Heatmap</h2>
          <div className="flex items-center justify-center py-12 text-gray-500 border border-dashed border-gray-700 rounded-lg">
            <p>Run analyses on samples to generate the resistome heatmap visualization.</p>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      <Modal isOpen={showEdit} onClose={() => setShowEdit(false)} title="Edit Project">
        <form onSubmit={handleUpdate} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Project Name</label>
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="input w-full"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Description</label>
            <textarea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              rows={3}
              className="input w-full resize-none"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setShowEdit(false)} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Project Modal */}
      <Modal isOpen={showDelete} onClose={() => setShowDelete(false)} title="Delete Project">
        <p className="text-gray-300 mb-4">
          Are you sure you want to delete <strong>{project.name}</strong>? This will permanently remove all associated samples, files, and results. This action cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setShowDelete(false)} className="btn-secondary">Cancel</button>
          <button onClick={handleDelete} disabled={deleting} className="btn-danger">
            {deleting ? 'Deleting...' : 'Delete Project'}
          </button>
        </div>
      </Modal>

      {/* Delete Sample Modal */}
      <Modal isOpen={!!deletingSampleId} onClose={() => setDeletingSampleId(null)} title="Delete Sample">
        <p className="text-gray-300 mb-4">
          Are you sure you want to delete <strong>{deletingSampleName}</strong>? This will permanently remove all associated files, jobs, and results.
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeletingSampleId(null)} className="btn-secondary">Cancel</button>
          <button onClick={handleDeleteSample} disabled={deletingSample} className="btn-danger">
            {deletingSample ? 'Deleting...' : 'Delete Sample'}
          </button>
        </div>
      </Modal>
    </div>
  );
}
