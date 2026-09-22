import { getToken } from "@/stores/auth";

const BASE = "/api/admin";

function h() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface OperationLog {
  id: number;
  operator_id: number | null;
  operator_name: string | null;
  operation_type: string;
  target_table: string;
  target_id: number | null;
  content_before: Record<string, unknown> | null;
  content_after: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OperationFilters {
  page?: number;
  page_size?: number;
  operator_name?: string;
  operation_type?: string;
  target_table?: string;
  start_date?: string;
  end_date?: string;
}

export async function fetchOperations(params?: OperationFilters): Promise<PaginatedResponse<OperationLog>> {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
  }
  const url = `${BASE}/operations${qs.toString() ? "?" + qs.toString() : ""}`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
  return resp.json();
}

export function exportOperationsUrl(params?: OperationFilters): string {
  const qs = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
  }
  return `${BASE}/operations/export${qs.toString() ? "?" + qs.toString() : ""}`;
}
