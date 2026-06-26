'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Download } from 'lucide-react';
import {
  getSample,
  getARGs,
  getPlasmids,
  getPlasmidMap,
  getISElements,
  getVirulence,
  getJobs,
  getIntegrons,
  getPointMutations,
  getSampleSummary,
  getCRISPRResults,
  getDefenseSystems,
  getICEResults,
} from '@/lib/api';
import type {
  Sample,
  ARGResult,
  PlasmidResult,
  PlasmidMapData,
  ISElementData,
  VirulenceResult,
  AnalysisJob,
  SampleSummary,
  IntegronResult,
  PointMutationResult,
  CRISPRResultData,
  DefenseSystemResult,
  ICEResultData,
} from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';
import ARGTable from '@/components/ARGTable';
import PlasmidMap from '@/components/PlasmidMap';
import LinearGenomeMap from '@/components/LinearGenomeMap';

const TABS = ['Summary', 'Resistance Genes', 'Plasmids', 'Mobile Elements', 'Defense Systems', 'Virulence'] as const;

function downloadTSV(filename: string, headers: string[], rows: (string | number | boolean | null | undefined)[][]) {
  const tsv = [headers.join('\t'), ...rows.map((r) => r.map((v) => v ?? '').join('\t'))].join('\n');
  const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
type Tab = (typeof TABS)[number];

function authDownload(url: string, openInTab = false) {
  const token = localStorage.getItem('radar_token');
  fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    .then(res => {
      if (!res.ok) throw new Error('Download failed');
      const disposition = res.headers.get('content-disposition');
      const match = disposition?.match(/filename=(.+)/);
      const filename = match ? match[1] : 'download';
      return res.blob().then(blob => ({ blob, filename }));
    })
    .then(({ blob, filename }) => {
      const objUrl = URL.createObjectURL(blob);
      if (openInTab) {
        window.open(objUrl, '_blank');
      } else {
        const a = document.createElement('a');
        a.href = objUrl;
        a.download = filename;
        a.click();
      }
    })
    .catch(() => alert('Download failed'));
}

export default function SampleDetailPage() {
  const params = useParams();
  const sampleId = params.id as string;

  const [tab, setTab] = useState<Tab>('Summary');
  const [sample, setSample] = useState<Sample | null>(null);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [args, setArgs] = useState<ARGResult[]>([]);
  const [plasmids, setPlasmids] = useState<PlasmidResult[]>([]);
  const [plasmidMaps, setPlasmidMaps] = useState<PlasmidMapData[]>([]);
  const [isData, setIsData] = useState<ISElementData | null>(null);
  const [flanking, setFlanking] = useState(5000);
  const [integrons, setIntegrons] = useState<IntegronResult[]>([]);
  const [pointMutations, setPointMutations] = useState<PointMutationResult[]>([]);
  const [virulence, setVirulence] = useState<VirulenceResult[]>([]);
  const [crisprs, setCrisprs] = useState<CRISPRResultData[]>([]);
  const [defenseSystems, setDefenseSystems] = useState<DefenseSystemResult[]>([]);
  const [ices, setIces] = useState<ICEResultData[]>([]);
  const [summary, setSummary] = useState<SampleSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSample = useCallback(async () => {
    try {
      const s = await getSample(sampleId);
      setSample(s);
      const [jobList, sum] = await Promise.all([
        getJobs(sampleId).catch(() => []),
        getSampleSummary(sampleId).catch(() => null),
      ]);
      setJobs(jobList);
      setSummary(sum);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sample');
    } finally {
      setLoading(false);
    }
  }, [sampleId]);

  useEffect(() => { loadSample(); }, [loadSample]);

  useEffect(() => {
    if (!sample) return;
    if (tab === 'Resistance Genes' && args.length === 0) {
      getARGs(sampleId).then(setArgs).catch(() => {});
      getPointMutations(sampleId).then(setPointMutations).catch(() => {});
    } else if (tab === 'Plasmids' && plasmids.length === 0) {
      getPlasmids(sampleId).then(setPlasmids).catch(() => {});
      getPlasmidMap(sampleId).then(setPlasmidMaps).catch(() => {});
    } else if (tab === 'Mobile Elements' && !isData) {
      getIntegrons(sampleId).then(setIntegrons).catch(() => {});
      getISElements(sampleId, flanking).then(setIsData).catch(() => {});
    } else if (tab === 'Defense Systems' && crisprs.length === 0 && defenseSystems.length === 0) {
      getCRISPRResults(sampleId).then(setCrisprs).catch(() => {});
      getDefenseSystems(sampleId).then(setDefenseSystems).catch(() => {});
      getICEResults(sampleId).then(setIces).catch(() => {});
    } else if (tab === 'Virulence' && virulence.length === 0) {
      getVirulence(sampleId).then(setVirulence).catch(() => {});
    }
  }, [tab, sample, sampleId, args.length, plasmids.length, isData, crisprs.length, defenseSystems.length, virulence.length]);

  // Refetch IS data when flanking distance changes (debounced)
  useEffect(() => {
    if (tab !== 'Mobile Elements' || !sample) return;
    const timer = setTimeout(() => {
      getISElements(sampleId, flanking).then(setIsData).catch(() => {});
    }, 300);
    return () => clearTimeout(timer);
  }, [flanking, sampleId, tab, sample]);

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
        <Link href="/" className="text-blue-400 hover:text-blue-300 mt-2 inline-block">Back to Dashboard</Link>
      </div>
    );
  }

  return (
    <div>
      <Link
        href="/results"
        className="text-sm text-gray-400 hover:text-gray-200 flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Results
      </Link>

      {error && (
        <div className="mb-6 p-4 bg-red-600/20 border border-red-600/50 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {/* Sample header */}
      <div className="card mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">{sample.name}</h1>
            <div className="flex items-center gap-4 mt-1">
              <span className="text-gray-400 text-sm">Type: {sample.sample_type}</span>
              {summary?.species && (
                <span className="text-sm italic text-gray-300">{summary.species}</span>
              )}
              {summary?.mlst_st && (
                <span className="text-sm px-2 py-0.5 bg-blue-600/20 text-blue-300 rounded">ST{summary.mlst_st}</span>
              )}
              {summary?.serotype && (
                <span className="text-sm px-2 py-0.5 bg-cyan-600/20 text-cyan-300 rounded">{summary.serotype}</span>
              )}
            </div>
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

      {/* ── Summary tab ── */}
      {tab === 'Summary' && (
        <div className="space-y-6">
          {/* Read QC */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-100">Read QC (fastp)</h2>
              <button
                onClick={() => authDownload(`/api/pipeline/qc/${sampleId}/fastp`, true)}
                className="btn-secondary text-xs flex items-center gap-1.5"
              >
                View Report
              </button>
            </div>
          </div>

          {/* Assembly QC */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-100">Assembly Quality</h2>
              <div className="flex items-center gap-2">
                {summary?.quast && (
                  <button
                    onClick={() => authDownload(`/api/pipeline/qc/${sampleId}/quast`, true)}
                    className="btn-secondary text-xs flex items-center gap-1.5"
                  >
                    View QUAST Report
                  </button>
                )}
                {summary?.quast && (
                  <button
                    onClick={() => authDownload(`/api/pipeline/assembly/${sampleId}`)}
                    className="btn-secondary text-xs flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download FASTA
                  </button>
                )}
              </div>
            </div>
            {summary?.quast ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className="p-3 bg-gray-800/50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-blue-400">
                    {summary.quast.total_length ? (summary.quast.total_length / 1e6).toFixed(2) : '-'}
                  </p>
                  <p className="text-xs text-gray-400">Total Length (Mbp)</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-green-400">
                    {summary.quast.n50 ? Math.round(summary.quast.n50 / 1000).toLocaleString() : '-'}
                  </p>
                  <p className="text-xs text-gray-400">N50 (kbp)</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-yellow-400">{summary.quast.num_contigs ?? '-'}</p>
                  <p className="text-xs text-gray-400">Contigs</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-purple-400">
                    {summary.quast.largest_contig ? Math.round(summary.quast.largest_contig / 1000).toLocaleString() : '-'}
                  </p>
                  <p className="text-xs text-gray-400">Largest (kbp)</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center">
                  <p className="text-2xl font-bold text-gray-300">{summary.quast.gc_percent?.toFixed(1) ?? '-'}%</p>
                  <p className="text-xs text-gray-400">GC Content</p>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">QUAST results not available.</p>
            )}
          </div>

          {/* Resistance Profile: ARG + MRG */}
          {summary && ((summary.drug_resistance && summary.drug_resistance.length > 0) || (summary.bacmet && summary.bacmet.length > 0)) && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-100 mb-3">Resistance Profile</h2>
              {/* ARG — Antibiotic Resistance Genes */}
              {summary.drug_resistance && summary.drug_resistance.length > 0 && (
                <div className="mb-4">
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">
                    ARG — {summary.arg_count} gene{summary.arg_count !== 1 ? 's' : ''} across {summary.drug_resistance.length} drug class{summary.drug_resistance.length !== 1 ? 'es' : ''}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {summary.drug_resistance.map((dc: string) => (
                      <span key={dc} className="px-2.5 py-1 bg-red-600/15 text-red-300 border border-red-600/30 rounded-lg text-xs font-medium">
                        {dc}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {/* MRG — Metal Resistance Genes */}
              {summary.bacmet && summary.bacmet.length > 0 && (() => {
                const compounds = Array.from(new Set(summary.bacmet.map((b: { compound: string }) => b.compound).filter(Boolean)));
                return (
                  <div>
                    <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">
                      MRG — {summary.bacmet.length} gene{summary.bacmet.length !== 1 ? 's' : ''} ({compounds.length} compound{compounds.length !== 1 ? 's' : ''})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {compounds.map((c: string) => (
                        <span key={c} className="px-2.5 py-1 bg-orange-600/15 text-orange-300 border border-orange-600/30 rounded-lg text-xs font-medium">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Predicted Disease / Pathotype */}
          {summary?.pathotype && summary.pathotype.pathotypes.length > 0 && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-100 mb-3">Predicted Pathotype & Disease</h2>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Pathotype</p>
                  <div className="flex flex-wrap gap-2">
                    {summary.pathotype.pathotypes.map((pt) => (
                      <span key={pt} className="px-3 py-1.5 bg-purple-600/20 text-purple-300 border border-purple-600/30 rounded-lg text-sm font-medium">
                        {pt}
                      </span>
                    ))}
                  </div>
                </div>
                {summary.pathotype.predicted_diseases.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Potential Diseases</p>
                    <div className="flex flex-wrap gap-2">
                      {summary.pathotype.predicted_diseases.map((d) => (
                        <span key={d} className="px-2.5 py-1 bg-orange-600/15 text-orange-300 border border-orange-600/30 rounded-lg text-xs">
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {summary.pathotype.key_evidence.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Key Evidence</p>
                    <div className="flex flex-wrap gap-2">
                      {summary.pathotype.key_evidence.map((e) => (
                        <span key={e} className="px-2 py-0.5 bg-gray-800 text-gray-300 rounded text-xs">
                          {e}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* BUSCO */}
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-100 mb-4">Genome Completeness (BUSCO)</h2>
            {summary?.busco ? (
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <div className="flex h-6 rounded-full overflow-hidden bg-gray-800">
                      <div
                        className="bg-green-500 transition-all"
                        style={{ width: `${summary.busco.complete || 0}%` }}
                        title={`Complete: ${summary.busco.complete}%`}
                      />
                      <div
                        className="bg-yellow-500 transition-all"
                        style={{ width: `${summary.busco.fragmented || 0}%` }}
                        title={`Fragmented: ${summary.busco.fragmented}%`}
                      />
                      <div
                        className="bg-red-500 transition-all"
                        style={{ width: `${summary.busco.missing || 0}%` }}
                        title={`Missing: ${summary.busco.missing}%`}
                      />
                    </div>
                  </div>
                  <span className="text-lg font-bold text-green-400 w-20 text-right">{summary.busco.complete}%</span>
                </div>
                <div className="flex gap-6 text-sm">
                  <span className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                    <span className="text-gray-400">Complete: {summary.busco.complete}%</span>
                    <span className="text-gray-600">(S: {summary.busco.single_copy}%, D: {summary.busco.duplicated}%)</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-yellow-500" />
                    <span className="text-gray-400">Fragmented: {summary.busco.fragmented}%</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <span className="text-gray-400">Missing: {summary.busco.missing}%</span>
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">BUSCO results not available.</p>
            )}
          </div>

        </div>
      )}

      {/* ── Resistance Genes tab ── */}
      {tab === 'Resistance Genes' && (
        <div className="space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-100">Resistance Genes (AMRFinderPlus)</h2>
              {args.length > 0 && (
                <button
                  onClick={() => authDownload(`/api/samples/${sampleId}/gene-sequences?type=arg`)}
                  className="btn-secondary flex items-center gap-2 text-xs"
                >
                  <Download className="w-3.5 h-3.5" />
                  FASTA
                </button>
              )}
            </div>
            <ARGTable results={args} />
          </div>

          {pointMutations.length > 0 && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Point Mutations (PointFinder)</h2>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">Gene</th>
                      <th className="table-header">Mutation</th>
                      <th className="table-header">Drug Class</th>
                      <th className="table-header">Resistance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {pointMutations.map((pm) => (
                      <tr key={pm.id} className="hover:bg-gray-800/50">
                        <td className="table-cell font-medium text-gray-200">{pm.gene}</td>
                        <td className="table-cell font-mono text-sm text-orange-300">{pm.mutation}</td>
                        <td className="table-cell">{pm.drug_class}</td>
                        <td className="table-cell">{pm.resistance}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Plasmids tab ── */}
      {tab === 'Plasmids' && (
        <div className="space-y-6">
          {plasmidMaps.length === 0 && plasmids.length === 0 ? (
            <div className="card">
              <p className="text-gray-500 text-center py-8">No plasmid results available.</p>
            </div>
          ) : (
            <>
              {/* Only show maps for contigs that have features */}
              {plasmidMaps.filter((pm) => pm.features.length > 0).map((pm) => (
                <PlasmidMap key={pm.contig} data={pm} />
              ))}

              {/* Plasmid summary table */}
              {plasmids.length > 0 && (
                <div className="card">
                  <h2 className="text-lg font-semibold text-gray-100 mb-4">Plasmid Results (MOB-recon)</h2>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-800">
                          <th className="table-header">Plasmid ID</th>
                          <th className="table-header">Replicon Type</th>
                          <th className="table-header">MOB Type</th>
                          <th className="table-header">Transferable</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-800">
                        {plasmids.map((p) => (
                          <tr key={p.id} className="hover:bg-gray-800/50">
                            <td className="table-cell font-medium text-gray-200">{p.plasmid_id}</td>
                            <td className="table-cell">{p.replicon || '-'}</td>
                            <td className="table-cell">{p.mob_type || '-'}</td>
                            <td className="table-cell">
                              <span className={`px-2 py-0.5 rounded text-xs ${
                                p.predicted_transferability ? 'bg-red-600/20 text-red-300' : 'bg-gray-600/20 text-gray-300'
                              }`}>{p.predicted_transferability ? 'Yes' : 'No'}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Mobile Elements tab ── */}
      {tab === 'Mobile Elements' && (
        <div className="space-y-6">
          {/* Controls */}
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-semibold text-gray-100">Mobile Elements</h2>
              <div className="flex items-center gap-3">
                {isData && isData.is_elements.length > 0 && (
                  <button
                    onClick={() => downloadTSV(
                      `${sample?.name || 'sample'}_mobile_elements.tsv`,
                      ['IS Name', 'Family', 'Contig', 'Location', 'Start', 'End', 'Nearby Genes'],
                      isData.is_elements.map((el: any) => [
                        el.is_name, el.is_family, el.contig,
                        el.molecule_type === 'plasmid' ? el.plasmid_id : 'chromosome',
                        el.start, el.end,
                        (el.nearby_genes || []).map((g: any) => `${g.gene}(${g.type},${g.distance}bp)`).join('; '),
                      ])
                    )}
                    className="btn-secondary flex items-center gap-2 text-xs"
                  >
                    <Download className="w-3.5 h-3.5" />
                    TSV
                  </button>
                )}
                <label className="text-xs text-gray-400">Flanking:</label>
                <input type="range" min={0} max={20000} step={500} value={flanking}
                  onChange={(e) => setFlanking(Number(e.target.value))}
                  className="w-32 accent-blue-500" />
                <span className="text-sm text-gray-300 font-mono w-16 text-right">{(flanking/1000).toFixed(1)} kb</span>
              </div>
            </div>
            {isData && (
              <p className="text-xs text-gray-400">
                {isData.total_is} IS elements detected — {isData.with_nearby || 0} flanked by ARG/VF within {(flanking/1000).toFixed(1)} kb
              </p>
            )}
          </div>

          {!isData ? (
            <div className="card"><p className="text-gray-500 text-center py-6">Loading...</p></div>
          ) : isData.is_elements.length === 0 ? (
            <div className="card"><p className="text-gray-500 text-center py-6">No mobile elements detected.</p></div>
          ) : (
            <>
              {/* Synteny maps for IS elements with nearby ARGs/VFs */}
              {isData.synteny_regions && isData.synteny_regions.length > 0 ? (
                <div className="space-y-4">
                  {isData.synteny_regions.map((region: any, i: number) => (
                    <LinearGenomeMap
                      key={`${region.contig}-${region.is_name}-${i}`}
                      title={`${region.is_name}${region.features?.[0]?.family && region.features[0].family !== region.is_name ? ` (${region.features[0].family})` : ''} — ${region.contig}`}
                      subtitle={`${region.molecule_type}${region.plasmid_id ? ` (${region.plasmid_id})` : ''} — ${(region.length / 1000).toFixed(1)} kb region — ${region.features.length} features`}
                      length={region.region_end}
                      features={region.features}
                      regionStart={region.region_start}
                      regionEnd={region.region_end}
                    />
                  ))}
                </div>
              ) : (
                <div className="card">
                  <p className="text-gray-500 text-center py-6">No IS elements flanked by ARGs or VFs within {(flanking/1000).toFixed(1)} kb.</p>
                </div>
              )}
            </>
          )}

          {/* Integrons */}
          {integrons.length > 0 && (
            <div className="card">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Integrons (IntegronFinder)</h2>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">ID</th>
                      <th className="table-header">Type</th>
                      <th className="table-header">Contig</th>
                      <th className="table-header">Position</th>
                      <th className="table-header">Gene Cassettes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {integrons.map((ig) => (
                      <tr key={ig.id} className="hover:bg-gray-800/50">
                        <td className="table-cell text-gray-200">{ig.integron_id}</td>
                        <td className="table-cell">
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            ig.integron_type === 'complete' ? 'bg-green-600/20 text-green-300'
                            : ig.integron_type === 'CALIN' ? 'bg-yellow-600/20 text-yellow-300'
                            : 'bg-gray-600/20 text-gray-300'
                          }`}>{ig.integron_type}</span>
                        </td>
                        <td className="table-cell font-mono text-xs">{ig.contig}</td>
                        <td className="table-cell font-mono text-xs">{ig.start?.toLocaleString()}-{ig.end?.toLocaleString()}</td>
                        <td className="table-cell">
                          {ig.cassettes && Array.isArray(ig.cassettes) && ig.cassettes.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {ig.cassettes.filter((c: any) => c.annotation && c.annotation !== 'protein').map((c: any, i: number) => (
                                <span key={i} className={`px-1.5 py-0.5 rounded text-xs ${
                                  c.annotation === 'intI' ? 'bg-purple-600/20 text-purple-300'
                                  : c.annotation === 'attC' ? 'bg-blue-600/20 text-blue-300'
                                  : 'bg-gray-700 text-gray-300'
                                }`}>{c.annotation}</span>
                              ))}
                            </div>
                          ) : <span className="text-gray-500">-</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Defense Systems tab ── */}
      {tab === 'Defense Systems' && (
        <div className="space-y-6">
          {/* CRISPR-Cas */}
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-100 mb-4">CRISPR-Cas Systems (CRISPRCasFinder)</h2>
            {crisprs.length === 0 ? (
              <p className="text-gray-500 text-center py-6">No CRISPR-Cas systems detected.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">ID</th>
                      <th className="table-header">Cas Type</th>
                      <th className="table-header">Spacers</th>
                      <th className="table-header">Repeat Length</th>
                      <th className="table-header">Evidence</th>
                      <th className="table-header">Contig</th>
                      <th className="table-header">Position</th>
                      <th className="table-header">Cas Genes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {crisprs.map((c) => (
                      <tr key={c.id} className="hover:bg-gray-800/50">
                        <td className="table-cell font-medium text-gray-200">{c.crispr_id}</td>
                        <td className="table-cell">
                          {c.cas_type ? (
                            <span className="px-2 py-0.5 bg-orange-600/20 text-orange-300 rounded text-xs">{c.cas_type}</span>
                          ) : <span className="text-gray-600">orphan array</span>}
                        </td>
                        <td className="table-cell text-center">{c.num_spacers}</td>
                        <td className="table-cell text-center">{c.repeat_length ?? '-'} bp</td>
                        <td className="table-cell text-center">
                          {c.evidence_level && (
                            <span className={`px-2 py-0.5 rounded text-xs ${
                              c.evidence_level >= 4 ? 'bg-green-600/20 text-green-300'
                              : c.evidence_level >= 3 ? 'bg-yellow-600/20 text-yellow-300'
                              : 'bg-gray-600/20 text-gray-300'
                            }`}>Level {c.evidence_level}</span>
                          )}
                        </td>
                        <td className="table-cell font-mono text-xs">{c.contig}</td>
                        <td className="table-cell text-sm">{c.start?.toLocaleString()}-{c.end?.toLocaleString()}</td>
                        <td className="table-cell">
                          {c.cas_genes && c.cas_genes.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {c.cas_genes.map((g, i) => (
                                <span key={i} className="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-xs">{g}</span>
                              ))}
                            </div>
                          ) : <span className="text-gray-600">-</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Defense Systems (DefenseFinder) */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-100">Defense Systems (DefenseFinder)</h2>
              {defenseSystems.length > 0 && (
                <button
                  onClick={() => downloadTSV(
                    `${sample?.name || 'sample'}_defense_systems.tsv`,
                    ['System Type', 'Subtype', 'Contig', 'Protein Count', 'Genes'],
                    defenseSystems.map((d) => [d.system_type, d.subtype, d.contig, d.protein_count, d.genes?.join('; ') || ''])
                  )}
                  className="btn-secondary flex items-center gap-2 text-xs"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download TSV
                </button>
              )}
            </div>
            <p className="text-gray-400 text-xs mb-3">
              Includes RM systems, abortive infection (Abi), BREX, DISARM, Zorya, Thoeris, retrons, CBASS, and more.
            </p>
            {defenseSystems.length === 0 ? (
              <p className="text-gray-500 text-center py-6">No defense systems detected.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">System Type</th>
                      <th className="table-header">Subtype</th>
                      <th className="table-header text-center">Proteins</th>
                      <th className="table-header">Contig</th>
                      <th className="table-header">Position</th>
                      <th className="table-header">Genes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {defenseSystems.map((d) => (
                      <tr key={d.id} className="hover:bg-gray-800/50">
                        <td className="table-cell">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            d.system_type.toLowerCase().includes('rm') || d.system_type.toLowerCase().includes('restriction')
                              ? 'bg-blue-600/20 text-blue-300'
                              : d.system_type.toLowerCase().includes('abi') || d.system_type.toLowerCase().includes('abort')
                              ? 'bg-red-600/20 text-red-300'
                              : 'bg-purple-600/20 text-purple-300'
                          }`}>{d.system_type}</span>
                        </td>
                        <td className="table-cell text-sm text-gray-300">{d.subtype || '-'}</td>
                        <td className="table-cell text-center">{d.protein_count ?? '-'}</td>
                        <td className="table-cell font-mono text-xs">{d.contig}</td>
                        <td className="table-cell text-sm">{d.start?.toLocaleString()}-{d.end?.toLocaleString()}</td>
                        <td className="table-cell">
                          {d.genes && d.genes.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {d.genes.slice(0, 5).map((g, i) => (
                                <span key={i} className="px-1.5 py-0.5 bg-gray-700 text-gray-300 rounded text-xs">{g}</span>
                              ))}
                              {d.genes.length > 5 && (
                                <span className="px-1.5 py-0.5 text-gray-500 text-xs">+{d.genes.length - 5} more</span>
                              )}
                            </div>
                          ) : <span className="text-gray-600">-</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ICE */}
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-100 mb-4">ICE / IME (ICEfinder)</h2>
            {ices.length === 0 ? (
              <p className="text-gray-500 text-center py-6">No integrative and conjugative elements detected.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">ID</th>
                      <th className="table-header">Type</th>
                      <th className="table-header">Size (kbp)</th>
                      <th className="table-header">Contig</th>
                      <th className="table-header">Position</th>
                      <th className="table-header">Integrase</th>
                      <th className="table-header">tRNA</th>
                      <th className="table-header">ARGs</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {ices.map((ice) => (
                      <tr key={ice.id} className="hover:bg-gray-800/50">
                        <td className="table-cell font-medium text-gray-200">{ice.ice_id}</td>
                        <td className="table-cell">
                          <span className="px-2 py-0.5 bg-cyan-600/20 text-cyan-300 rounded text-xs">{ice.ice_type}</span>
                        </td>
                        <td className="table-cell">{ice.length ? (ice.length / 1000).toFixed(1) : '-'}</td>
                        <td className="table-cell font-mono text-xs">{ice.contig}</td>
                        <td className="table-cell text-sm">{ice.start?.toLocaleString()}-{ice.end?.toLocaleString()}</td>
                        <td className="table-cell text-sm">{ice.integrase || '-'}</td>
                        <td className="table-cell text-sm">{ice.nearest_trna || '-'}</td>
                        <td className="table-cell">
                          {ice.arg_genes && ice.arg_genes.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {ice.arg_genes.map((g, i) => (
                                <span key={i} className="px-1.5 py-0.5 bg-red-600/20 text-red-300 rounded text-xs">{g}</span>
                              ))}
                            </div>
                          ) : <span className="text-gray-600">-</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Virulence tab ── */}
      {tab === 'Virulence' && (
        <div className="space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-100">Virulence Factors (AMRFinderPlus)</h2>
              {virulence.length > 0 && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => authDownload(`/api/samples/${sampleId}/gene-sequences?type=virulence`)}
                    className="btn-secondary flex items-center gap-2 text-xs"
                  >
                    <Download className="w-3.5 h-3.5" />
                    FASTA
                  </button>
                  <button
                    onClick={() => downloadTSV(
                      `${sample?.name || 'sample'}_virulence.tsv`,
                      ['Gene', 'Description', 'Category', 'Identity%', 'Coverage%', 'Contig', 'Database'],
                      virulence.map((v) => [v.gene, v.description || '', v.category, v.identity, v.coverage, v.contig, v.database])
                    )}
                    className="btn-secondary flex items-center gap-2 text-xs"
                  >
                    <Download className="w-3.5 h-3.5" />
                    TSV
                  </button>
                </div>
              )}
            </div>
            {virulence.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No virulence factors detected.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-800">
                      <th className="table-header">Gene</th>
                      <th className="table-header">Description</th>
                      <th className="table-header">Category</th>
                      <th className="table-header">Identity%</th>
                      <th className="table-header">Coverage%</th>
                      <th className="table-header">Contig</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {virulence.map((v) => (
                      <tr key={v.id} className="hover:bg-gray-800/50">
                        <td className="table-cell font-medium text-gray-200">{v.gene}</td>
                        <td className="table-cell text-sm text-gray-400">{v.description || '-'}</td>
                        <td className="table-cell">{v.category}</td>
                        <td className="table-cell">{v.identity?.toFixed(1)}%</td>
                        <td className="table-cell">{v.coverage?.toFixed(1)}%</td>
                        <td className="table-cell font-mono text-xs">{v.contig}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
