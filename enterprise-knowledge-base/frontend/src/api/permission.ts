import { getToken } from "@/stores/auth";

const BASE = "/api/admin/scope-permissions";

function headers() {
  return { Authorization: `Bearer ${getToken()}` };
}

export interface ScopePermission {
  id: number;
  role: string;
  scope: string;
  is_active: boolean;
}

export async function fetchPermissions(): Promise<ScopePermission[]> {
  const resp = await fetch(BASE, { headers: headers() });
  const data = await resp.json();
  return data.items ?? data;
}

export async function createPermission(data: {
  role: string;
  scope: string;
  is_active?: boolean;
}): Promise<ScopePermission> {
  const resp = await fetch(BASE, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function updatePermission(
  id: number,
  data: { is_active: boolean }
): Promise<ScopePermission> {
  const resp = await fetch(`${BASE}/${id}`, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function deletePermission(id: number): Promise<void> {
  await fetch(`${BASE}/${id}`, { method: "DELETE", headers: headers() });
}

export async function createDefaults(): Promise<{ created: number }> {
  const resp = await fetch(`${BASE}/defaults`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function reloadCache(): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/reload`, {
    method: "POST",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
