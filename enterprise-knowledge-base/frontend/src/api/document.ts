import { getToken } from "@/stores/auth";

const BASE = "/api/admin";

function h() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface Document {
  id: number;
  category_id: number;
  title: string;
  file_type: string;
  file_size: number;
  word_count: number;
  scope: string;
  status: string;
  chunk_count: number;
  chunk_strategy: string;
  review_status: string;
  review_comment: string | null;
  department: string | null;
  clean_status: string;
}

export interface DocumentDetail extends Document {
  plain_text: string | null;
  raw_text: string | null;
  clean_report: string | null;
}

export interface CleanReport {
  original_chars: number;
  cleaned_chars: number;
  removed_page_markers: number;
  removed_placeholders: number;
  merged_fragments: number;
  collapsed_blank_lines: number;
  llm_enhanced: boolean;
}

export interface CleanResponse {
  id: number;
  clean_status: string;
  word_count: number;
  chunk_count: number;
  report: CleanReport;
}

export interface Chunk {
  id: number;
  doc_id: number;
  chunk_index: number;
  content: string;
  vector_id: string | null;
  bm25_id: string | null;
  last_sync_at: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DocumentListParams {
  page?: number;
  page_size?: number;
  category_id?: number;
  scope?: string;
  status?: string;
}

export async function fetchDocuments(params?: DocumentListParams): Promise<PaginatedResponse<Document>> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
  }
  const url = `${BASE}/documents${qs.toString() ? "?" + qs.toString() : ""}`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`加载文档列表失败 (HTTP ${resp.status}) ${err}`);
  }
  return resp.json();
}

export async function fetchDocument(id: number): Promise<DocumentDetail> {
  const resp = await fetch(`${BASE}/documents/${id}`, { headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function reviewDocument(id: number, action: "approve" | "reject", comment?: string): Promise<Document> {
  const resp = await fetch(`${BASE}/documents/${id}/review`, {
    method: "POST", headers: h(), body: JSON.stringify({ action, comment: comment || null }),
  });
  return resp.json();
}

export async function deleteDocument(id: number): Promise<void> {
  await fetch(`${BASE}/documents/${id}`, { method: "DELETE", headers: h() });
}

export async function batchDeleteDocuments(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/documents/bulk-delete`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export interface CreateDocumentPayload {
  category_id: number;
  title: string;
  scope?: string;
  chunk_strategy?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  department?: string;
}

export async function createDocument(payload: CreateDocumentPayload): Promise<Document> {
  const resp = await fetch(`${BASE}/documents`, {
    method: "POST", headers: h(), body: JSON.stringify(payload),
  });
  return resp.json();
}

export async function uploadContent(docId: number, content: string, fileType: string = "md"): Promise<Document> {
  const resp = await fetch(`${BASE}/documents/${docId}/content`, {
    method: "POST", headers: h(), body: JSON.stringify({ content, file_type: fileType }),
  });
  return resp.json();
}

export async function chunkDocument(docId: number): Promise<{ chunk_count: number }> {
  const resp = await fetch(`${BASE}/documents/${docId}/chunk`, {
    method: "POST", headers: h(),
  });
  return resp.json();
}

export async function uploadFile(
  file: File,
  title: string,
  categoryId: number,
  scope: string = "public",
  chunkStrategy: string = "recursive",
  department?: string,
  autoClean: boolean = true,
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title);
  formData.append("category_id", String(categoryId));
  formData.append("scope", scope);
  formData.append("chunk_strategy", chunkStrategy);
  formData.append("auto_clean", String(autoClean));
  if (department) formData.append("department", department);

  const resp = await fetch(`${BASE}/documents/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "上传失败" }));
    throw new Error(err.detail || "上传失败");
  }
  return resp.json();
}

const ALLOWED_FILE_EXTS = [".pdf", ".docx", ".md", ".txt"];
const ALLOWED_FILE_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/markdown",
  "text/plain",
];

export function validateFile(file: File): string | null {
  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  if (!ext || !ALLOWED_FILE_EXTS.includes(ext)) {
    return `不支持的文件类型: ${ext}，仅支持 pdf, docx, md, txt`;
  }
  if (file.size > 50 * 1024 * 1024) {
    return "文件大小不能超过 50MB";
  }
  return null;
}

export async function fetchDepartments(): Promise<string[]> {
  const resp = await fetch(`${BASE}/documents/departments`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) return [];
  return resp.json();
}

export async function fetchChunks(docId: number): Promise<Chunk[]> {
  const resp = await fetch(`${BASE}/documents/${docId}/chunks`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  return resp.json();
}

export async function resyncDocument(docId: number): Promise<{ synced: number }> {
  const resp = await fetch(`${BASE}/documents/${docId}/resync`, {
    method: "POST", headers: h(),
  });
  return resp.json();
}

export async function cleanDocument(docId: number, useLlm: boolean = false): Promise<CleanResponse> {
  const resp = await fetch(`${BASE}/documents/${docId}/clean`, {
    method: "POST", headers: h(), body: JSON.stringify({ use_llm: useLlm }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "清洗失败" }));
    throw new Error(err.detail || `清洗失败 (HTTP ${resp.status})`);
  }
  return resp.json();
}

export async function bulkCleanDocuments(
  ids: number[], useLlm: boolean = false,
): Promise<{ cleaned: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/documents/bulk-clean`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids, use_llm: useLlm }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
