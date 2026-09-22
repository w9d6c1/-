import { getToken } from "@/stores/auth";

const BASE = "/api/admin/source-contents";

function h() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface SourceContent {
  id: number;
  title: string;
  scope: string;
  status: string;
  source_type: string;
  source_name: string | null;
  original_url: string | null;
  publish_time: string | null;
  word_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface SourceContentDetail extends SourceContent {
  source_links: SourceLink[];
}

export interface SourceLink {
  id: number;
  doc_id: number;
  platform: string;
  external_id: string;
  original_url: string | null;
  source_name: string | null;
  publish_time: string | null;
  is_primary: boolean;
  created_at: string;
}

export interface SyncState {
  platform: string;
  last_cursor: string | null;
  last_sync_at: string | null;
  last_status: string;
  last_error: string | null;
}

export interface SyncLog {
  id: number;
  platform: string;
  started_at: string;
  finished_at: string | null;
  fetched_count: number;
  ingested_count: number;
  duplicated_count: number;
  status: string;
  error: string | null;
}

export interface SyncTriggerResult {
  total_fetched: number;
  total_ingested: number;
  failed_platforms: string[];
  all_ok: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SourceContentListParams {
  page?: number;
  page_size?: number;
  source_type?: string;
  status?: string;
  search?: string;
}

export async function fetchSourceContents(
  params?: SourceContentListParams,
): Promise<PaginatedResponse<SourceContent>> {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
  }
  const url = `${BASE}${qs.toString() ? "?" + qs.toString() : ""}`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`加载列表失败 (HTTP ${resp.status}) ${err}`);
  }
  return resp.json();
}

export async function fetchSourceContentDetail(id: number): Promise<SourceContentDetail> {
  const resp = await fetch(`${BASE}/${id}`, { headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function updateSourceContentStatus(
  id: number,
  status: "online" | "offline",
): Promise<SourceContent> {
  const resp = await fetch(`${BASE}/${id}/status`, {
    method: "PUT",
    headers: h(),
    body: JSON.stringify({ status }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function deleteSourceContent(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/${id}`, { method: "DELETE", headers: h() });
  if (!resp.ok) throw new Error(await resp.text());
}

export async function mergeSourceContents(
  primaryDocId: number,
  duplicateDocId: number,
): Promise<SourceContent> {
  const resp = await fetch(`${BASE}/merge`, {
    method: "POST",
    headers: h(),
    body: JSON.stringify({ primary_doc_id: primaryDocId, duplicate_doc_id: duplicateDocId }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function triggerSync(
  platforms?: string[],
): Promise<SyncTriggerResult> {
  const resp = await fetch(`${BASE}/sync`, {
    method: "POST",
    headers: h(),
    body: JSON.stringify({ platforms: platforms || null }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function fetchPreviewUrl(id: number): Promise<string> {
  const resp = await fetch(`${BASE}/${id}/preview-url`, { headers: h() });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "无可用预览链接" }));
    throw new Error(err.detail || `获取链接失败 (HTTP ${resp.status})`);
  }
  return (await resp.json()).url;
}

export async function fetchSyncStates(): Promise<SyncState[]> {
  const resp = await fetch(`${BASE}/sync-states`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function fetchSyncLogs(
  platform?: string,
  page?: number,
  pageSize?: number,
): Promise<PaginatedResponse<SyncLog>> {
  const qs = new URLSearchParams();
  if (platform) qs.set("platform", platform);
  if (page) qs.set("page", String(page));
  if (pageSize) qs.set("page_size", String(pageSize));
  const url = `${BASE}/sync-logs${qs.toString() ? "?" + qs.toString() : ""}`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
