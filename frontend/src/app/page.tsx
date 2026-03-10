'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { FolderKanban, TestTubes, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react';
import { listProjects, listSamples } from '@/lib/api';
import type { Project, Sample } from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

interface DashboardStats {
  totalProjects: number;
  totalSamples: number;
  analysesComplete: number;
  highRiskSamples: number;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats>({
    totalProjects: 0,
    totalSamples: 0,
    analysesComplete: 0,
    highRiskSamples: 0,
  });
  const [recentSamples, setRecentSamples] = useState<Sample[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const projects = await listProjects().catch(() => [] as Project[]);

        // Load samples from all projects
        const allSamples: Sample[] = [];
        for (const p of projects) {
          const s = await listSamples(p.id).catch(() => [] as Sample[]);
          allSamples.push(...s);
        }

        const completeSamples = allSamples.filter((s) => s.status === 'complete').length;

        setStats({
          totalProjects: projects.length,
          totalSamples: allSamples.length,
          analysesComplete: completeSamples,
          highRiskSamples: 0,
        });

        setRecentSamples(
          [...allSamples].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5)
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, []);

  const statCards = [
    { label: 'Total Projects', value: stats.totalProjects, icon: FolderKanban, color: 'text-blue-400', bg: 'bg-blue-600/20' },
    { label: 'Total Samples', value: stats.totalSamples, icon: TestTubes, color: 'text-green-400', bg: 'bg-green-600/20' },
    { label: 'Analyses Complete', value: stats.analysesComplete, icon: CheckCircle, color: 'text-purple-400', bg: 'bg-purple-600/20' },
    { label: 'High Risk Samples', value: stats.highRiskSamples, icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-600/20' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Welcome to RADAR</h1>
        <p className="text-gray-400">
          Resistome Analysis, Detection, Assessment &amp; Risk -- your comprehensive platform for antibiotic resistance analysis.
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-yellow-600/20 border border-yellow-600/50 rounded-lg text-yellow-300 text-sm">
          Note: Could not connect to the backend API. Showing default values. ({error})
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="card">
              <div className="flex items-center justify-between mb-3">
                <div className={`p-2 rounded-lg ${card.bg}`}>
                  <Icon className={`w-5 h-5 ${card.color}`} />
                </div>
              </div>
              <p className="text-2xl font-bold text-white">{card.value}</p>
              <p className="text-sm text-gray-400">{card.label}</p>
            </div>
          );
        })}
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Samples */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-100">Recent Samples</h2>
            <Link href="/projects" className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1">
              View all <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          {recentSamples.length === 0 ? (
            <p className="text-gray-500 text-sm py-4">No samples yet. Create a project and add samples to get started.</p>
          ) : (
            <div className="space-y-3">
              {recentSamples.map((sample) => (
                <Link
                  key={sample.id}
                  href={`/samples/${sample.id}`}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-800 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-200">{sample.name}</p>
                    <p className="text-xs text-gray-500">{sample.sample_type}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={sample.status} />
                    <span className="text-xs text-gray-500">
                      {new Date(sample.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Quick Links */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-100">Quick Actions</h2>
          </div>
          <div className="space-y-3">
            <Link
              href="/analysis"
              className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <p className="text-sm font-medium text-gray-200">Run Analysis Pipeline</p>
              <ArrowRight className="w-4 h-4 text-gray-400" />
            </Link>
            <Link
              href="/results"
              className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <p className="text-sm font-medium text-gray-200">View Results</p>
              <ArrowRight className="w-4 h-4 text-gray-400" />
            </Link>
            <Link
              href="/risk"
              className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-800 transition-colors"
            >
              <p className="text-sm font-medium text-gray-200">Risk Assessment</p>
              <ArrowRight className="w-4 h-4 text-gray-400" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
