import { test, expect } from "@playwright/test";

const MOCK_ITEMS = {
  items: [
    {
      id: 1,
      title: "公司2024年度总结",
      scope: "public",
      status: "online",
      source_type: "wechat",
      source_name: "公司公众号",
      original_url: "https://mp.weixin.qq.com/s/abc",
      publish_time: "2024-12-01T10:00:00",
      word_count: 1500,
      chunk_count: 5,
      created_at: "2024-12-02T08:00:00",
      updated_at: "2024-12-02T08:00:00",
    },
    {
      id: 2,
      title: "技术分享：Vue3最佳实践",
      scope: "public",
      status: "offline",
      source_type: "zhihu",
      source_name: "知乎专栏",
      original_url: null,
      publish_time: null,
      word_count: 3000,
      chunk_count: 10,
      created_at: "2024-11-01T08:00:00",
      updated_at: "2024-11-15T08:00:00",
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
  total_pages: 1,
};

const MOCK_DETAIL = {
  ...MOCK_ITEMS.items[0],
  source_links: [
    {
      id: 1,
      doc_id: 1,
      platform: "wechat",
      external_id: "ext-abc",
      original_url: "https://mp.weixin.qq.com/s/abc",
      source_name: "公司公众号",
      publish_time: "2024-12-01T10:00:00",
      is_primary: true,
      created_at: "2024-12-02T08:00:00",
    },
  ],
};

test.describe("SourceContentList admin page", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.setItem("token", "fake-token-value");
      } catch {
        /* about:blank */
      }
    });

    await page.route("**/api/admin/auth/me", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 1,
          username: "tester",
          role: "operator",
          department: "运营部",
        }),
      });
    });

    await page.route("**/api/admin/source-contents?**", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_ITEMS),
      });
    });
    await page.route("**/api/admin/source-contents/1", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_DETAIL),
      });
    });
  });

  test("page loads with list data", async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await expect(page.locator('text=多源内容管理')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=内容列表（共 2 条）')).toBeVisible({ timeout: 5000 });

    await expect(page.locator("text=公司2024年度总结")).toBeVisible();
    await expect(page.locator("text=技术分享：Vue3最佳实践")).toBeVisible();
  });

  test("filter dropdowns are present", async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("来源平台").first()).toBeVisible();

    await expect(page.getByText("状态").first()).toBeVisible();

    const searchInput = page.locator('input[placeholder="搜索标题..."]');
    await expect(searchInput).toBeVisible();
  });

  test("status tags render correctly", async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await expect(page.locator(".el-table").locator("text=在线").first()).toBeVisible();
    await expect(page.locator(".el-table").locator("text=下线").first()).toBeVisible();
  });

  test('"同步管理" button opens sync drawer', async ({ page }) => {
    await page.route("**/api/admin/source-contents/sync-states", (route) => {
      route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });
    await page.route("**/api/admin/source-contents/sync-logs*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 10, total_pages: 0 }),
      });
    });

    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await page.click('button:has-text("同步管理")');
    await expect(page.getByRole("heading", { name: "同步管理" })).toBeVisible({ timeout: 3000 });
    await expect(page.locator('text=触发全平台同步')).toBeVisible();
  });

  test('"合并" button opens merge dialog', async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await expect(page.locator('button:has-text("合并")').first()).toBeVisible();
  });

  test('"详情" button opens detail dialog', async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    await page.locator('button:has-text("详情")').first().click();
    await expect(page.locator('text=来源链接 (1)')).toBeVisible({ timeout: 5000 });
  });

  test('action buttons present for each row', async ({ page }) => {
    await page.goto("/#/admin/source-contents");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator(".el-table__body .el-table__row").first();
    await expect(firstRow.locator('button:has-text("详情")')).toBeVisible();
    await expect(firstRow.locator('button:has-text("合并")')).toBeVisible();
    await expect(firstRow.locator('button:has-text("删除")')).toBeVisible();
  });
});
