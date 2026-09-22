import { defineStore } from "pinia";
import { ref } from "vue";
import {
  phoneLogin as apiPhoneLogin,
  getMe,
  type UserInfo,
} from "@/api/auth";

const memoryFallback = new Map<string, string>();

function safeGetItem(key: string): string | null {
  try {
    const v = localStorage.getItem(key);
    if (v !== null) return v;
  } catch {
    // 存储不可用，使用内存兜底
  }
  return memoryFallback.get(key) ?? null;
}

function safeSetItem(key: string, value: string): void {
  memoryFallback.set(key, value);
  try {
    localStorage.setItem(key, value);
  } catch {
    // 部分内嵌浏览器（如 VS Code Simple Browser）禁用存储写入，降级为仅内存保存
  }
}

function safeRemoveItem(key: string): void {
  memoryFallback.delete(key);
  try {
    localStorage.removeItem(key);
  } catch {
    // 忽略存储不可用
  }
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string>(safeGetItem("token") || "");
  const user = ref<UserInfo | null>(null);
  const isLoggedIn = ref(!!token.value);

  async function doPhoneLogin(phone: string, code: string) {
    const resp = await apiPhoneLogin(phone, code);
    token.value = resp.access_token;
    safeSetItem("token", resp.access_token);
    isLoggedIn.value = true;
    user.value = await getMe(resp.access_token);
  }

  async function init() {
    const saved = safeGetItem("token");
    if (saved && !user.value) {
      try {
        user.value = await getMe(saved);
        token.value = saved;
        isLoggedIn.value = true;
      } catch {
        logout();
      }
    }
  }

  function logout() {
    token.value = "";
    user.value = null;
    isLoggedIn.value = false;
    safeRemoveItem("token");
  }

  return { token, user, isLoggedIn, init, doPhoneLogin, logout };
});

export function getToken(): string {
  return safeGetItem("token") || "";
}

export function clearToken() {
  safeRemoveItem("token");
}

let _cachedRole: string | null = null;
let _cachedDept: string | null = null;

export function getUserRole(): string {
  if (_cachedRole) return _cachedRole;
  const token = getToken();
  if (!token) return "readonly";
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    _cachedRole = payload.role || "readonly";
    _cachedDept = payload.department || null;
    return _cachedRole as string;
  } catch {
    return "readonly";
  }
}

export function getUserDepartment(): string | null {
  if (_cachedDept !== null) return _cachedDept || null;
  getUserRole(); // fills both caches
  return _cachedDept || null;
}
