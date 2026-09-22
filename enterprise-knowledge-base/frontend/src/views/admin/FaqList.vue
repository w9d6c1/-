<template>
  <div>
    <!-- 创建 + 批量导入 -->
    <el-card style="margin-bottom: 16px">
      <template #header>
        <span>新建 FAQ</span>
        <el-button style="float: right" size="small" @click="importVisible = true">批量导入</el-button>
      </template>
      <el-space fill alignment="start" style="flex-wrap: wrap" :size="12">
        <el-input v-model="form.question" placeholder="问题" style="width: 260px" />
        <el-input v-model="form.answer" type="textarea" :rows="2" placeholder="答案" style="width: 300px" />
        <el-select v-model="form.category_id" placeholder="分类" style="width: 160px">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="form.scope" style="width: 100px">
          <el-option label="公共" value="public" />
          <el-option label="客服" value="customer" />
          <el-option label="内部" value="internal" />
        </el-select>
        <el-button type="primary" :disabled="!form.question || !form.answer || !form.category_id" @click="handleCreate">新增 FAQ</el-button>
      </el-space>
    </el-card>

    <!-- 列表 -->
    <el-card>
      <template #header>
        <el-space>
          <el-select v-model="filterCategory" placeholder="全部分类" clearable style="width: 140px" @change="loadFAQs">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <el-select v-model="filterScope" placeholder="全部范围" clearable style="width: 110px" @change="loadFAQs">
            <el-option label="公共" value="public" />
            <el-option label="客服" value="customer" />
            <el-option label="内部" value="internal" />
          </el-select>
          <el-select v-model="filterReview" placeholder="全部审核状态" clearable style="width: 130px">
            <el-option label="待审核" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
          <el-input v-model="searchQuery" placeholder="搜索问题..." style="width: 200px" clearable />
        </el-space>
      </template>

      <div v-if="selectedIds.length > 0" style="margin-bottom:12px">
        <el-button type="danger" @click="handleBatchDelete">批量删除 ({{ selectedIds.length }})</el-button>
        <el-button @click="selectedIds = []">取消选择</el-button>
      </div>

      <el-table :data="filteredFAQs" stripe v-loading="loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="问题" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.question }}</span>
            <el-badge v-if="row.similar_questions?.length" :value="row.similar_questions.length" style="margin-left: 8px" />
          </template>
        </el-table-column>
        <el-table-column label="分类" width="100">
          <template #default="{ row }">{{ catName(row.category_id) }}</template>
        </el-table-column>
        <el-table-column label="范围" width="70">
          <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : row.status === 'draft' ? 'info' : 'warning'" size="small">{{ row.status === 'online' ? '在线' : row.status === 'draft' ? '草稿' : '下线' }}</el-tag>
            <el-tag v-if="row.review_status === 'pending'" type="warning" size="small" style="margin-left: 4px">待审</el-tag>
            <el-tag v-else-if="row.review_status === 'rejected'" type="danger" size="small" style="margin-left: 4px">{{ row.review_comment ? `驳回: ${row.review_comment}` : '已驳回' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="60" />
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.review_status === 'pending'" size="small" type="success" @click="handleApprove(row.id)">通过</el-button>
            <el-button v-if="row.review_status === 'pending'" size="small" type="danger" @click="handleReject(row.id)">驳回</el-button>
            <el-button v-if="row.status === 'draft' && row.review_status !== 'pending'" size="small" type="warning" @click="submitReview(row.id)">提交审核</el-button>
            <el-button size="small" :type="row.status === 'online' ? 'warning' : 'success'" @click="toggleStatus(row)">{{ row.status === 'online' ? '下线' : '上线' }}</el-button>
            <el-button size="small" @click="openVersions(row)">历史</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑 Dialog -->
    <el-dialog v-model="editVisible" :title="`编辑 FAQ #${editForm.id}`" width="640px">
      <el-form label-width="80px">
        <el-form-item label="问题">
          <el-input v-model="editForm.question" />
        </el-form-item>
        <el-form-item label="答案">
          <el-input v-model="editForm.answer" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category_id" style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="范围">
          <el-select v-model="editForm.scope" style="width: 100%">
            <el-option label="公共" value="public" />
            <el-option label="客服" value="customer" />
            <el-option label="内部" value="internal" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editForm.status" style="width: 100%">
            <el-option label="在线" value="online" />
            <el-option label="下线" value="offline" />
            <el-option label="草稿" value="draft" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="editForm.department" placeholder="可选" />
        </el-form-item>
        <el-form-item label="生效开始">
          <el-date-picker v-model="editForm.effective_start" type="datetime" placeholder="可选" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss" />
        </el-form-item>
        <el-form-item label="生效结束">
          <el-date-picker v-model="editForm.effective_end" type="datetime" placeholder="可选" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss" />
        </el-form-item>
        <el-form-item label="标签">
          <el-space>
            <el-tag v-for="(t, i) in editForm.tags" :key="i" closable @close="editForm.tags.splice(i, 1)">{{ t }}</el-tag>
            <el-input v-if="tagInputVisible" ref="tagInputRef" v-model="newTag" size="small" style="width: 100px" @keyup.enter="addTag" @blur="addTag" />
            <el-button v-else size="small" @click="showTagInput">+ 标签</el-button>
          </el-space>
        </el-form-item>
        <el-form-item label="相似问句">
          <div v-for="(s, i) in editForm.similar_questions" :key="i" style="margin-bottom: 4px">
            <el-tag closable @close="editForm.similar_questions.splice(i, 1)">{{ s }}</el-tag>
          </div>
          <el-input v-model="newSimilar" size="small" placeholder="输入相似问句，回车添加" style="width: 60%; margin-top: 4px" @keyup.enter="addSimilar" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 版本历史 Dialog -->
    <el-dialog v-model="versionVisible" :title="`版本历史 — #${versionFaqId}`" width="700px">
      <el-timeline v-loading="versionLoading">
        <el-timeline-item
          v-for="v in versions"
          :key="v.id"
          :timestamp="v.created_at"
          placement="top"
        >
          <el-card shadow="hover">
            <p><strong>v{{ v.version }}</strong> — {{ scopeLabel(v.scope) }} / {{ v.status }}</p>
            <p style="color: #606266; font-size: 13px; margin: 6px 0"><b>Q:</b> {{ v.question }}</p>
            <p style="color: #606266; font-size: 13px; margin: 6px 0"><b>A:</b> {{ v.answer.substring(0, 120) }}{{ v.answer.length > 120 ? '...' : '' }}</p>
            <div v-if="v.tags?.length" style="margin: 4px 0">
              <el-tag v-for="t in v.tags" :key="t" size="small" style="margin-right: 4px">{{ t }}</el-tag>
            </div>
            <el-button size="small" type="warning" style="margin-top: 6px" @click="handleRollback(v.id)">回滚到此版本</el-button>
          </el-card>
        </el-timeline-item>
      </el-timeline>
      <template #footer>
        <el-button @click="versionVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入 Dialog -->
    <el-dialog v-model="importVisible" title="批量导入 FAQ" width="600px">
      <p style="color: #909399; margin-bottom: 8px">每行一个 FAQ，格式：问题 | 答案</p>
      <el-input v-model="importText" type="textarea" :rows="10" placeholder="如何退货 | 请在订单页面申请退货&#10;保修期多久 | 产品保修期为1年" />
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!importText.trim()" :loading="importing" @click="handleBulkImport">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getToken } from "@/stores/auth";
import {
  fetchFAQs, createFAQ, updateFAQ, deleteFAQ, bulkImportFAQ, batchDeleteFAQs,
  submitForReview, approveFAQ, rejectFAQ,
  getFAQVersions, rollbackFAQ,
  type FAQ,
} from "@/api/faq";

const BASE = "/api/admin";
function h() { return { Authorization: `Bearer ${getToken()}` }; }

interface Category { id: number; name: string; }

const faqs = ref<FAQ[]>([]);
const categories = ref<Category[]>([]);
const loading = ref(false);
const filterCategory = ref<number>();
const filterScope = ref("");
const filterReview = ref("");
const searchQuery = ref("");

const form = ref({ question: "", answer: "", category_id: 0 as unknown as number, scope: "public" });

const editVisible = ref(false);
const editForm = ref({
  id: 0, question: "", answer: "", category_id: 0, scope: "public", status: "draft",
  department: "", tags: [] as string[], similar_questions: [] as string[],
  effective_start: "", effective_end: "",
});
const newTag = ref("");
const tagInputVisible = ref(false);
const tagInputRef = ref();
const newSimilar = ref("");
const saving = ref(false);

const versionVisible = ref(false);
const versionFaqId = ref(0);
const versions = ref<any[]>([]);
const versionLoading = ref(false);

const importVisible = ref(false);
const importText = ref("");
const importing = ref(false);
const selectedIds = ref<number[]>([]);

function handleSelectionChange(rows: FAQ[]) {
  selectedIds.value = rows.map(r => r.id);
}

const filteredFAQs = computed(() => {
  let result = faqs.value;
  if (filterCategory.value) result = result.filter(f => f.category_id === filterCategory.value);
  if (filterScope.value) result = result.filter(f => f.scope === filterScope.value);
  if (filterReview.value) result = result.filter(f => f.review_status === filterReview.value);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter(f => f.question.toLowerCase().includes(q) || f.answer.toLowerCase().includes(q));
  }
  return result;
});

function catName(id: number) { return categories.value.find(c => c.id === id)?.name || `#${id}`; }
function scopeLabel(s: string) { return s === "public" ? "公共" : s === "customer" ? "客服" : "内部"; }

async function loadCategories() {
  try {
    const resp = await fetch(`${BASE}/categories?page_size=500`, { headers: h() });
    if (resp.ok) {
      const data = await resp.json();
      categories.value = data.items || data;
    }
  } catch { /* ignore */ }
}

async function loadFAQs() {
  loading.value = true;
  try {
    const res = await fetchFAQs();
    faqs.value = res.items;
  } catch {
    ElMessage.error("加载 FAQ 失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  if (!form.value.question || !form.value.answer || !form.value.category_id) return;
  try {
    await createFAQ({ category_id: form.value.category_id, question: form.value.question, answer: form.value.answer });
    form.value.question = ""; form.value.answer = "";
    await loadFAQs();
    ElMessage.success("FAQ 已创建");
  } catch (e: any) {
    ElMessage.error(e.message || "创建失败");
  }
}

function openEdit(faq: FAQ) {
  editForm.value = {
    id: faq.id, question: faq.question, answer: faq.answer,
    category_id: faq.category_id, scope: faq.scope || "public", status: faq.status || "draft",
    department: faq.department || "", tags: faq.tags?.slice() || [],
    similar_questions: faq.similar_questions?.slice() || [],
    effective_start: faq.effective_start || "",
    effective_end: faq.effective_end || "",
  };
  editVisible.value = true;
}

async function saveEdit() {
  saving.value = true;
  const { id, question, answer, category_id, scope, status, department, tags, similar_questions, effective_start, effective_end } = editForm.value;
  await updateFAQ(id, { question, answer, category_id, scope, status, department, tags, similar_questions, effective_start: effective_start || undefined, effective_end: effective_end || undefined });
  editVisible.value = false;
  await loadFAQs();
  ElMessage.success("FAQ 已更新");
  saving.value = false;
}

async function toggleStatus(faq: FAQ) {
  const newStatus = faq.status === "online" ? "offline" : "online";
  await updateFAQ(faq.id, { status: newStatus });
  await loadFAQs();
  ElMessage.success(`已${newStatus === "online" ? "上" : "下"}线`);
}

async function submitReview(id: number) {
  try {
    await submitForReview(id);
    await loadFAQs();
    ElMessage.success("已提交审核");
  } catch (e: any) { ElMessage.error(e.message || "提交失败"); }
}

async function handleApprove(id: number) {
  try {
    await approveFAQ(id);
    await loadFAQs();
    ElMessage.success("审核通过");
  } catch (e: any) { ElMessage.error(e.message || "操作失败"); }
}

async function handleReject(id: number) {
  try {
    const { value } = await ElMessageBox.prompt("请输入驳回原因（选填）", "驳回 FAQ", {
      confirmButtonText: "确认驳回", cancelButtonText: "取消", inputPlaceholder: "驳回原因...",
    });
    await rejectFAQ(id, value || undefined);
    await loadFAQs();
    ElMessage.success("已驳回");
  } catch { /* cancelled */ }
}

async function openVersions(faq: FAQ) {
  versionFaqId.value = faq.id;
  versionVisible.value = true;
  versionLoading.value = true;
  try {
    versions.value = await getFAQVersions(faq.id);
  } catch {
    versions.value = [];
  }
  versionLoading.value = false;
}

async function handleRollback(versionId: number) {
  try {
    await ElMessageBox.confirm("确定回滚到此版本？当前内容将被保存为历史版本。", "确认回滚", { type: "warning" });
    await rollbackFAQ(versionFaqId.value, versionId);
    versionVisible.value = false;
    await loadFAQs();
    ElMessage.success("已回滚");
  } catch { /* cancelled */ }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该 FAQ？", "确认删除", { type: "warning" });
    await deleteFAQ(id);
    await loadFAQs();
    ElMessage.success("已删除");
  } catch { /* cancelled */ }
}

async function showTagInput() {
  tagInputVisible.value = true;
  await nextTick();
  tagInputRef.value?.focus();
}

function addTag() {
  if (newTag.value.trim()) {
    editForm.value.tags.push(newTag.value.trim());
    newTag.value = "";
  }
  tagInputVisible.value = false;
}

function addSimilar() {
  if (newSimilar.value.trim()) {
    editForm.value.similar_questions.push(newSimilar.value.trim());
    newSimilar.value = "";
  }
}

async function handleBulkImport() {
  const lines = importText.value.split("\n").filter(l => l.trim());
  const items = lines.map(l => {
    const parts = l.split("|");
    return { category_id: 1, question: (parts[0] || "").trim(), answer: (parts[1] || "").trim() };
  }).filter(i => i.question && i.answer);

  if (items.length === 0) { ElMessage.warning("未解析到有效的 FAQ"); return; }

  importing.value = true;
  try {
    const result = await bulkImportFAQ(items);
    importVisible.value = false;
    importText.value = "";
    await loadFAQs();
    ElMessage.success(`成功导入 ${result.imported} 条 FAQ`);
  } catch {
    ElMessage.error("导入失败");
  }
  importing.value = false;
}

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 个 FAQ？`, "批量删除", { type: "warning" });
    const result = await batchDeleteFAQs(selectedIds.value);
    if (result.failed.length > 0) {
      ElMessage.warning(`成功 ${result.deleted} 个，失败 ${result.failed.length} 个`);
    } else {
      ElMessage.success(`已删除 ${result.deleted} 个 FAQ`);
    }
    selectedIds.value = [];
    await loadFAQs();
  } catch { /* cancelled */ }
}

onMounted(async () => {
  await loadCategories();
  await loadFAQs();
});
</script>
