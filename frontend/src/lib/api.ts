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
  identity_percent: number;
  coverage_percent: number;
  contig: string;
  database: string;
  on_plasmid: boolean;
}

export interface PlasmidResult {
  id: string;
  sample_id: string;
  plasmid_id: string;
  replicon_type: string;
  mobility: string;
  size_bp: number;
  contig: string;
  arg_count: number;
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
  virulence_factor: string;
  identity_percent: number;
  coverage_percent: number;
  contig: string;
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
  return fetchAPI<ARGResult[]>(`/api/results/${sampleId}/args`);
}

export async function getPlasmids(sampleId: string): Promise<PlasmidResult[]> {
  return fetchAPI<PlasmidResult[]>(`/api/results/${sampleId}/plasmids`);
}

export async function getMobility(sampleId: string): Promise<MobilityResult[]> {
  return fetchAPI<MobilityResult[]>(`/api/results/${sampleId}/mobility`);
}

export async function getRisk(sampleId: string): Promise<RiskScore> {
  return fetchAPI<RiskScore>(`/api/results/${sampleId}/risk`);
}

export async function getVirulence(sampleId: string): Promise<VirulenceResult[]> {
  return fetchAPI<VirulenceResult[]>(`/api/results/${sampleId}/virulence`);
}

export async function getHeatmap(projectId: string): Promise<HeatmapData> {
  return fetchAPI<HeatmapData>(`/api/results/heatmap/${projectId}`);
}

export async function exportCSV(projectId: string): Promise<Blob> {
  const res = await fetch(`/api/results/export/${projectId}?format=csv`);
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

// Phenotype
export async function getPrediction(sampleId: string): Promise<PhenotypeComparison[]> {
  return fetchAPI<PhenotypeComparison[]>(`/api/phenotype/${sampleId}/predict`);
}

export async function getComparison(sampleId: string): Promise<PhenotypeComparison[]> {
  return fetchAPI<PhenotypeComparison[]>(`/api/phenotype/${sampleId}/compare`);
}

// Risk
export async function calculateRisk(
  projectId: string,
  weights?: { arg_weight: number; vf_weight: number; mobility_weight: number }
): Promise<RiskScore[]> {
  return fetchAPI<RiskScore[]>(`/api/risk/${projectId}/calculate`, {
    method: 'POST',
    body: JSON.stringify(weights || {}),
  });
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
  illumina_r1: FileSlot | null;
  illumina_r2: FileSlot | null;
  long_read: FileSlot | null;
  long_read_platform: string | null;
  source: string;
  has_metadata: boolean;
  project_id: string | null;
  project_name: string | null;
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

export async function uploadFilesToProject(projectId: string, files: File[]): Promise<FileManagerResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const res = await fetch(`/api/projects/${projectId}/file-manager/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new APIError(await res.text().catch(() => 'Upload failed'), res.status);
  return res.json();
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

export async function deleteFileManagerFile(projectId: string, fileId: string): Promise<void> {
  return fetchAPI<void>(`/api/projects/${projectId}/file-manager/files/${fileId}`, { method: 'DELETE' });
}

export async function deleteFileManagerSample(projectId: string, sampleId: string): Promise<void> {
  return fetchAPI<void>(`/api/projects/${projectId}/file-manager/samples/${sampleId}`, { method: 'DELETE' });
}
