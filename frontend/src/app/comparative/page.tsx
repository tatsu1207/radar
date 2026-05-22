'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { GitBranch, ArrowRight } from 'lucide-react';
import { listProjects, listSamples } from '@/lib/api';
import type { Project, Sample } from '@/lib/api';

export default function ComparativePage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [sampleCounts, setSampleCounts] = useState<Record<string, { total: number; complete: number }>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listProjects()
      .then(async (projs) => {
        setProjects(projs);
        // Load sample counts per project
        const counts: Record<string, { total: number; complete: number }> = {};
        await Promise.all(
          projs.map(async (p) => {
            try {
              const samples = await listSamples(p.id);
              counts[p.id] = {
                total: samples.length,
                complete: samples.filter((s: Sample) => s.status === 'complete').length,
              };
            } catch {
              counts[p.id] = { total: 0, complete: 0 };
            }
          })
        );
        setSampleCounts(counts);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
        <h1 className="text-2xl font-bold text-white">Comparative Analysis</h1>
        <p className="text-gray-400 text-sm mt-1">
          Select a project to run pan-genome, SNP phylogeny, or Mashtree analyses across its samples.
        </p>
      </div>

      {projects.length === 0 ? (
        <div className="card text-center py-12">
          <GitBranch className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400">No projects yet. Create a project and add samples first.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => {
            const counts = sampleCounts[project.id] || { total: 0, complete: 0 };
            const canAnalyze = counts.complete >= 2;

            return (
              <button
                key={project.id}
                onClick={() => router.push(`/projects/${project.id}/comparative`)}
                className="card text-left hover:border-blue-500/50 transition-colors group"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-100 group-hover:text-blue-400 transition-colors">
                      {project.name}
                    </h3>
                    <p className="text-gray-500 text-sm mt-1 line-clamp-2">
                      {project.description || 'No description'}
                    </p>
                    <div className="flex items-center gap-3 mt-3">
                      <span className="text-xs text-gray-400">
                        {counts.total} sample{counts.total !== 1 ? 's' : ''}
                      </span>
                      <span className={`text-xs ${canAnalyze ? 'text-green-400' : 'text-yellow-400'}`}>
                        {counts.complete} complete
                      </span>
                    </div>
                    {!canAnalyze && (
                      <p className="text-xs text-yellow-500 mt-2">
                        Need at least 2 completed samples
                      </p>
                    )}
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-600 group-hover:text-blue-400 transition-colors mt-1" />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
