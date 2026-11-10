'use client';

import { useState } from 'react';
import { Download, ExternalLink, FileArchive } from 'lucide-react';
import { openSampleFile, formatBytes } from '@/lib/api';
import type { SampleFiles } from '@/lib/api';

export default function SampleDownloads({ sampleId, files }: { sampleId: string; files: SampleFiles | null }) {
  const [error, setError] = useState<string | null>(null);
  const open = (key: string, view: boolean) => {
    setError(null);
    openSampleFile(sampleId, key, view).catch((e) => setError(`Could not open file: ${e.message ?? e}`));
  };

  if (!files) return <div className="card"><p className="text-gray-500 text-sm">Loading…</p></div>;
  if (files.groups.length === 0) {
    return <div className="card"><p className="text-gray-500 text-sm">No files available for this sample yet.</p></div>;
  }

  const bundle = files.groups.find((g) => g.category === 'bundle')?.items[0];

  return (
    <div className="space-y-6">
      {bundle && (
        <div className="card flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Download all results</h2>
            <p className="text-sm text-gray-400">
              One ZIP with the read QC reports, assembly, QUAST, BUSCO and annotation results. Reads are not included (size); download them below.
            </p>
          </div>
          <button onClick={() => open(bundle.key, false)} className="btn-primary text-sm flex items-center gap-2">
            <FileArchive className="w-4 h-4" />
            {bundle.filename}
          </button>
        </div>
      )}

      {files.groups.filter((g) => g.category !== 'bundle').map((group) => (
        <div key={group.category} className="card">
          <h2 className="text-lg font-semibold text-gray-100 mb-3">{group.title}</h2>
          <ul className="divide-y divide-gray-800">
            {group.items.map((item) => (
              <li key={item.key} className="py-2 flex items-center justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <p className="text-sm text-gray-100">{item.label}</p>
                  <p className="text-xs text-gray-500 truncate">
                    {item.filename}{item.size != null && ` · ${formatBytes(item.size)}`}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  {item.viewable && (
                    <button onClick={() => open(item.key, true)} className="btn-secondary text-xs flex items-center gap-1.5">
                      <ExternalLink className="w-3.5 h-3.5" />
                      View
                    </button>
                  )}
                  <button onClick={() => open(item.key, false)} className="btn-secondary text-xs flex items-center gap-1.5">
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {error && <p className="text-red-400 text-sm">{error}</p>}
    </div>
  );
}
