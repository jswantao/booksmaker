// API TypeScript interfaces — mirroring models/schemas.py

// ---- Generic ----
export type ProviderChoice = "openai" | "local" | "auto";
export type TranslateTask = "paragraph_translate" | "long_text_translate";

export interface ApiSuccess<T = Record<string, unknown>> {
  success: true;
  [key: string]: unknown;
}
export interface ApiError {
  success: false;
  error: string;
  code?: string;
}
export type ApiResponse<T = Record<string, unknown>> = ApiSuccess<T> | ApiError;

// ---- Config ----
export interface ConfigRequest {
  api_key: string;
  base_url: string;
  model_name: string;
  embedding_model: string;
  embedding_provider: string;
  bge_model_id: string;
  llm_provider: string;
  local_translate_model: string;
  local_epub_model: string;
  download_source: string;
  modelscope_cache_dir: string;
}

export interface ConfigResponse {
  api_key: string;
  base_url: string;
  model_name: string;
  embedding_model: string;
  embedding_provider: string;
  bge_model_id: string;
  llm_provider: string;
  local_translate_model: string;
  local_epub_model: string;
  download_source: string;
  modelscope_cache_dir: string;
  is_configured: boolean;
}

export interface LlmStatus {
  [task: string]: {
    provider_name: string;
    model_name: string;
    status: string;
    load_status?: string;
    load_error?: string;
  };
}

export interface EmbeddingStatus {
  provider: string;
  loaded: boolean;
  error?: string;
}

export interface ModelScopeModel {
  id: string;
  name: string;
  params: string;
  params_b: number;
  family: string;
  desc: string;
  on_modelscope: boolean;
}

// ---- Translate ----
export interface TranslateRequest {
  text: string;
  source_lang?: string;
  target_lang?: string;
  use_tm?: boolean;
  use_rag?: boolean;
  kb_ids?: string[];
  group_id?: string | null;
  chapter?: string | null;
  context?: string | null;
  book_title?: string | null;
  provider?: ProviderChoice;
  task?: TranslateTask;
}

export interface TranslateResponse {
  success: boolean;
  translation?: string;
  from_tm?: boolean;
  task?: string;
  provider?: string;
  model?: string;
  memory_terms?: number;
  memory_added?: number;
  book_title?: string | null;
  error?: string;
  tm_references?: unknown[];
}

// ---- EPUB ----
export interface EpubReplaceRequest {
  translation: string;
  epub_code: string;
  title?: string;
  book_title?: string | null;
  provider?: ProviderChoice;
}

export interface EpubReplaceResponse {
  success: boolean;
  epub_code?: string;
  provider?: string;
  model?: string;
  error?: string;
  download_url?: string;
}

// ---- TM ----
export interface TmEntry {
  id: number;
  source: string;
  target: string;
  use_count: number;
  created_at: string;
  updated_at: string;
  context: string;
  match_type?: "exact" | "fuzzy";
  similarity?: number;
}

export interface TmListResponse {
  success: boolean;
  results: TmEntry[];
  total: number;
}

export interface TmSearchResponse {
  success: boolean;
  results: TmEntry[];
}

