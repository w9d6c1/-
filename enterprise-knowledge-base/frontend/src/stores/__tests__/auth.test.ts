import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/auth", () => ({
  phoneLogin: vi.fn(),
  getMe: vi.fn(),
}));

import { phoneLogin, getMe } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

const mockedPhoneLogin = vi.mocked(phoneLogin);
const mockedGetMe = vi.mocked(getMe);

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("starts logged out when no token is stored", () => {
    const store = useAuthStore();
    expect(store.token).toBe("");
    expect(store.isLoggedIn).toBe(false);
    expect(store.user).toBeNull();
  });

  it("restores token from localStorage on creation", () => {
    localStorage.setItem("token", "saved-token");
    const store = useAuthStore();
    expect(store.token).toBe("saved-token");
    expect(store.isLoggedIn).toBe(true);
  });

  it("doPhoneLogin saves the token and loads the user profile", async () => {
    mockedPhoneLogin.mockResolvedValue({
      access_token: "token-xyz",
      user: { id: 1, username: "tester" },
    } as never);
    mockedGetMe.mockResolvedValue({
      id: 1,
      username: "tester",
      role: "operator",
      department: "运营部",
    } as never);

    const store = useAuthStore();
    await store.doPhoneLogin("13800000000", "123456");

    expect(mockedPhoneLogin).toHaveBeenCalledWith("13800000000", "123456");
    expect(store.token).toBe("token-xyz");
    expect(store.isLoggedIn).toBe(true);
    expect(store.user?.username).toBe("tester");
    expect(localStorage.getItem("token")).toBe("token-xyz");
  });

  it("init() restores a valid session", async () => {
    localStorage.setItem("token", "persisted-token");
    mockedGetMe.mockResolvedValue({
      id: 2,
      username: "restored",
      role: "readonly",
    } as never);

    const store = useAuthStore();
    await store.init();
    expect(store.isLoggedIn).toBe(true);
    expect(store.user?.username).toBe("restored");
  });

  it("init() logs out when the token is invalid", async () => {
    localStorage.setItem("token", "expired-token");
    mockedGetMe.mockRejectedValue(new Error("Unauthorized"));

    const store = useAuthStore();
    await store.init();
    expect(store.isLoggedIn).toBe(false);
    expect(store.token).toBe("");
    expect(localStorage.getItem("token")).toBeNull();
  });

  it("logout clears token and user state", async () => {
    localStorage.setItem("token", "t");
    mockedGetMe.mockResolvedValue({ id: 1, username: "u" } as never);
    const store = useAuthStore();
    await store.init();
    store.logout();
    expect(store.isLoggedIn).toBe(false);
    expect(store.token).toBe("");
    expect(localStorage.getItem("token")).toBeNull();
  });
});

function asciiJson(payload: object): string {
  return JSON.stringify(payload).replace(
    /[\u0080-\uffff]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}

function makeJwt(payload: object): string {
  const enc = (s: string) => Buffer.from(s, "utf8").toString("base64").replace(/=+$/, "");
  return `${enc(asciiJson({ alg: "HS256", typ: "JWT" }))}.${enc(asciiJson(payload))}.signature`;
}

describe("getUserRole / getUserDepartment", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
  });

  it("decodes role and department from the token payload", async () => {
    localStorage.setItem(
      "token",
      makeJwt({ role: "dept_admin", department: "技术部" }),
    );
    const { getUserRole, getUserDepartment } = await import("@/stores/auth");
    expect(getUserRole()).toBe("dept_admin");
    expect(getUserDepartment()).toBe("技术部");
  });

  it("falls back to readonly for a malformed token", async () => {
    localStorage.setItem("token", "not-a-jwt");
    const { getUserRole } = await import("@/stores/auth");
    expect(getUserRole()).toBe("readonly");
  });
});
