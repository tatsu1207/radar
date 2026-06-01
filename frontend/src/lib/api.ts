// API client for RADAR backend

export interface Project {
  id: string;
  name: string;
  description: string;
  sample_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Sample {
  id: string;
  project_id: string;
  name: string;
  sample_type: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface AnalysisJob {
  id: string;
  sample_id: string;
  tool: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | 'cancelled';
  started_at: string | null;
  finished_at: string | null;
  log: string | null;
  celery_task_id: string | null;
  threads: number | null;
}

export interface ARGResult {
  id: string;
  sample_id: string;
  gene: string;
  drug_class: string;
  mechanism: string;
  identity: number;
  coverage: number;
  contig: string;
  start: number;
  end: number;
  database: string;
  on_plasmid: boolean;
}

export interface PlasmidResult {
  id: string;
  sample_id: string;
  plasmid_id: string;
  replicon: string;
  mob_type: string;
  predicted_transferability: boolean;
}

export interface MobilityResult {
  id: string;
  sample_id: string;
  element_type: string;
  element_name: string;
  contig: string;
  start: number;
  end: number;
  nearby_args: string[];
}

export interface VirulenceResult {
  id: string;
  sample_id: string;
  gene: string;
  category: string;
  identity: number;
  coverage: number;
  contig: string;
  database: string;
}

export interface RiskScore {
  sample_id: string;
  sample_name: string;
  arg_score: number;
  vf_score: number;
  mobility_score: number;
  composite_score: number;
  risk_category: 'low' | 'medium' | 'high' | 'critical';
}

export interface HeatmapData {
  samples: string[];
  drug_classes: string[];
  matrix: number[][];
}

export interface Metadata {
  id: string;
  sample_id: string;
  source: string;
  collection_date: string;
  location: string;
  species: string;
  custom_fields: Record<string, string>;
}

export interface ASTResult {
  id: string;
  sample_id: string;
  antibiotic: string;
  mic: string;
  interpretation: 'S' | 'I' | 'R';
}

export interface PhenotypeComparison {
  antibiotic: string;
  predicted: 'S' | 'I' | 'R';
  observed: 'S' | 'I' | 'R' | null;
  concordance: boolean | null;
  confidence: number;
}

export class APIError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'APIError';
  }
}

async function fetchAPI<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => 'Unknown error');
    throw new APIError(errorBody, res.status);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

// Projects
export async function listProjects(): Promise<Project[]> {
  const data = await fetchAPI<{ items: Project[]; total: number }>('/api/projects');
  return data.items;
}

export async function getProject(id: string): Promise<Project> {
  return fetchAPI<Project>(`/api/projects/${id}`);
}

