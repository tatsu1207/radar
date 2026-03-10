'use client';

import Link from 'next/link';
import { CheckCircle, XCircle, Clock, Loader2, Ban, Minus, Trash2 } from 'lucide-react';
import type { Sample, AnalysisJob } from '@/lib/api';

const STEP_COLUMNS = [
  { tool: 'bbduk', label: 'Trim' },
  { tool: 'unicycler', label: 'Assembly' },
  { tool: 'amrfinderplus', label: 'ARG' },
  { tool: 'mob_recon', label: 'Plasmid' },
  { tool: 'mefinder', label: 'Mobile' },
  { tool: 'phenotype_prediction', label: 'Pheno' },
  { tool: 'risk_scoring', label: 'Risk' },
];

function StepDot({ status }: { status?: string }) {
  switch (status) {
    case 'complete':
      return <CheckCircle className="w-4 h-4 text-green-400" />;
    case 'running':
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
    case 'failed':
      return <XCircle className="w-4 h-4 text-red-400" />;
    case 'cancelled':
      return <Ban className="w-4 h-4 text-yellow-400" />;
    case 'pending':
      return <Clock className="w-4 h-4 text-gray-400 animate-pulse" />;
    default:
      return <Minus className="w-4 h-4 text-gray-700" />;
  }
}

interface SampleTableProps {
  samples: Sample[];
  jobs: AnalysisJob[];
  onDeleteSample?: (sampleId: string) => void;
}

export default function SampleTable({ samples, jobs, onDeleteSample }: SampleTableProps) {
  if (samples.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>No samples yet. Add files via File Manager to get started.</p>
      </div>
    );
  }

  function getLatestStatus(sampleId: string, tool: string): string | undefined {
    const matching = jobs.filter((j) => j.sample_id === sampleId && j.tool === tool);
    if (matching.length === 0) return undefined;
    const latest = matching.sort(
      (a, b) => new Date(b.started_at || 0).getTime() - new Date(a.started_at || 0).getTime()
    )[0];
    return latest.status;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="table-header text-left">Sample</th>
            {STEP_COLUMNS.map((col) => (
              <th key={col.tool} className="table-header text-center" title={col.tool}>
                {col.label}
              </th>
            ))}
            <th className="table-header text-center w-10"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {samples.map((sample) => (
            <tr key={sample.id} className="hover:bg-gray-800/50 transition-colors">
              <td className="table-cell">
                <Link
                  href={`/samples/${sample.id}`}
                  className="text-blue-400 hover:text-blue-300 font-medium"
                >
                  {sample.name}
                </Link>
              </td>
              {STEP_COLUMNS.map((col) => (
                <td key={col.tool} className="table-cell text-center">
                  <div className="flex justify-center">
                    <StepDot status={getLatestStatus(sample.id, col.tool)} />
                  </div>
                </td>
              ))}
              <td className="table-cell text-center">
                {onDeleteSample && (
                  <button
                    onClick={() => onDeleteSample(sample.id)}
                    className="p-1 rounded hover:bg-red-900/50 text-gray-600 hover:text-red-400 transition-colors"
                    title="Delete sample"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
