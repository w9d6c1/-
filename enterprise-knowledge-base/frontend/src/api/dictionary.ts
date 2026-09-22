import { getToken } from "@/stores/auth";

const BASE = "/api/admin";

function h() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface Synonym {
  id: number;
  word: string;
  synonyms: string[];
  scope: string;
}

export interface SensitiveWord {
  id: number;
  word: string;
  word_type: string;
  answer: string | null;
  scope: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface BatchImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

// ── 同义词 ──

export async function fetchSynonyms(page: number = 1, pageSize: number = 50): Promise<PaginatedResponse<Synonym>> {
  const resp = await fetch(`${BASE}/synonyms?page=${page}&page_size=${pageSize}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  return resp.json();
}

export async function createSynonym(word: string, synonyms: string[], scope: string = "public"): Promise<Synonym> {
  const resp = await fetch(`${BASE}/synonyms`, {
    method: "POST", headers: h(), body: JSON.stringify({ word, synonyms, scope }),
  });
  return resp.json();
}

export async function updateSynonym(id: number, payload: Partial<Synonym>): Promise<Synonym> {
  const resp = await fetch(`${BASE}/synonyms/${id}`, {
    method: "PUT", headers: h(), body: JSON.stringify(payload),
  });
  return resp.json();
}

export async function deleteSynonym(id: number): Promise<void> {
  await fetch(`${BASE}/synonyms/${id}`, { method: "DELETE", headers: h() });
}

export async function batchDeleteSynonyms(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/synonyms/bulk-delete`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function importSynonymsCsv(file: File): Promise<BatchImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE}/synonyms/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "导入失败" }));
    throw new Error(err.detail || "导入失败");
  }
  return resp.json();
}

// ── 敏感词 ──

export async function fetchSensitiveWords(page: number = 1, pageSize: number = 50): Promise<PaginatedResponse<SensitiveWord>> {
  const resp = await fetch(`${BASE}/sensitive-words?page=${page}&page_size=${pageSize}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  return resp.json();
}

export async function createSensitiveWord(word: string, answer?: string): Promise<SensitiveWord> {
  const resp = await fetch(`${BASE}/sensitive-words`, {
    method: "POST", headers: h(), body: JSON.stringify({ word, word_type: "sensitive", answer: answer || null }),
  });
  return resp.json();
}

export async function deleteSensitiveWord(id: number): Promise<void> {
  await fetch(`${BASE}/sensitive-words/${id}`, { method: "DELETE", headers: h() });
}

export async function batchDeleteSensitiveWords(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/sensitive-words/bulk-delete`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function importSensitiveWordsCsv(file: File): Promise<BatchImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE}/sensitive-words/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "导入失败" }));
    throw new Error(err.detail || "导入失败");
  }
  return resp.json();
}

// ── 禁答词 ──

export async function fetchForbidWords(page: number = 1, pageSize: number = 50): Promise<PaginatedResponse<SensitiveWord>> {
  const resp = await fetch(`${BASE}/forbid-words?page=${page}&page_size=${pageSize}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  return resp.json();
}

export async function createForbidWord(word: string, answer?: string, scope?: string): Promise<SensitiveWord> {
  const resp = await fetch(`${BASE}/forbid-words`, {
    method: "POST", headers: h(), body: JSON.stringify({ word, answer: answer || null, scope: scope || "all" }),
  });
  return resp.json();
}

export async function deleteForbidWord(id: number): Promise<void> {
  await fetch(`${BASE}/forbid-words/${id}`, { method: "DELETE", headers: h() });
}

export async function batchDeleteForbidWords(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/forbid-words/bulk-delete`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function importForbidWordsCsv(file: File): Promise<BatchImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE}/forbid-words/import`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "导入失败" }));
    throw new Error(err.detail || "导入失败");
  }
  return resp.json();
}
