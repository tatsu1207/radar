'use client';

import { useState } from 'react';
import { ExternalLink, Download } from 'lucide-react';
import { openSampleFile } from '@/lib/api';
import type { SampleFiles, NanoStats } from '@/lib/api';

function num(v: string | undefined): number | null {
  if (!v) return null;
  const n = parseFloat(v.replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}

function fmtInt(v: string | undefined): string {
  const n = num(v);
  return n == null ? '-' : Math.round(n).toLocaleString();
}

function fmtBases(v: string | undefined): string {
  const n = num(v);
  if (n == null) return '-';
  return n >= 1e9 ? `${(n / 1e9).toFixed(2)} Gb` : `${(n / 1e6).toFixed(1)} Mb`;
}

function fmtDec(v: string | undefined): string {
  const n = num(v);
  return n == null ? '-' : n.toFixed(1);
}

// ">Q10": "5000 (100.0%) 25.4Mb" -> "100.0%"
function fmtCutoff(v: string | undefined): string {
  const m = v?.match(/\(([\d.]+%)\)/);
  return m ? m[1] : '-';
}

const ROWS: { label: string; get: (s: NanoStats) => string }[] = [
  { label: 'Reads', get: (s) => fmtInt(s['Number of reads']) },
  { label: 'Total bases', get: (s) => fmtBases(s['Total bases']) },
  { label: 'Read length N50 (bp)', get: (s) => fmtInt(s['Read length N50']) },
  { label: 'Mean / median length (bp)', get: (s) => `${fmtInt(s['Mean read length'])} / ${fmtInt(s['Median read length'])}` },
  { label: 'Mean / median quality (Q)', get: (s) => `${fmtDec(s['Mean read quality'])} / ${fmtDec(s['Median read quality'])}` },
  { label: 'Reads > Q10', get: (s) => fmtCutoff(s['Reads >Q10']) },
  { label: 'Reads > Q15', get: (s) => fmtCutoff(s['Reads >Q15']) },
  { label: 'Reads > Q20', get: (s) => fmtCutoff(s['Reads >Q20']) },
];

const STAGES = [
  { stage: 'raw' as const, title: 'Uploaded reads' },
  { stage: 'filtered' as const, title: 'After Chopper' },
];

export default function ReadQCCard({ sampleId, files }: { sampleId: string; files: SampleFiles | null }) {
  const [error, setError] = useState<string | null>(null);
  const open = (key: string, view: boolean) => {
    setError(null);
    openSampleFile(sampleId, key, view).catch((e) => setError(`Could not open file: ${e.message ?? e}`));
  };

  const qc = files?.read_qc;
  const stages = STAGES.filter(({ stage }) => qc?.nanoplot[stage]);
  const hasAny = !!qc && (qc.fastp || stages.length > 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <h2 className="text-lg font-semibold text-gray-100">Read QC</h2>
        {qc?.fastp && (
          <button onClick={() => open('fastp-html', true)} className="btn-secondary text-xs flex items-center gap-1.5">
            <ExternalLink className="w-3.5 h-3.5" />
            fastp report (Illumina)
          </button>
        )}
      </div>

      {!files && <p className="text-gray-500 text-sm">Loading…</p>}
      {files && !hasAny && (
        <p className="text-gray-500 text-sm">
          No read QC report yet. Reports are made when the pipeline runs on FASTQ input (not for assembled FASTA input).
        </p>
      )}

      {stages.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-2">Long reads (NanoPlot)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-700">
                  <th className="text-left font-normal py-1.5 pr-4"></th>
                  {stages.map(({ stage, title }) => (
                    <th key={stage} className="text-right font-normal py-1.5 px-3">{title}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.label} className="border-b border-gray-800">
                    <td className="py-1.5 pr-4 text-gray-400">{row.label}</td>
                    {stages.map(({ stage }) => (
                      <td key={stage} className="py-1.5 px-3 text-right text-gray-100 tabular-nums">
                        {row.get(qc!.nanoplot[stage]!)}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <td className="pt-3 pr-4"></td>
                  {stages.map(({ stage }) => (
                    <td key={stage} className="pt-3 px-3">
                      <div className="flex justify-end gap-2 flex-wrap">
                        <button onClick={() => open(`nanoplot-${stage}-html`, true)}
                          className="btn-secondary text-xs flex items-center gap-1.5">
                          <ExternalLink className="w-3.5 h-3.5" />
                          Report
                        </button>
                        <button onClick={() => open(`nanoplot-${stage}-stats`, false)}
                          className="btn-secondary text-xs flex items-center gap-1.5">
                          <Download className="w-3.5 h-3.5" />
                          NanoStats
                        </button>
                      </div>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
      {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
    </div>
  );
}
