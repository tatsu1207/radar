'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { listProjects, listSamples, uploadFiles } from '@/lib/api';
import type { Project, Sample } from '@/lib/api';
import FileUpload from '@/components/FileUpload';

export default function UploadPage() {
  const searchParams = useSearchParams();
  const preselectedProject = searchParams.get('project');
  const preselectedSample = searchParams.get('sample');

  const [projects, setProjects] = useState<Project[]>([]);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>(
    preselectedProject ?? ''
  );
  const [selectedSample, setSelectedSample] = useState<string>(
    preselectedSample ?? ''
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedProject) {
      listSamples(selectedProject)
        .then(setSamples)
        .catch(() => setSamples([]));
    } else {
      setSamples([]);
      setSelectedSample('');
    }
  }, [selectedProject]);

  async function handleUpload(files: File[]) {
    if (!selectedSample) {
      setError('Please select a sample first');
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      const result = await uploadFiles(selectedSample, files);
      setSuccess(`Successfully uploaded ${result.uploaded.length} file(s)`);
    } catch (err) {
      throw err; // Let FileUpload handle the error state
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
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Upload Files</h1>
        <p className="text-gray-400 text-sm mt-1">Upload sequencing data and files to a sample</p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}
      {success && (
        <div className="mb-6 p-4 bg-green-600/20 border border-green-600/50 rounded-lg text-green-300 text-sm">
          {success}
        </div>
      )}

      <div className="card mb-6">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Select Target</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Project</label>
            <select
              value={selectedProject}
              onChange={(e) => {
                setSelectedProject(e.target.value);
                setSelectedSample('');
              }}
              className="input w-full"
            >
              <option value="">Select a project...</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Sample</label>
            <select
              value={selectedSample}
              onChange={(e) => setSelectedSample(e.target.value)}
              className="input w-full"
              disabled={!selectedProject}
            >
              <option value="">Select a sample...</option>
              {samples.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="text-lg font-semibold text-gray-100 mb-4">Upload Files</h2>
        {!selectedSample ? (
          <div className="text-center py-8 text-gray-500">
            Please select a project and sample above to upload files.
          </div>
        ) : (
          <FileUpload onUpload={handleUpload} />
        )}
      </div>
    </div>
  );
}