export async function createProject(data: { name: string; description: string }): Promise<Project> {
  return fetchAPI<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateProject(id: string, data: { name?: string; description?: string }): Promise<Project> {
  return fetchAPI<Project>(`/api/projects/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteProject(id: string): Promise<void> {
  return fetchAPI<void>(`/api/projects/${id}`, { method: 'DELETE' });
}

// Samples
export async function listSamples(projectId: string): Promise<Sample[]> {
  const data = await fetchAPI<{ items: Sample[]; total: number }>(`/api/projects/${projectId}/samples`);
  return data.items;
}

export async function getSample(id: string): Promise<Sample> {
  return fetchAPI<Sample>(`/api/samples/${id}`);
}

export async function createSample(projectId: string, data: { name: string; input_type: string }): Promise<Sample> {
  return fetchAPI<Sample>(`/api/projects/${projectId}/samples`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteSample(id: string): Promise<void> {
  return fetchAPI<void>(`/api/samples/${id}`, { method: 'DELETE' });
}

// Upload
export async function uploadFiles(sampleId: string, files: File[]): Promise<{ uploaded: string[] }> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));

  const res = await fetch(`/api/samples/${sampleId}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.text().catch(() => 'Upload failed');
    throw new APIError(errorBody, res.status);
  }

  return res.json();
}

// Analysis
export async function startAnalysis(sampleId: string, threads: number = 4): Promise<AnalysisJob> {
  return fetchAPI<AnalysisJob>(`/api/samples/${sampleId}/analyze`, {
    method: 'POST',
    body: JSON.stringify({ threads }),
  });
}

export async function runStep(sampleId: string, tool: string, threads: number = 4): Promise<AnalysisJob> {
  return fetchAPI<AnalysisJob>(`/api/samples/${sampleId}/run-step`, {
    method: 'POST',
    body: JSON.stringify({ tool, threads }),
  });
}

export async function cancelJob(jobId: string): Promise<AnalysisJob> {
  return fetchAPI<AnalysisJob>(`/api/jobs/${jobId}/cancel`, {
    method: 'POST',
  });
}

export async function getProjectJobs(projectId: string): Promise<AnalysisJob[]> {
  return fetchAPI<AnalysisJob[]>(`/api/projects/${projectId}/jobs`);
}

export async function getJobs(sampleId: string): Promise<AnalysisJob[]> {
  return fetchAPI<AnalysisJob[]>(`/api/samples/${sampleId}/jobs`);
}

export async function getJob(jobId: string): Promise<AnalysisJob> {
  return fetchAPI<AnalysisJob>(`/api/jobs/${jobId}`);
}

// Results
export async function getARGs(sampleId: string): Promise<ARGResult[]> {
  return fetchAPI<ARGResult[]>(`/api/samples/${sampleId}/args`);
}

export async function getPlasmids(sampleId: string): Promise<PlasmidResult[]> {
  return fetchAPI<PlasmidResult[]>(`/api/samples/${sampleId}/plasmids`);
}

export interface ISElementData {
  is_elements: {
    contig: string; start: number; end: number;
    is_name: string; is_family: string;
    molecule_type: string; plasmid_id: string;
    nearby_args: { gene: string; drug_class: string; start: number; end: number; distance: number; database: string }[];
  }[];
  arg_associations: {
    gene: string; drug_class: string; contig: string;
    start: number; end: number; on_plasmid: boolean; database: string;
    nearby_is: { is_name: string; is_family: string; start: number; end: number; distance: number }[];
  }[];
  flanking_distance: number;
  total_is: number;
  args_with_is: number;
}

export async function getISElements(sampleId: string, flanking: number = 5000): Promise<ISElementData> {
  return fetchAPI<ISElementData>(`/api/samples/${sampleId}/is-elements?flanking=${flanking}`);
}

export interface LinearMapContig {
  contig: string;
  length: number;
  molecule_type: string;
  plasmid_id: string;
  features: { type: string; name: string; label: string; family: string; start: number; end: number; strand?: number }[];
}

export async function getLinearMap(sampleId: string): Promise<LinearMapContig[]> {
  return fetchAPI<LinearMapContig[]>(`/api/samples/${sampleId}/linear-map`);
}

export interface PlasmidMapFeature {
  type: 'arg' | 'mobile_element' | 'prophage' | 'relaxase' | 'orit' | 't4ss' | 'replicon';
  name: string;
  label: string;
  family: string;
  start: number;
  end: number;
}

export interface PlasmidMapData {
  plasmid_id: string;
  contig: string;
  size: number;
  replicon: string;
  mob_type: string;
  mpf_type: string;
  orit_type: string;
  predicted_mobility: string;
  features: PlasmidMapFeature[];
}

export async function getPlasmidMap(sampleId: string): Promise<PlasmidMapData[]> {
  return fetchAPI<PlasmidMapData[]>(`/api/samples/${sampleId}/plasmid-map`);
}

export async function getMobility(sampleId: string): Promise<MobilityResult[]> {
  return fetchAPI<MobilityResult[]>(`/api/samples/${sampleId}/mobility`);
}

export async function getRisk(sampleId: string): Promise<RiskScore> {
  return fetchAPI<RiskScore>(`/api/samples/${sampleId}/risk`);
}

export async function getVirulence(sampleId: string): Promise<VirulenceResult[]> {
  return fetchAPI<VirulenceResult[]>(`/api/samples/${sampleId}/virulence`);
}

export async function getHeatmap(projectId: string): Promise<HeatmapData> {
  return fetchAPI<HeatmapData>(`/api/projects/${projectId}/heatmap`);
}

export async function exportCSV(sampleId: string): Promise<Blob> {
  const res = await fetch(`/api/samples/${sampleId}/export`);
  if (!res.ok) {
    throw new APIError('Export failed', res.status);
  }
  return res.blob();
}

// Metadata
export async function getMetadata(sampleId: string): Promise<Metadata> {
  return fetchAPI<Metadata>(`/api/samples/${sampleId}/metadata`);
}

export async function updateMetadata(
  sampleId: string,
  data: Partial<Omit<Metadata, 'id' | 'sample_id'>>
): Promise<Metadata> {
  return fetchAPI<Metadata>(`/api/samples/${sampleId}/metadata`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function importMetadataCSV(projectId: string, file: File): Promise<{ imported: number }> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`/api/projects/${projectId}/metadata/import`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    throw new APIError('Import failed', res.status);
  }

  return res.json();
}

export async function getAST(sampleId: string): Promise<ASTResult[]> {
  return fetchAPI<ASTResult[]>(`/api/samples/${sampleId}/ast`);
}

export async function addAST(
  sampleId: string,
  data: { antibiotic: string; mic: string; interpretation: string }
): Promise<ASTResult> {
  return fetchAPI<ASTResult>(`/api/samples/${sampleId}/ast`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// Phenotype (legacy)
export async function getPrediction(sampleId: string): Promise<PhenotypeComparison[]> {
  return fetchAPI<PhenotypeComparison[]>(`/api/phenotype/${sampleId}/predict`);
}

export async function getComparison(sampleId: string): Promise<PhenotypeComparison[]> {
  return fetchAPI<PhenotypeComparison[]>(`/api/phenotype/${sampleId}/compare`);
}

// Risk (legacy - used by risk page)
export async function calculateRisk(
  projectId: string,
  weights?: { arg_weight: number; vf_weight: number; mobility_weight: number }
): Promise<RiskScore[]> {
  return fetchAPI<RiskScore[]>(`/api/risk/${projectId}/calculate`, {
    method: 'POST',
    body: JSON.stringify(weights || {}),
  });
}

// ---------------------------------------------------------------------------
// New per-sample result types and endpoints
// ---------------------------------------------------------------------------

export interface ResFinderResult {
  id: string;
  sample_id: string;
  gene: string;
  drug_class: string;
  phenotype: string;
  identity: number;
  coverage: number;
  contig: string;
  accession: string;
}

export interface RGIResult {
  id: string;
  sample_id: string;
  gene: string;
  drug_class: string;
  resistance_mechanism: string;
  amr_gene_family: string;
  model_type: string;
  identity: number;
  coverage: number;
  contig: string;
  cut_off: string;
}

export interface VFDBResult {
  id: string;
  sample_id: string;
  gene: string;
  product: string;
  vf_class: string;
  identity: number;
  coverage: number;
  contig: string;
  accession: string;
}

export interface SerotypeResult {
  id: string;
  sample_id: string;
  tool: string;
  serotype: string;
  o_antigen: string;
  h_antigen: string;
  k_locus: string;
  serovar: string;
  details: Record<string, string>;
}

export interface CgMLSTResult {
  id: string;
  sample_id: string;
  schema_name: string;
  allelic_profile: Record<string, string>;
  loci_found: number;
  loci_total: number;
}

export interface BaktaAnnotation {
  id: string;
  sample_id: string;
  gff_path: string;
  gbk_path: string;
  faa_path: string;
  cds_count: number;
  rrna_count: number;
  trna_count: number;
  ncrna_count: number;
  crispr_count: number;
  hypothetical_count: number;
}

export interface IntegronResult {
  id: string;
  sample_id: string;
  integron_id: string;
  integron_type: string;
  contig: string;
  start: number;
  end: number;
  cassettes: string[];
}

export interface PointMutationResult {
  id: string;
  sample_id: string;
  gene: string;
  mutation: string;
  drug_class: string;
  resistance: string;
  nucleotide_change: string;
}

export interface ARGConcordance {
  gene: string;
  drug_class: string;
  amrfinderplus: { identity: number; coverage: number } | null;
  resfinder: { identity: number; coverage: number } | null;
  rgi: { identity: number; coverage: number; cut_off: string } | null;
}

export async function getResFinderResults(sampleId: string): Promise<ResFinderResult[]> {
  return fetchAPI<ResFinderResult[]>(`/api/samples/${sampleId}/resfinder`);
}

export async function getRGIResults(sampleId: string): Promise<RGIResult[]> {
  return fetchAPI<RGIResult[]>(`/api/samples/${sampleId}/rgi`);
}

export async function getVFDBResults(sampleId: string): Promise<VFDBResult[]> {
  return fetchAPI<VFDBResult[]>(`/api/samples/${sampleId}/vfdb`);
}

export async function getSerotype(sampleId: string): Promise<SerotypeResult> {
  return fetchAPI<SerotypeResult>(`/api/samples/${sampleId}/serotype`);
}

export async function getCgMLST(sampleId: string): Promise<CgMLSTResult> {
  return fetchAPI<CgMLSTResult>(`/api/samples/${sampleId}/cgmlst`);
}

export async function getBaktaAnnotation(sampleId: string): Promise<BaktaAnnotation> {
  return fetchAPI<BaktaAnnotation>(`/api/samples/${sampleId}/bakta`);
}

export async function getIntegrons(sampleId: string): Promise<IntegronResult[]> {
  return fetchAPI<IntegronResult[]>(`/api/samples/${sampleId}/integrons`);
}

export async function getPointMutations(sampleId: string): Promise<PointMutationResult[]> {
  return fetchAPI<PointMutationResult[]>(`/api/samples/${sampleId}/point-mutations`);
}

export interface CRISPRResultData {
  id: string;
  sample_id: string;
  crispr_id: string;
  contig: string;
  start: number;
  end: number;
  cas_type: string | null;
  cas_genes: string[] | null;
  num_spacers: number;
  repeat_length: number | null;
  spacer_length: number | null;
  evidence_level: number | null;
}

export interface DefenseSystemResult {
  id: string;
  sample_id: string;
  system_type: string;
  subtype: string | null;
  genes: string[] | null;
  contig: string;
  start: number;
  end: number;
  protein_count: number;
}

export interface ICEResultData {
  id: string;
  sample_id: string;
  ice_id: string;
  ice_type: string;
  contig: string;
  start: number;
  end: number;
  length: number;
  integrase: string | null;
  arg_genes: string[] | null;
  nearest_trna: string | null;
}

export async function getCRISPRResults(sampleId: string): Promise<CRISPRResultData[]> {
  return fetchAPI<CRISPRResultData[]>(`/api/samples/${sampleId}/crispr`);
}

export async function getDefenseSystems(sampleId: string): Promise<DefenseSystemResult[]> {
  return fetchAPI<DefenseSystemResult[]>(`/api/samples/${sampleId}/defense-systems`);
}

export async function getICEResults(sampleId: string): Promise<ICEResultData[]> {
  return fetchAPI<ICEResultData[]>(`/api/samples/${sampleId}/ice`);
}

export async function getARGConcordance(sampleId: string): Promise<ARGConcordance[]> {
  return fetchAPI<ARGConcordance[]>(`/api/samples/${sampleId}/args/concordance`);
}

export interface SampleSummary {
  sample_id: string;
  sample_name: string;
  status: string;
  species: string | null;
  species_identity: number | null;
  mlst_scheme: string | null;
  mlst_st: string | null;
  serotype: string | null;
  serotype_tool: string | null;
  arg_count: number;
  arg_genes: string[];
  drug_classes: string[];
  vf_count: number;
  vf_genes: string[];
  drug_resistance: string[];
  pathotype: {
    pathotypes: string[];
    predicted_diseases: string[];
    key_evidence: string[];
    vf_marker_summary: Record<string, boolean>;
  } | null;
  plasmids: { plasmid_id: string; replicon: string; mobility: string }[];
  bacmet: { gene: string; compound: string; identity: number }[];
  quast: { total_length?: number; num_contigs?: number; n50?: number; gc_percent?: number; largest_contig?: number } | null;
  busco: { complete?: number; single_copy?: number; duplicated?: number; fragmented?: number; missing?: number } | null;
}

export async function getSampleSummary(sampleId: string): Promise<SampleSummary> {
  return fetchAPI<SampleSummary>(`/api/samples/${sampleId}/summary`);
}

// File Manager types
export interface FileSlot {
  id: string;
  filename: string;
  size: number;
}

export interface FileManagerSample {
  sample_id: string;
  name: string;
  status: string;
  input_type: string;
  illumina_r1: FileSlot | null;
  illumina_r2: FileSlot | null;
  long_read: FileSlot | null;
  long_read_platform: string | null;
  assembly: FileSlot | null;
  source: string;
  has_metadata: boolean;
  project_id: string | null;
  project_name: string | null;
  pipeline_status: string | null;
  pipeline_job_id: string | null;
  pipeline_progress: number;
  busco_complete: number | null;
}

export interface FileManagerResponse {
  samples: FileManagerSample[];
  total: number;
}

export interface SRADownload {
  id: string;
  srr_accession: string;
  sample_id: string | null;
  status: 'queued' | 'downloading' | 'complete' | 'failed';
  progress: number;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface BVBRCFetch {
  id: string;
  genome_id: string;
  sample_id: string | null;
  status: 'queued' | 'downloading' | 'complete' | 'failed';
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface MetadataTSVResult {
  updated: number;
  created: number;
  errors: string[];
}

// File Manager API functions
export async function getFileManager(projectId: string): Promise<FileManagerResponse> {
  return fetchAPI<FileManagerResponse>(`/api/projects/${projectId}/file-manager`);
}

export async function getAllFileManager(): Promise<FileManagerResponse> {
  return fetchAPI<FileManagerResponse>('/api/file-manager/all');
}

export function uploadFilesToProject(
  projectId: string,
  files: File[],
  onProgress?: (percent: number) => void,
): Promise<FileManagerResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const url = `/api/projects/${projectId}/file-manager/upload`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new APIError('Invalid response', xhr.status));
        }
      } else {
        reject(new APIError(xhr.responseText || 'Upload failed', xhr.status));
      }
    };

    xhr.onerror = () => reject(new APIError('Network error during upload', 0));
    xhr.send(formData);
  });
}

