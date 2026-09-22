import axios from "axios";

const api = axios.create({
  baseURL: "/api",
});

export interface PhoneLoginResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username: string | null;
    phone: string | null;
    display_name: string | null;
    role: string;
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
}

export async function sendCode(phone: string): Promise<{ status: string; code?: string }> {
  const resp = await api.post("/admin/auth/send-code", { phone });
  return resp.data;
}

export async function phoneLogin(phone: string, code: string): Promise<PhoneLoginResponse> {
  const resp = await api.post<PhoneLoginResponse>("/admin/auth/phone-login", { phone, code });
  return resp.data;
}

export async function getMe(token: string): Promise<UserInfo> {
  const resp = await api.get<UserInfo>("/admin/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return resp.data;
}
