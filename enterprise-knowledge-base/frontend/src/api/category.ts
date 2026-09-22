import { getToken } from "@/stores/auth";

const BASE = "/api/admin";

function headers() {
  return { Authorization: `Bearer ${getToken()}` };
}

function jsonHeaders() {
  return { ...headers(), "Content-Type": "application/json" };
}

export type CategoryScope = "public" | "customer" | "internal";
export type CategoryStatus = "enabled" | "disabled";

export interface Category {
  id: number;
  parent_id: number | null;
  name: string;
  sort_order: number;
  scope: string;
  status: string;
  department: string | null;
  children?: Category[];
}

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CategoryPayload {
  name: string;
  scope: CategoryScope;
  parent_id?: number | null;
  sort_order?: number;
  department?: string | null;
}

export interface CategoryUpdatePayload {
  name?: string;
  scope?: CategoryScope;
  parent_id?: number | null;
  sort_order?: number;
  status?: CategoryStatus;
}

/** 扁平分类列表 (用于父级下拉选择) */
export async function fetchCategories(): Promise<Category[]> {
  const resp = await fetch(`${BASE}/categories?page_size=500`, { headers: headers() });
  const data: PaginatedResponse<Category> = await resp.json();
  return data.items ?? [];
}

/** 树形分类结构 (根节点数组，children 递归嵌套) */
export async function fetchCategoryTree(): Promise<Category[]> {
  const resp = await fetch(`${BASE}/categories/tree`, { headers: headers() });
  return resp.json();
}

export async function createCategory(data: CategoryPayload): Promise<Category> {
  const resp = await fetch(`${BASE}/categories`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function updateCategory(id: number, data: CategoryUpdatePayload): Promise<Category> {
  const resp = await fetch(`${BASE}/categories/${id}`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function setCategoryStatus(id: number, status: CategoryStatus): Promise<Category> {
  return updateCategory(id, { status });
}

export async function deleteCategory(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/categories/${id}`, { method: "DELETE", headers: headers() });
  if (!resp.ok) throw new Error(await resp.text());
}

export async function batchDeleteCategories(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/categories/bulk-delete`, {
    method: "POST", headers: jsonHeaders(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
