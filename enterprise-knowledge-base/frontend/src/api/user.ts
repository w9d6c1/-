import { getToken } from "@/stores/auth";

const BASE = "/api/admin/users";

function headers() {
  return {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
}

export interface UserInfo {
  id: number;
  username: string | null;
  phone: string | null;
  display_name: string | null;
  email: string | null;
  role: string;
  department: string | null;
  is_active: boolean;
  created_at: string;
}

export interface UserListResponse {
  items: UserInfo[];
  total: number;
  page: number;
  page_size: number;
}

export async function fetchUsers(
  page = 1,
  pageSize = 20
): Promise<UserListResponse> {
  const resp = await fetch(
    `${BASE}?page=${page}&page_size=${pageSize}`,
    { headers: headers() }
  );
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function createUser(data: {
  username: string;
  password: string;
  password_confirm: string;
  display_name?: string;
  role?: string;
  department?: string;
}): Promise<UserInfo> {
  const resp = await fetch(BASE, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function updateUser(
  id: number,
  data: {
    role?: string;
    department?: string;
    display_name?: string;
    is_active?: boolean;
  }
): Promise<UserInfo> {
  const resp = await fetch(`${BASE}/${id}`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function disableUser(id: number): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function batchDisableUsers(ids: number[]): Promise<{ deleted: number; failed: { id: number; reason: string }[] }> {
  const resp = await fetch(`${BASE}/bulk-delete`, {
    method: "POST", headers: headers(), body: JSON.stringify({ ids }),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
