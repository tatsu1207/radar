'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import {
  getSample,
  getARGs,
  getPlasmids,
  getMobility,
  getVirulence,
  getRisk,
  getMetadata,
  updateMetadata,
  getJobs,
  getComparison,
} from '@/lib/api';
import type {
  Sample,
  ARGResult,
  PlasmidResult,
  MobilityResult,
  VirulenceResult,
  RiskScore,
  Metadata,
  AnalysisJob,
  PhenotypeComparison,
} from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';
import ARGTable from '@/components/ARGTable';
import RadarChartComponent from '@/components/RadarChart';
import MetadataForm from '@/components/MetadataForm';

const TABS = ['Overview', 'ARG Results', 'Plasmids', 'Mobility', 'Virulence', 'Risk', 'Phenotype'] as const;
type Tab = (typeof TABS)[number];

export default function SampleDetailPage() {
  const params = useParams();
  const sampleId = params.id as string;

  const [tab, setTab] = useState<Tab>('Overview');
  const [sample, setSample] = useState<Sample | null>(null);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [args, setArgs] = useState<ARGResult[]>([]);
  const [plasmids, setPlasmids] = useState<PlasmidResult[]>([]);
  const [mobility, setMobility] = useState<MobilityResult[]>([]);
  const [virulence, setVirulence] = useState<VirulenceResult[]>([]);
  const [riskScore, setRiskScore] = useState<RiskScore | null>(null);
  const [phenotype, setPhenotype] = useState<PhenotypeComparison[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSample = useCallback(async () => {
    try {
      const s = await getSample(sampleId);
      setSample(s);
      const [meta, jobList] = await Promise.all([
        getMetadata(sampleId).catch(() => null),
        getJobs(sampleId).catch(() => []),
      ]);
      setMetadata(meta);
      setJobs(jobList);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample');
    } finally {
      setLoading(false);
    }
  }, [sampleId]);

  useEffect(() => {
    loadSample();
  }, [loadSample]);

  // Load tab-specific data on tab change
  useEffect(() => {
    if (!sample) return;

    if (tab === 'ARG Results' && args.length === 0) {
      getARGs(sampleId).then(setArgs).catch(() => {});
    } else if (tab === 'Plasmids' && plasmids.length === 0) {
      getPlasmids(sampleId).then(setPlasmids).catch(() => {});
    } else if (tab === 'Mobility' && mobility.length === 0) {
      getMobility(sampleId).then(setMobility).catch(() => {});
    } else if (tab === 'Virulence' && virulence.length === 0) {
      getVirulence(sampleId).then(setVirulence).catch(() => {});
    } else if (tab === 'Risk' && !riskScore) {
      getRisk(sampleId).then(setRiskScore).catch(() => {});
    } else if (tab === 'Phenotype' && phenotype.length === 0) {
      getComparison(sampleId).then(setPhenotype).catch(() => {});
    }
  }, [tab, sample, sampleId, args.length, plasmids.length, mobility.length, virulence.length, riskScore, phenotype.length]);

  async function handleSaveMetadata(data: Partial<Omit<Metadata, 'id' | 'sample_id'>>) {
    const updated = await updateMetadata(sampleId, data);
    setMetadata(updated);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!sample) {
    return (
      <div className="text-center py-16">
        <p className="text-gray-400">Sample not found</p>
        <Link href="/projects" className="text-blue-400 hover:text-blue-300 mt-2 inline-block">Back to Projects</Link>
      </div>
    );
  }

  return (
    <div>
      <Link
        href={`/projects/${sample.project_id}`}
        className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Project
      </Link>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {/* Sample header */}
      <div className="card mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{sample.name}</h1>
            <p className="text-gray-400 text-sm mt-1">
              Type: {sample.sample_type} | Created: {new Date(sample.created_at).toLocaleDateString()}
            </p>
          </div>
          <StatusBadge status={sample.status} />
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                tab === t
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'Overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-100 mb-4">Metadata</h2>
            <MetadataForm metadata={metadata} onSave={handleSaveMetadata} />
          </div>
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-100 mb-4">Analysis Jobs</h2>
            {jobs.length === 0 ? (
              <p className="text-gray-500 text-sm">No analysis jobs yet.</p>
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => (
                  <div key={job.id} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-gray-200">{job.tool}</p>
                      <p className="text-xs text-gray-500">
                        {job.started_at ? new Date(job.started_at).toLocaleString() : 'Not started'}
                      </p>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'ARG Results' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Antibiotic Resistance Genes</h2>
          <ARGTable results={args} />
        </div>
      )}

      {tab === 'Plasmids' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Plasmid Results</h2>
          {plasmids.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No plasmid results available.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="table-header">Plasmid ID</th>
                    <th className="table-header">Replicon Type</th>
                    <th className="table-header">Mobility</th>
                    <th className="table-header">Size (bp)</th>
                    <th className="table-header">Contig</th>
                    <th className="table-header">ARG Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {plasmids.map((p) => (
                    <tr key={p.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="table-cell font-medium text-gray-200">{p.plasmid_id}</td>
                      <td className="table-cell">{p.replicon_type}</td>
                      <td className="table-cell">{p.mobility}</td>
                      <td className="table-cell">{p.size_bp.toLocaleString()}</td>
                      <td className="table-cell font-mono text-xs">{p.contig}</td>
                      <td className="table-cell">
                        <span className={p.arg_count > 0 ? 'text-orange-400 font-medium' : 'text-gray-500'}>
                          {p.arg_count}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'Mobility' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Mobile Genetic Elements</h2>
          {mobility.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No mobility results available.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="table-header">Element Type</th>
                    <th className="table-header">Element Name</th>
                    <th className="table-header">Contig</th>
                    <th className="table-header">Start</th>
                    <th className="table-header">End</th>
                    <th className="table-header">Nearby ARGs</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {mobility.map((m) => (
                    <tr key={m.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="table-cell">
                        <span className="px-2 py-0.5 bg-purple-600/20 text-purple-300 rounded text-xs">
                          {m.element_type}
                        </span>
                      </td>
                      <td className="table-cell font-medium text-gray-200">{m.element_name}</td>
                      <td className="table-cell font-mono text-xs">{m.contig}</td>
                      <td className="table-cell">{m.start.toLocaleString()}</td>
                      <td className="table-cell">{m.end.toLocaleString()}</td>
                      <td className="table-cell">
                        {m.nearby_args.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {m.nearby_args.map((arg, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-red-600/20 text-red-300 rounded text-xs">
                                {arg}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-gray-500">None</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'Virulence' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Virulence Factors</h2>
          {virulence.length === 0 ? (
            <p className="text-gray-500 text-center py-8">No virulence results available.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="table-header">Gene</th>
                    <th className="table-header">Virulence Factor</th>
                    <th className="table-header">Identity%</th>
                    <th className="table-header">Coverage%</th>
                    <th className="table-header">Contig</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {virulence.map((v) => (
                    <tr key={v.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="table-cell font-medium text-gray-200">{v.gene}</td>
                      <td className="table-cell">{v.virulence_factor}</td>
                      <td className="table-cell">{v.identity_percent.toFixed(1)}%</td>
                      <td className="table-cell">{v.coverage_percent.toFixed(1)}%</td>
                      <td className="table-cell font-mono text-xs">{v.contig}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'Risk' && (
        <div className="max-w-lg mx-auto">
          {riskScore ? (
            <RadarChartComponent riskScore={riskScore} />
          ) : (
            <div className="card text-center py-12">
              <p className="text-gray-500">Risk assessment not yet calculated. Run analysis first.</p>
            </div>
          )}
        </div>
      )}

      {tab === 'Phenotype' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-4">Phenotype Prediction vs Observed</h2>
          {phenotype.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              No phenotype data available. Add AST results and run prediction.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="table-header">Antibiotic</th>
                    <th className="table-header">Predicted</th>
                    <th className="table-header">Observed</th>
                    <th className="table-header">Concordance</th>
                    <th className="table-header">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {phenotype.map((p) => (
                    <tr key={p.antibiotic} className="hover:bg-gray-800/50 transition-colors">
                      <td className="table-cell font-medium text-gray-200">{p.antibiotic}</td>
                      <td className="table-cell">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            p.predicted === 'R'
                              ? 'bg-red-600/20 text-red-300'
                              : p.predicted === 'I'
                              ? 'bg-yellow-600/20 text-yellow-300'
                              : 'bg-green-600/20 text-green-300'
                          }`}
                        >
                          {p.predicted}
                        </span>
                      </td>
                      <td className="table-cell">
                        {p.observed ? (
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-semibold ${
                              p.observed === 'R'
                                ? 'bg-red-600/20 text-red-300'
                                : p.observed === 'I'
                                ? 'bg-yellow-600/20 text-yellow-300'
                                : 'bg-green-600/20 text-green-300'
                            }`}
                          >
                            {p.observed}
                          </span>
                        ) : (
                          <span className="text-gray-500">N/A</span>
                        )}
                      </td>
                      <td className="table-cell">
                        {p.concordance === null ? (
                          <span className="text-gray-500">--</span>
                        ) : p.concordance ? (
                          <span className="text-green-400">Match</span>
                        ) : (
                          <span className="text-red-400">Mismatch</span>
                        )}
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-gray-700 rounded-full h-1.5">
                            <div
                              className="bg-blue-500 h-1.5 rounded-full"
                              style={{ width: `${p.confidence * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-400">{(p.confidence * 100).toFixed(0)}%</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