export interface FileBrowserEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
}

export interface FileBrowserResponse {
  current: string;
  parent: string | null;
  entries: FileBrowserEntry[];
}

export async function browseServerFiles(path?: string): Promise<FileBrowserResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : '';
  return fetchAPI<FileBrowserResponse>(`/api/file-browser${params}`);
}

export async function registerServerPaths(projectId: string, paths: string[]): Promise<FileManagerResponse> {
  return fetchAPI<FileManagerResponse>(`/api/projects/${projectId}/file-manager/server-paths`, {
    method: 'POST',
    body: JSON.stringify({ paths }),
  });
}

export async function submitSRA(projectId: string, accessions: string[]): Promise<SRADownload[]> {
  return fetchAPI<SRADownload[]>(`/api/projects/${projectId}/file-manager/sra`, {
    method: 'POST',
    body: JSON.stringify({ accessions }),
  });
}

export async function getSRADownloads(projectId: string): Promise<SRADownload[]> {
  return fetchAPI<SRADownload[]>(`/api/projects/${projectId}/file-manager/sra`);
}

export async function submitBVBRC(projectId: string, genomeIds: string[]): Promise<BVBRCFetch[]> {
  return fetchAPI<BVBRCFetch[]>(`/api/projects/${projectId}/file-manager/bvbrc`, {
    method: 'POST',
    body: JSON.stringify({ genome_ids: genomeIds }),
  });
}