// ---- KB ----
export interface KbInfo {
  id: string;
  name: string;
  description: string;
  collection_name: string;
  embedding_model: string;
  group_id: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface KbGroup {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface KbListResponse {
  success: boolean;
  kbs: KbInfo[];
  groups: KbGroup[];
}

export interface KbCreateRequest {
  name: string;
  description?: string | null;
  embedding_model?: string | null;
  group_id?: string | null;
}

export interface KbUpdateRequest {
  name: string;
  description?: string | null;
  group_id?: string | null;
  embedding_model?: string | null;
}

export interface KbGroupRequest {
  name: string;
  description?: string | null;
}

export interface HybridSearchRequest {
  query: string;
  kb_ids?: string[] | null;
  group_id?: string | null;
  chapter?: string | null;
  top_k?: number;
  score_threshold?: number;
  semantic_weight?: number;
  keyword_weight?: number;
}

export interface HybridSearchResult {
  document: string;
  score: number;
  method: string;
  metadata: Record<string, string>;
  detail: { vector: number; keyword: number };
  kb_id: string;
  kb_name: string;
}

// ---- Pipeline ----
export interface PipelineRunRequest {
  file_path: string;
  book_title?: string;
  kb_ids?: string[];
  memory_path?: string;
  resume_from?: number;
  auto_save_interval?: number;
  task?: string;
}

export interface PipelineBuildKbRequest {
  file_path: string;
  kb_name: string;
  chunk_size?: number;
  overlap?: number;
}

export interface PipelineStatusResponse {
  success: boolean;
  running?: boolean;
  paused?: boolean;
  terms?: number;
  book?: string;
  total_chunks?: number;
  chunks_done?: number;
  is_done?: boolean;
  last_error?: string;
  completed_chapters?: number;
  total_terms?: number;
  terms_count?: number;
}

export interface PipelineResultResponse {
  success: boolean;
  output?: string;
  message?: string;
}

export interface PipelineMemoryResponse {
  success: boolean;
  terms?: Record<string, string>;
  terminology?: Record<string, string> | Array<{ en: string; zh?: string; target?: string; source?: string }>;
  summaries?: unknown[];
  progress?: Record<string, unknown>;
  project_name?: string;
  completed_chapters?: number;
  total_chunks?: number;
  chunks_done?: number;
  total_terms?: number;
  last_updated?: string;
  updated_at?: string;
}

export interface PipelineMemoryInitRequest {
  memory_path: string;
  project?: string;
  terminology?: Record<string, string> | null;
}

// ---- Terminology ----
export interface TermUpsertRequest {
  en_term: string;
  zh_term: string;
  kb_target?: string;
}

// ---- Knowledge ----
export interface KnowledgeStatusResponse {
  success: boolean;
  kb_count?: number;
  group_count?: number;
  total_documents?: number;
  history_count?: number;
  epub_count?: number;
  history?: unknown[];
  epub?: unknown[];
}

// ---- Training ----
export interface LossPoint {
  step: number;
  loss: number;
  epoch: number;
}

export interface TrainingStatusResponse {
  success: boolean;
  running: boolean;
  started_at: string | null;
  progress: number;
  step: number;
  total_steps: number;
  loss: number | null;
  current_epoch: number;
  total_epochs: number;
  config: Record<string, unknown>;
  error: string | null;
  gpu_memory_used: number | null;
  gpu_memory_reserved: number | null;
  system_ram_used: number | null;
  training_speed: number | null;
  phase: TrainingPhase;
  loss_history: LossPoint[];
}

export type TrainingPhase =
  | "idle"
  | "downloading"
  | "loading_data"
  | "loading_model"
  | "training"
  | "evaluating"
  | "saving"
  | "complete"
  | "error";

export interface TrainingDataStatus {
  success: boolean;
  tm_entries: number;
  shared_terms: number;
  train_samples: number;
  memory_books: Array<{ name: string; terms: number; chunks: number }>;
  ready: boolean;
}

export interface TrainedModel {
  name: string;
  path: string;
  base_model: string;
  description: string;
  type?: string;
}

export interface TrainingHistoryRun {
  id: string;
  started_at: string;
  finished_at: string;
  base_model: string;
  epochs: number;
  final_loss: number | null;
  total_steps: number;
  duration_seconds: number;
  status: "completed" | "failed";
  output_dir: string;
}

export interface MergeRequest {
  lora_path: string;
  base_model?: string;
  output_name: string;
  strategy?: string;
}

export interface MergeStatusResponse {
  success: boolean;
  running: boolean;
  log_lines: string[];
  error: string | null;
  done: boolean;
}

export interface TrainingEnvCheck {
  success: boolean;
  deps: Record<string, string>;
  all_ok: boolean;
  gpu_available: boolean;
  gpu_info: string;
  python: string;
  hint: string | null;
  cached_models: string[];
  cache_dir: string;
}

export interface AvailableModelsResponse {
  recommended: { id: string; label: string }[];
  cached: { id: string; path: string; source: string }[];
  merged: { id: string; path: string; name: string; base_model?: string; description?: string }[];
  lora_adapters: { id: string; path: string; name: string }[];
}
