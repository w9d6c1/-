import { getToken } from "@/stores/auth";

const BASE = "/api/admin";

function h() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface FAQ {
  id: number;
  category_id: number;
  question: string;
  similar_questions: string[] | null;
  answer: string;
  tags: string[] | null;
  scope: string;
  status: string;
  version: number;
  review_status: string;
  reviewer_id: number | null;
  review_comment: string | null;
  department: string | null;
  effective_start: string | null;
  effective_end: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export async function fetchFAQs(page: number = 1, pageSize: number = 500): Promise<PaginatedResponse<FAQ>> {
  const resp = await fetch(`${BASE}/faqs?page=${page}&page_size=${pageSize}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`加载 FAQ 列表失败 (HTTP ${resp.status}) ${err}`);
  }
  return resp.json();
}

export async function fetchFAQ(id: number): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  return resp.json();
}

export async function createFAQ(data: { category_id: number; question: string; answer: string }): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs`, { method: "POST", headers: h(), body: JSON.stringify(data) });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export type FAQUpdatePayload = Partial<FAQ> & { scope?: string; department?: string };

export async function updateFAQ(id: number, data: FAQUpdatePayload): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}`, { method: "PUT", headers: h(), body: JSON.stringify(data) });
  return resp.json();
}

export async function deleteFAQ(id: number): Promise<void> {
  await fetch(`${BASE}/faqs/${id}`, { method: "DELETE", headers: h() });
}

export async function batchDeleteFAQs(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/faqs/bulk-delete`, {
    method: "POST", headers: h(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export interface FAQCreatePayload {
  category_id: number;
  question: string;
  answer: string;
  scope?: string;
  similar_questions?: string[];
  tags?: string[];
}

export async function bulkImportFAQ(items: FAQCreatePayload[]): Promise<{ imported: number }> {
  const resp = await fetch(`${BASE}/faqs/bulk`, { method: "POST", headers: h(), body: JSON.stringify({ items }) });
  return resp.json();
}

export async function submitForReview(id: number): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}/submit`, { method: "POST", headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function approveFAQ(id: number): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}/approve`, { method: "POST", headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function rejectFAQ(id: number, comment?: string): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}/reject`, {
    method: "POST", headers: h(), body: JSON.stringify({ action: "reject", comment: comment || null }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export interface FAQVersion {
  id: number;
  version: number;
  question: string;
  answer: string;
  similar_questions: string[] | null;
  tags: string[] | null;
  scope: string;
  status: string;
  created_at: string;
}

export async function getFAQVersions(id: number): Promise<FAQVersion[]> {
  const resp = await fetch(`${BASE}/faqs/${id}/versions`, { headers: { Authorization: `Bearer ${getToken()}` } });
  return resp.json();
}

export async function rollbackFAQ(id: number, versionId: number): Promise<FAQ> {
  const resp = await fetch(`${BASE}/faqs/${id}/rollback/${versionId}`, { method: "POST", headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