export async function getBVBRCFetches(projectId: string): Promise<BVBRCFetch[]> {
  return fetchAPI<BVBRCFetch[]>(`/api/projects/${projectId}/file-manager/bvbrc`);
}

export async function uploadMetadataTSV(projectId: string, file: File): Promise<MetadataTSVResult> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/file-manager/metadata`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new APIError(await res.text().catch(() => 'Upload failed'), res.status);
  return res.json();
}

export function globalUploadFiles(
  files: File[],
  onProgress?: (percent: number) => void,
): Promise<FileManagerResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const url = `/api/file-manager/upload`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new APIError('Invalid response', xhr.status));
        }
      } else {
        reject(new APIError(xhr.responseText || 'Upload failed', xhr.status));
      }
    };

    xhr.onerror = () => reject(new APIError('Network error during upload', 0));
    xhr.send(formData);
  });
}

export async function globalRegisterServerPaths(paths: string[]): Promise<FileManagerResponse> {
  return fetchAPI<FileManagerResponse>('/api/file-manager/server-paths', {
    method: 'POST',
    body: JSON.stringify({ paths }),
  });
}

export async function globalSubmitSRA(accessions: string[]): Promise<SRADownload[]> {
  return fetchAPI<SRADownload[]>('/api/file-manager/sra', {
    method: 'POST',
    body: JSON.stringify({ accessions }),
  });
}

export async function globalGetSRADownloads(): Promise<SRADownload[]> {
  return fetchAPI<SRADownload[]>('/api/file-manager/sra');
}

export async function cancelSRADownload(downloadId: string): Promise<void> {
  return fetchAPI<void>(`/api/file-manager/sra/${downloadId}`, { method: 'DELETE' });
}

export async function removeSRADownload(downloadId: string): Promise<void> {
  return fetchAPI<void>(`/api/file-manager/sra/${downloadId}/remove`, { method: 'DELETE' });
}

export async function retrySRADownload(downloadId: string): Promise<void> {
  return fetchAPI<void>(`/api/file-manager/sra/${downloadId}/retry`, { method: 'POST' });
}

// Pipeline
export interface PipelineStatus {
  sample_id: string;
  sample_name: string;
  status: 'not_started' | 'running' | 'complete' | 'failed';
  job_id: string | null;
  log: string | null;
  has_qc: boolean;
}

export async function getPipelineStatus(): Promise<PipelineStatus[]> {
  return fetchAPI<PipelineStatus[]>('/api/pipeline/status');
}

export async function startPipeline(sampleId: string, threads: number = 12): Promise<{ job_id: string; status: string }> {
  return fetchAPI<{ job_id: string; status: string }>(`/api/pipeline/start/${sampleId}`, {
    method: 'POST',
    body: JSON.stringify({ threads }),
  });
}

export async function deleteFileManagerFile(projectId: string, fileId: string): Promise<void> {
  return fetchAPI<void>(`/api/projects/${projectId}/file-manager/files/${fileId}`, { method: 'DELETE' });
}

export async function deleteFileManagerSample(projectId: string, sampleId: string): Promise<void> {
  return fetchAPI<void>(`/api/projects/${projectId}/file-manager/samples/${sampleId}`, { method: 'DELETE' });
}

// Global Metadata
export interface MetadataRow {
  sample_id: string;
  sample_name: string;
  source: string | null;
  species: string | null;
  collection_date: string | null;
  location: string | null;
  [key: string]: string | null;
}

export interface AllMetadataResponse {
  rows: MetadataRow[];
  custom_columns: string[];
}

export async function getAllMetadata(): Promise<AllMetadataResponse> {
  return fetchAPI<AllMetadataResponse>('/api/metadata/all');
}

export async function uploadMetadataGlobal(file: File): Promise<{ created: number; updated: number; errors: string[] }> {
  const formData = new FormData();
  formData.append('file', file);
  // We need a project_id for the existing endpoint; use a global upload instead
  const res = await fetch('/api/metadata/upload', {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new APIError(await res.text().catch(() => 'Upload failed'), res.status);
  return res.json();
}
