'use client';

import { useState, useEffect } from 'react';
import { Download } from 'lucide-react';
import { authFetch } from '@/components/tools/shared';

interface SRASample {
  sample_id: string;
  sample_name: string;
  organism: string;
  collection_date: string;
  geo_loc_name: string;
  isolation_source: string;
  library_strategy: string;
  library_source: string;
  library_selection: string;
  library_layout: string;
  platform: string;
  instrument_model: string;
  filetype: string;
  filenames: string[];
  filename1: string;
  filename2: string;
}

const INSTRUMENT_OPTIONS: Record<string, string[]> = {
  ILLUMINA: ['Illumina MiSeq', 'Illumina HiSeq 2500', 'Illumina HiSeq 4000', 'Illumina NovaSeq 6000', 'NextSeq 500', 'NextSeq 2000', 'Illumina iSeq 100'],
  OXFORD_NANOPORE: ['MinION', 'GridION', 'PromethION', 'Flongle'],
  PACBIO_SMRT: ['PacBio RS II', 'Sequel', 'Sequel II', 'Sequel IIe', 'Revio'],
};

export default function SRASubmissionTool() {
  const [samples, setSamples] = useState<SRASample[]>([]);
  const [loading, setLoading] = useState(true);
  const [bioproject, setBioproject] = useState('');
  const [edited, setEdited] = useState<Record<string, Partial<SRASample>>>({});

  useEffect(() => {
    authFetch('/api/sra-submission')
      .then((r) => r.json())
      .then((d) => { setSamples(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const getVal = (s: SRASample, field: keyof SRASample): string => {
    const override = edited[s.sample_id]?.[field];
    if (override !== undefined) return String(override);
    return String(s[field] || '');
  };

  const setVal = (sampleId: string, field: keyof SRASample, value: string) => {
    setEdited((prev) => ({
      ...prev,
      [sampleId]: { ...prev[sampleId], [field]: value },
    }));
  };

  const downloadBioSampleTSV = () => {
    const headers = ['sample_name', 'organism', 'collection_date', 'geo_loc_name', 'isolation_source', 'sample_type'];
    const rows = samples.map((s) => [
      getVal(s, 'sample_name'),
      getVal(s, 'organism'),
      getVal(s, 'collection_date') || 'missing',
      getVal(s, 'geo_loc_name') || 'missing',
      getVal(s, 'isolation_source') || 'missing',
      'whole genome sequencing',
    ]);
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'biosample_attributes.tsv'; a.click();
  };

  const downloadSRAMetadataTSV = () => {
    const headers = ['bioproject_accession', 'biosample_accession', 'library_ID', 'title',
      'library_strategy', 'library_source', 'library_selection', 'library_layout',
      'platform', 'instrument_model', 'design_description', 'filetype', 'filename', 'filename2'];
    const rows = samples.map((s) => {
      const org = getVal(s, 'organism');
      const layout = getVal(s, 'library_layout');
      return [
        bioproject,
        '',  // biosample_accession -- filled after BioSample submission
        getVal(s, 'sample_name'),
        `Whole genome sequencing of ${org || 'bacterial isolate'} ${getVal(s, 'sample_name')}`,
        getVal(s, 'library_strategy'),
        getVal(s, 'library_source'),
        getVal(s, 'library_selection'),
        layout,
        getVal(s, 'platform'),
        getVal(s, 'instrument_model'),
        `${org || 'Bacterial'} genomic DNA library`,
        getVal(s, 'filetype'),
        getVal(s, 'filename1'),
        layout === 'paired' ? getVal(s, 'filename2') : '',
      ];
    });
    const tsv = [headers.join('\t'), ...rows.map((r) => r.join('\t'))].join('\n');
    const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'sra_metadata.tsv'; a.click();
  };

  if (loading) return <div className="flex items-center justify-center h-32"><div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>;

  return (
    <div className="space-y-6">
      <p className="text-gray-400 text-sm">
        Prepare BioSample and SRA metadata files for NCBI submission. Edit fields below, then download the TSV templates.
      </p>

      {samples.length === 0 ? (
        <div className="card text-center py-8 text-gray-500">No samples with FASTQ files found. Upload sequencing data first.</div>
      ) : (
        <>
          {/* BioProject */}
          <div className="card">
            <div className="flex items-center gap-4">
              <label className="text-sm text-gray-300 font-medium whitespace-nowrap">BioProject Accession:</label>
              <input type="text" value={bioproject} onChange={(e) => setBioproject(e.target.value)}
                placeholder="PRJNA000000 (leave blank if creating new)" className="input flex-1 text-sm" />
            </div>
          </div>

          {/* Download buttons */}
          <div className="flex gap-3">
            <button onClick={downloadBioSampleTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download BioSample TSV
            </button>
            <button onClick={downloadSRAMetadataTSV} className="btn-primary flex items-center gap-2 text-sm">
              <Download className="w-4 h-4" />
              Download SRA Metadata TSV
            </button>
          </div>

          {/* Editable table */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">Sample Metadata ({samples.length} samples)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Sample</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Organism</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Collection Date</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Location</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Isolation Source</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Layout</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Platform</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Instrument</th>
                    <th className="text-left py-2 px-2 text-gray-400 font-medium whitespace-nowrap">Files</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {samples.map((s) => {
                    const plat = getVal(s, 'platform');
                    return (
                      <tr key={s.sample_id} className="hover:bg-gray-800/20">
                        <td className="py-2 px-2 font-medium text-gray-200 whitespace-nowrap">{s.sample_name}</td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'organism')} onChange={(e) => setVal(s.sample_id, 'organism', e.target.value)}
                            className="input text-xs w-40 py-1 px-2" placeholder="Organism" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'collection_date')} onChange={(e) => setVal(s.sample_id, 'collection_date', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="YYYY-MM-DD" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'geo_loc_name')} onChange={(e) => setVal(s.sample_id, 'geo_loc_name', e.target.value)}
                            className="input text-xs w-32 py-1 px-2" placeholder="Country: Region" />
                        </td>
                        <td className="py-2 px-2">
                          <input type="text" value={getVal(s, 'isolation_source')} onChange={(e) => setVal(s.sample_id, 'isolation_source', e.target.value)}
                            className="input text-xs w-28 py-1 px-2" placeholder="e.g. blood" />
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'library_layout')} onChange={(e) => setVal(s.sample_id, 'library_layout', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="paired">paired</option>
                            <option value="single">single</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={plat} onChange={(e) => setVal(s.sample_id, 'platform', e.target.value)}
                            className="input text-xs py-1 px-2">
                            <option value="ILLUMINA">ILLUMINA</option>
                            <option value="OXFORD_NANOPORE">OXFORD_NANOPORE</option>
                            <option value="PACBIO_SMRT">PACBIO_SMRT</option>
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select value={getVal(s, 'instrument_model')} onChange={(e) => setVal(s.sample_id, 'instrument_model', e.target.value)}
                            className="input text-xs py-1 px-2">
                            {(INSTRUMENT_OPTIONS[plat] || INSTRUMENT_OPTIONS.ILLUMINA).map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-2 text-gray-400 whitespace-nowrap">
                          {s.filenames.slice(0, 2).map((f, i) => (
                            <div key={i} className="truncate max-w-[150px]" title={f}>{f}</div>
                          ))}
                          {s.filenames.length > 2 && <div className="text-gray-600">+{s.filenames.length - 2} more</div>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Instructions */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-100 mb-3">SRA Submission Steps</h2>
            <ol className="list-decimal list-inside space-y-2 text-sm text-gray-400">
              <li>Create a <strong className="text-gray-200">BioProject</strong> at <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">NCBI Submission Portal</a> (if you don&apos;t have one)</li>
              <li>Download and submit the <strong className="text-gray-200">BioSample TSV</strong> — this registers your samples and gives you BioSample accessions</li>
              <li>Enter your BioProject accession above, then download the <strong className="text-gray-200">SRA Metadata TSV</strong></li>
              <li>Fill in the BioSample accessions in the SRA metadata file</li>
              <li>Upload your FASTQ files and the SRA metadata to the <a href="https://submit.ncbi.nlm.nih.gov/" target="_blank" className="text-blue-400 hover:text-blue-300">SRA submission wizard</a></li>
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
