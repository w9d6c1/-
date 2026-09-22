import { test, expect } from "@playwright/test";

const MOCK_USER = {
  id: 1,
  username: "tester",
  phone: "13812345678",
  display_name: "测试员",
  email: null,
  role: "operator",
  department: "运营部",
  is_active: true,
  created_at: "2026-01-01T00:00:00",
};

test.describe("Login page (phone + SMS)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/admin/auth/send-code", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", code: "123456" }),
      });
    });
    await page.route("**/api/admin/auth/phone-login", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-token",
          token_type: "bearer",
          user: MOCK_USER,
        }),
      });
    });
    await page.route("**/api/admin/auth/me", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_USER),
      });
    });
  });

  test("sends SMS code and shows it", async ({ page }) => {
    await page.goto("/#/login");
    await page.waitForLoadState("networkidle");

    await page.fill('input[placeholder="请输入手机号"]', "13812345678");
    await page.click('button:has-text("获取验证码")');

    await expect(page.locator('text=验证码: 123456')).toBeVisible({ timeout: 5000 });
  });

  test("validates empty phone before sending code", async ({ page }) => {
    await page.goto("/#/login");
    await page.waitForLoadState("networkidle");

    await page.click('button:has-text("获取验证码")');
    await expect(page.locator("text=请输入手机号")).toBeVisible();
  });

  test("phone login redirects to admin dashboard", async ({ page }) => {
    await page.goto("/#/login");
    await page.waitForLoadState("networkidle");

    await page.fill('input[placeholder="请输入手机号"]', "13812345678");
    await page.fill('input[placeholder="请输入验证码"]', "123456");
    await page.click('button:has-text("登录 / 注册")');

    await expect(page).toHaveURL(/#\/admin/, { timeout: 10000 });
  });

  test("failed phone login shows backend error message", async ({ page }) => {
    await page.route("**/api/admin/auth/phone-login", (route) => {
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "验证码错误" }),
      });
    });
    await page.goto("/#/login");
    await page.waitForLoadState("networkidle");

    await page.fill('input[placeholder="请输入手机号"]', "13812345678");
    await page.fill('input[placeholder="请输入验证码"]', "000000");
    await page.click('button:has-text("登录 / 注册")');

    await expect(page.locator("text=验证码错误")).toBeVisible({ timeout: 5000 });
  });
});
