<template>
  <div>
    <el-card>
      <h3>审核中心</h3>

      <el-tabs v-model="activeTab">
        <!-- ═══ 待审核文档 ═══ -->
        <el-tab-pane :label="`待审核文档（${docPending.length}）`" name="docs">
          <el-table :data="docPending" stripe v-loading="loadingDoc">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="scope" label="范围" width="70">
              <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="切片" width="60" />
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button size="small" @click="previewDoc(row.id)">查看</el-button>
                <el-button size="small" type="success" @click="approveDoc(row.id)">通过</el-button>
                <el-button size="small" type="danger" @click="rejectDoc(row.id)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ═══ 已审核文档 ═══ -->
        <el-tab-pane :label="`已审核文档（${docReviewed.length}）`" name="docsReviewed">
          <el-table :data="docReviewed" stripe v-loading="loadingDoc">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="scope" label="范围" width="70">
              <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
            </el-table-column>
            <el-table-column label="审核状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.review_status === 'approved' ? 'success' : 'danger'" size="small">
                  {{ row.review_status === 'approved' ? '已通过' : '已驳回' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="review_comment" label="审核意见" min-width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" @click="previewDoc(row.id)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ═══ 待审核 FAQ ═══ -->
        <el-tab-pane :label="`待审核 FAQ（${faqPending.length}）`" name="faqs">
          <el-table :data="faqPending" stripe v-loading="loadingFaq">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="question" label="问题" min-width="250" show-overflow-tooltip />
            <el-table-column prop="scope" label="范围" width="70">
              <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button size="small" @click="previewFaq(row)">查看</el-button>
                <el-button size="small" type="success" @click="approveFaq(row.id)">通过</el-button>
                <el-button size="small" type="danger" @click="rejectFaq(row.id)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- ═══ 已审核 FAQ ═══ -->
        <el-tab-pane :label="`已审核 FAQ（${faqReviewed.length}）`" name="faqsReviewed">
          <el-table :data="faqReviewed" stripe v-loading="loadingFaq">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="question" label="问题" min-width="250" show-overflow-tooltip />
            <el-table-column prop="scope" label="范围" width="70">
              <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
            </el-table-column>
            <el-table-column label="审核状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.review_status === 'approved' ? 'success' : 'danger'" size="small">
                  {{ row.review_status === 'approved' ? '已通过' : '已驳回' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="review_comment" label="审核意见" min-width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" @click="previewFaq(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="800px" top="5vh">
      <div v-if="previewLoading" style="text-align:center; padding:40px">加载中...</div>
      <div v-else class="preview-body">
        <div v-if="previewType === 'faq'" class="preview-faq">
          <div class="preview-section">
            <div class="preview-label">问题</div>
            <div class="preview-text">{{ previewFaqData?.question }}</div>
          </div>
          <div class="preview-section">
            <div class="preview-label">答案</div>
            <div class="preview-text answer">{{ previewFaqData?.answer }}</div>
          </div>
        </div>
        <div v-else class="preview-doc">
          <div class="preview-section">
            <div class="preview-label">标题</div>
            <div class="preview-text">{{ previewDocData?.title }}</div>
          </div>
          <div class="preview-section">
            <div class="preview-label">正文（{{ previewDocData?.word_count || 0 }} 字）</div>
            <div class="preview-text content">{{ previewDocData?.plain_text || '（无文本内容）' }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <template v-if="previewIsPending">
          <el-button type="success" @click="previewApprove">通过</el-button>
          <el-button type="danger" @click="previewReject">驳回</el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { fetchDocuments, fetchDocument, reviewDocument, type Document, type DocumentDetail } from "@/api/document";
import { fetchFAQs, approveFAQ, rejectFAQ, type FAQ } from "@/api/faq";

const activeTab = ref("docs");
const loadingDoc = ref(false);
const loadingFaq = ref(false);
const allDocs = ref<Document[]>([]);
const allFaqs = ref<FAQ[]>([]);

const docPending = computed(() => allDocs.value.filter((d) => d.review_status === "pending"));
const docReviewed = computed(() => allDocs.value.filter((d) => d.review_status !== "pending" && d.review_status !== "draft"));
const faqPending = computed(() => allFaqs.value.filter((f) => f.review_status === "pending"));
const faqReviewed = computed(() => allFaqs.value.filter((f) => f.review_status !== "pending" && f.review_status !== "draft"));

// ── 预览弹窗 ──
const previewVisible = ref(false);
const previewLoading = ref(false);
const previewTitle = ref("");
const previewType = ref<"faq" | "doc">("faq");
const previewIsPending = ref(false);
const previewFaqData = ref<FAQ | null>(null);
const previewDocData = ref<DocumentDetail | null>(null);
const previewCurrentId = ref(0);

function scopeLabel(scope: string) {
  if (scope === "public") return "公共";
  if (scope === "customer") return "客服";
  return "内部";
}

async function loadDocs() {
  loadingDoc.value = true;
  try {
    const res = await fetchDocuments({ page_size: 100 });
    allDocs.value = res.items ?? [];
  } catch (e: any) {
    ElMessage.error(e.message || "加载文档列表失败");
  } finally {
    loadingDoc.value = false;
  }
}

async function loadFaqs() {
  loadingFaq.value = true;
  try {
    const res = await fetchFAQs(1, 500);
    allFaqs.value = res.items ?? [];
  } catch (e: any) {
    ElMessage.error(e.message || "加载 FAQ 列表失败");
  } finally {
    loadingFaq.value = false;
  }
}

async function previewFaq(row: FAQ) {
  previewType.value = "faq";
  previewTitle.value = `FAQ 详情 — #${row.id}`;
  previewFaqData.value = row;
  previewDocData.value = null;
  previewCurrentId.value = row.id;
  previewIsPending.value = row.review_status === "pending";
  previewVisible.value = true;
}

async function previewDoc(id: number) {
  previewType.value = "doc";
  previewTitle.value = `文档详情 — #${id}`;
  previewFaqData.value = null;
  previewDocData.value = null;
  previewCurrentId.value = id;
  previewLoading.value = true;
  previewVisible.value = true;
  try {
    const detail = await fetchDocument(id);
    previewDocData.value = detail;
    previewIsPending.value = detail.review_status === "pending";
  } catch (e: any) {
    ElMessage.error(e.message || "加载文档失败");
    previewVisible.value = false;
  } finally {
    previewLoading.value = false;
  }
}

async function previewApprove() {
  const id = previewCurrentId.value;
  if (previewType.value === "doc") {
    await reviewDocument(id, "approve");
    previewVisible.value = false;
    ElMessage.success("已通过");
    await loadDocs();
  } else {
    await approveFAQ(id);
    previewVisible.value = false;
    ElMessage.success("审核通过");
    await loadFaqs();
  }
}

async function previewReject() {
  const id = previewCurrentId.value;
  try {
    const { value } = await ElMessageBox.prompt("请输入驳回原因（选填）", "驳回", {
      confirmButtonText: "确认驳回", cancelButtonText: "取消", inputPlaceholder: "驳回原因...",
    });
    if (previewType.value === "doc") {
      await reviewDocument(id, "reject", value || undefined);
      previewVisible.value = false;
      ElMessage.success("已驳回");
      await loadDocs();
    } else {
      await rejectFAQ(id, value || undefined);
      previewVisible.value = false;
      ElMessage.success("已驳回");
      await loadFaqs();
    }
  } catch { /* cancelled */ }
}

async function approveDoc(id: number) {
  await reviewDocument(id, "approve");
  ElMessage.success("已通过");
  await loadDocs();
}

async function rejectDoc(id: number) {
  try {
    const { value } = await ElMessageBox.prompt("请输入驳回原因（选填）", "驳回文档", {
      confirmButtonText: "确认驳回", cancelButtonText: "取消", inputPlaceholder: "驳回原因...",
    });
    await reviewDocument(id, "reject", value || undefined);
    ElMessage.success("已驳回");
    await loadDocs();
  } catch { /* cancelled */ }
}

async function approveFaq(id: number) {
  try {
    await approveFAQ(id);
    ElMessage.success("审核通过");
    await loadFaqs();
  } catch (e: any) { ElMessage.error(e.message || "操作失败"); }
}

async function rejectFaq(id: number) {
  try {
    const { value } = await ElMessageBox.prompt("请输入驳回原因（选填）", "驳回 FAQ", {
      confirmButtonText: "确认驳回", cancelButtonText: "取消", inputPlaceholder: "驳回原因...",
    });
    await rejectFAQ(id, value || undefined);
    ElMessage.success("已驳回");
    await loadFaqs();
  } catch { /* cancelled */ }
}

onMounted(async () => {
  await Promise.all([loadDocs(), loadFaqs()]);
});
</script>

<style scoped>
.preview-body { max-height: 60vh; overflow-y: auto; }
.preview-section { margin-bottom: 20px; }
.preview-label { font-weight: 600; color: #303133; margin-bottom: 8px; font-size: 14px; }
.preview-text { font-size: 14px; line-height: 1.8; color: #606266; white-space: pre-wrap; word-break: break-word; }
.preview-text.content { background: #f5f7fa; padding: 16px; border-radius: 8px; border: 1px solid #ebeef5; }
.preview-text.answer { background: #f5f7fa; padding: 16px; border-radius: 8px; border: 1px solid #ebeef5; }
</style>
