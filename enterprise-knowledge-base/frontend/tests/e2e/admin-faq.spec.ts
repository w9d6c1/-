import { test, expect } from "@playwright/test";

const MOCK_FAQS = {
  items: [
    {
      id: 1,
      question: "如何申请年假？",
      answer: "登录系统填写请假单即可。",
      category_id: 1,
      scope: "internal",
      status: "online",
      review_status: "approved",
      version: 1,
      similar_questions: ["年假申请", "请假流程"],
    },
    {
      id: 2,
      question: "退换货政策是什么？",
      answer: "七天无理由退换货。",
      category_id: 2,
      scope: "customer",
      status: "offline",
      review_status: "pending",
      version: 1,
      similar_questions: [],
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
  total_pages: 1,
};

const MOCK_CATEGORIES = {
  items: [
    { id: 1, name: "人事制度", parent_id: null },
    { id: 2, name: "售后服务", parent_id: null },
  ],
};

test.describe("FAQ admin page", () => {
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

    await page.route("**/api/admin/faqs?**", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_FAQS),
      });
    });
    await page.route("**/api/admin/categories**", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_CATEGORIES),
      });
    });
  });

  test("page loads FAQ rows with status tags", async ({ page }) => {
    await page.goto("/#/admin/faqs");
    await page.waitForLoadState("networkidle");

    await expect(page.locator('text=新建 FAQ')).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=如何申请年假？")).toBeVisible();
    await expect(page.locator("text=退换货政策是什么？")).toBeVisible();

    await expect(page.locator(".el-table").locator("text=在线")).toBeVisible();
    await expect(page.locator(".el-table").locator("text=待审")).toBeVisible();
  });

  test("create button is disabled until all fields are filled", async ({ page }) => {
    await page.goto("/#/admin/faqs");
    await page.waitForLoadState("networkidle");

    const createBtn = page.locator('button:has-text("新增 FAQ")');
    await expect(createBtn).toBeDisabled();

    await page.fill('input[placeholder="问题"]', "新问题");
    await page.fill('textarea[placeholder="答案"]', "新答案");
    await page.locator(".el-card").first().locator(".el-select").first().click();
    await page.click(".el-select-dropdown__item:has-text('人事制度')");
    await expect(createBtn).toBeEnabled();
  });

  test("row action buttons are present", async ({ page }) => {
    await page.goto("/#/admin/faqs");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator(".el-table__body .el-table__row").first();
    await expect(firstRow.locator('button:has-text("编辑")')).toBeVisible();
    await expect(firstRow.locator('button:has-text("历史")')).toBeVisible();
    await expect(firstRow.locator('button:has-text("删除")')).toBeVisible();
  });
});
