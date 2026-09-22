<template>
  <div>
    <!-- 创建表单 -->
    <el-card style="margin-bottom: 16px">
      <template #header><span>新建文档</span></template>
      <el-space fill alignment="start" style="flex-wrap: wrap" :size="12">
        <el-input v-model="form.title" :placeholder="selectedFileName ? '标题（默认用文件名）' : '文档标题'" style="width: 260px" />
        <el-select v-model="form.category_id" placeholder="选择分类" style="width: 180px">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="form.scope" style="width: 120px">
          <el-option label="公共" value="public" />
          <el-option label="客服" value="customer" />
          <el-option label="内部" value="internal" />
        </el-select>
        <el-select
          v-if="form.scope === 'internal'"
          v-model="form.department"
          :disabled="deptLocked"
          filterable
          allow-create
          default-first-option
          clearable
          placeholder="所属部门（可留空=通用）"
          style="width: 200px"
        >
          <el-option v-for="d in departments" :key="d" :label="d" :value="d" />
        </el-select>
        <el-button @click="showAdvanced = !showAdvanced" text>{{ showAdvanced ? '收起' : '高级选项' }}</el-button>
      </el-space>
      <el-space v-if="showAdvanced" fill :size="12" style="margin-top: 10px">
        <el-select v-model="form.chunk_strategy" style="width: 130px">
          <el-option label="递归分块" value="recursive" />
          <el-option label="固定分块" value="fixed" />
          <el-option label="语义分块" value="semantic" />
        </el-select>
        <el-input v-model.number="form.chunk_size" placeholder="分块大小" style="width: 100px" type="number" />
        <el-input v-model.number="form.chunk_overlap" placeholder="重叠" style="width: 80px" type="number" />
        <el-switch v-model="form.auto_clean" active-text="上传后自动清洗" />
      </el-space>
      <div class="file-upload-row" style="margin-top: 10px">
        <input ref="fileInputRef" type="file" accept=".pdf,.docx,.md,.txt" style="display:none" @change="handleFileSelect" />
        <el-button @click="fileInputRef?.click()" :icon="Upload">
          {{ selectedFileName ? '重新选择文件' : '选择文件（可选）' }}
        </el-button>
        <span v-if="selectedFileName" class="selected-file">{{ selectedFileName }}</span>
        <el-button v-if="selectedFileName" text type="danger" @click="clearFile">移除文件</el-button>
        <span v-else class="upload-hint">不选文件则创建空文档，之后可粘贴内容</span>
      </div>
      <el-button
        type="primary"
        :loading="creating"
        :disabled="creating || !canSubmit"
        @click="handleSubmit"
        style="margin-top: 10px"
      >
        {{ selectedFileName ? '上传并创建' : '创建文档' }}
      </el-button>
    </el-card>

    <!-- 文档列表 -->
    <el-card>
      <template #header><span>文档列表（共 {{ total }} 条）</span></template>
      <div v-if="selectedIds.length > 0" style="margin-bottom:12px">
        <el-button type="primary" :loading="bulkCleaning" @click="handleBulkClean">批量清洗 ({{ selectedIds.length }})</el-button>
        <el-button type="danger" @click="handleBatchDelete">批量删除 ({{ selectedIds.length }})</el-button>
        <el-button @click="selectedIds = []">取消选择</el-button>
      </div>

      <el-table :data="docs" stripe v-loading="loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="分类" width="120">
          <template #default="{ row }">{{ catName(row.category_id) }}</template>
        </el-table-column>
        <el-table-column label="部门" width="100">
          <template #default="{ row }">
            <span v-if="row.department">{{ row.department }}</span>
            <span v-else style="color:#bbb">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="word_count" label="字数" width="70" />
        <el-table-column prop="chunk_count" label="分块" width="60" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status === 'online' ? '在线' : row.status === 'draft' ? '草稿' : '下线' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="review_status" label="审核" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.review_status === 'pending'" type="warning" size="small">待审</el-tag>
            <el-tag v-else-if="row.review_status === 'approved'" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="row.review_status === 'rejected'" type="danger" size="small">{{ row.review_comment ? `驳回: ${row.review_comment}` : '驳回' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="clean_status" label="清洗" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.clean_status === 'cleaned'" type="success" size="small">已清洗</el-tag>
            <el-tag v-else-if="row.clean_status === 'skipped'" type="info" size="small">未清洗</el-tag>
            <el-tag v-else size="small">待处理</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'draft'" size="small" @click="openUpload(row)">上传内容</el-button>
            <el-button v-if="row.word_count && row.word_count > 0" size="small" :loading="cleaningId === row.id" @click="openClean(row)">清洗</el-button>
            <el-button v-if="row.word_count && row.word_count > 0 && row.chunk_count === 0" size="small" type="success" @click="handleChunk(row)">分块</el-button>
            <el-button v-if="row.chunk_count && row.chunk_count > 0" size="small" type="info" @click="openChunks(row)">查看切片</el-button>
            <el-button v-if="row.status === 'online' && row.chunk_count > 0" size="small" type="warning" :loading="syncingId === row.id" @click="handleResync(row)">重新向量化</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[10, 20, 50]"
        @current-change="loadDocs"
        @size-change="handleSizeChange"
        background
        style="margin-top: 16px; justify-content: flex-end"
      />
    </el-card>

      <!-- 上传内容 Dialog -->
      <el-dialog v-model="uploadVisible" :title="`上传文档内容 — 《${uploadTarget?.title}》`" width="700px">
        <el-select v-model="uploadFileType" style="width: 140px; margin-bottom: 12px">
          <el-option label="Markdown" value="md" />
          <el-option label="纯文本" value="txt" />
        </el-select>
        <el-input v-model="uploadContentText" type="textarea" :rows="14" placeholder="在此粘贴文档内容..." />
        <template #footer>
          <el-button @click="uploadVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!uploadContentText.trim()" :loading="uploading" @click="handleUpload">上传内容</el-button>
        </template>
      </el-dialog>

      <!-- 查看切片 Dialog -->
      <el-dialog v-model="chunkVisible" :title="`切片列表 — 《${chunkDoc?.title}》（共 ${chunks.length} 块）`" width="900px">
        <el-table :data="chunks" stripe v-loading="loadingChunks" max-height="500">
          <el-table-column prop="chunk_index" label="序号" width="70" align="center" />
          <el-table-column prop="content" label="切片内容" min-width="400" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="white-space: pre-wrap; word-break: break-all">{{ row.content }}</span>
            </template>
          </el-table-column>
          <el-table-column label="向量同步" width="130" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.vector_id" type="success" size="small">已同步</el-tag>
              <el-tag v-else type="info" size="small">未同步</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="BM25同步" width="130" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.bm25_id" type="success" size="small">已同步</el-tag>
              <el-tag v-else type="info" size="small">未同步</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="last_sync_at" label="最后同步" width="170">
            <template #default="{ row }">{{ row.last_sync_at ? new Date(row.last_sync_at).toLocaleString() : '-' }}</template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="chunkVisible = false">关闭</el-button>
        </template>
      </el-dialog>

      <!-- 清洗优化 Dialog -->
      <el-dialog v-model="cleanVisible" :title="`清洗优化 — 《${cleanTarget?.title}》`" width="560px">
        <p style="color:#666;line-height:1.7">
          规则清洗：移除页标记/占位行、合并断行碎片、规范空白（即时、免费）。<br />
          LLM 增强：对表格结构和多字碎片做语义级重建（较慢，需配置 LLM）。
        </p>
        <el-switch v-model="cleanUseLlm" active-text="使用 LLM 增强" style="margin-bottom: 12px" />
        <el-descriptions v-if="cleanReport" :column="2" border size="small" style="margin-top: 8px">
          <el-descriptions-item label="清洗前字数">{{ cleanReport.original_chars }}</el-descriptions-item>
          <el-descriptions-item label="清洗后字数">{{ cleanReport.cleaned_chars }}</el-descriptions-item>
          <el-descriptions-item label="移除页标记">{{ cleanReport.removed_page_markers }}</el-descriptions-item>
          <el-descriptions-item label="移除占位行">{{ cleanReport.removed_placeholders }}</el-descriptions-item>
          <el-descriptions-item label="合并碎片">{{ cleanReport.merged_fragments }}</el-descriptions-item>
          <el-descriptions-item label="LLM 增强">{{ cleanReport.llm_enhanced ? '是' : '否' }}</el-descriptions-item>
        </el-descriptions>
        <template #footer>
          <el-button @click="cleanVisible = false">关闭</el-button>
          <el-button type="primary" :loading="cleaning" @click="handleClean">
            {{ cleanReport ? '重新清洗' : '执行清洗' }}
          </el-button>
        </template>
      </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import { getToken, getUserRole, getUserDepartment } from "@/stores/auth";
import {
  fetchDocuments,
  createDocument,
  uploadContent as uploadDocContent,
  uploadFile,
  validateFile,
  chunkDocument,
  deleteDocument,
  batchDeleteDocuments,
  fetchChunks,
  resyncDocument,
  fetchDepartments,
  cleanDocument,
  bulkCleanDocuments,
  type Document,
  type Chunk,
  type CleanReport,
} from "@/api/document";

const BASE = "/api/admin";
function h() { return { Authorization: `Bearer ${getToken()}` }; }

interface Category { id: number; name: string; }

const docs = ref<Document[]>([]);
const categories = ref<Category[]>([]);
const departments = ref<string[]>([]);
const loading = ref(false);
const creating = ref(false);
const showAdvanced = ref(false);

const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

const form = ref({
  title: "",
  category_id: 0 as unknown as number,
  scope: "public",
  department: "" as string,
  chunk_strategy: "recursive",
  chunk_size: 512,
  chunk_overlap: 80,
  auto_clean: true,
});

const deptLocked = computed(() => {
  const role = getUserRole();
  const dept = getUserDepartment();
  return role !== "superadmin" && !!dept;
});

const canSubmit = computed(() => {
  if (!form.value.title || !form.value.category_id) return false;
  if (!selectedFileName.value && !form.value.title.trim()) return false;
  return true;
});

const uploadVisible = ref(false);
const uploadTarget = ref<Document | null>(null);
const uploadContentText = ref("");
const uploadFileType = ref("md");
const uploading = ref(false);

const fileInputRef = ref<HTMLInputElement | null>(null);
const selectedFile = ref<File | null>(null);
const selectedFileName = ref("");

const chunkVisible = ref(false);
const chunkDoc = ref<Document | null>(null);
const chunks = ref<Chunk[]>([]);
const loadingChunks = ref(false);
const syncingId = ref<number | null>(null);
const selectedIds = ref<number[]>([]);

const cleanVisible = ref(false);
const cleanTarget = ref<Document | null>(null);
const cleanUseLlm = ref(false);
const cleaning = ref(false);
const cleaningId = ref<number | null>(null);
const cleanReport = ref<CleanReport | null>(null);
const bulkCleaning = ref(false);

function openClean(doc: Document) {
  cleanTarget.value = doc;
  cleanUseLlm.value = false;
  cleanReport.value = null;
  cleanVisible.value = true;
}

async function handleClean() {
  if (!cleanTarget.value) return;
  cleaning.value = true;
  cleaningId.value = cleanTarget.value.id;
  try {
    const resp = await cleanDocument(cleanTarget.value.id, cleanUseLlm.value);
    cleanReport.value = resp.report;
    const idx = docs.value.findIndex(d => d.id === resp.id);
    if (idx !== -1) docs.value[idx] = { ...docs.value[idx], clean_status: resp.clean_status, word_count: resp.word_count, chunk_count: resp.chunk_count };
    ElMessage.success(resp.report.llm_enhanced ? "LLM 清洗完成" : "清洗完成");
  } catch (e: any) {
    ElMessage.error(e.message || "清洗失败");
  } finally {
    cleaning.value = false;
    cleaningId.value = null;
  }
}

async function handleBulkClean() {
  if (selectedIds.value.length === 0) return;
  bulkCleaning.value = true;
  try {
    const resp = await bulkCleanDocuments(selectedIds.value, false);
    if (resp.failed.length > 0) {
      ElMessage.warning(`清洗完成：成功 ${resp.cleaned}，失败 ${resp.failed.length}`);
    } else {
      ElMessage.success(`批量清洗完成（${resp.cleaned} 篇）`);
    }
    selectedIds.value = [];
    await loadDocs();
  } catch {
    ElMessage.error("批量清洗失败");
  } finally {
    bulkCleaning.value = false;
  }
}

function handleSelectionChange(rows: Document[]) {
  selectedIds.value = rows.map(r => r.id);
}

function catName(id: number) {
  return categories.value.find(c => c.id === id)?.name || `#${id}`;
}

function statusType(s: string) {
  if (s === "online") return "success";
  if (s === "offline") return "warning";
  return "info";
}

async function loadCategories() {
  try {
    const resp = await fetch(`${BASE}/categories?page_size=500`, { headers: h() });
    if (resp.ok) {
      const data = await resp.json();
      categories.value = data.items || data;
    }
  } catch { /* ignore */ }
}

async function loadDepartments() {
  try {
    departments.value = await fetchDepartments();
  } catch { /* ignore */ }
}

function initFormDepartment() {
  const role = getUserRole();
  const dept = getUserDepartment();
  if (role !== "superadmin" && dept) {
    form.value.department = dept;
  }
}

async function loadDocs() {
  loading.value = true;
  try {
    const res = await fetchDocuments({
      page: currentPage.value,
      page_size: pageSize.value,
    });
    docs.value = res.items;
    total.value = res.total;
  } catch {
    ElMessage.error("加载文档失败");
  } finally {
    loading.value = false;
  }
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadDocs();
}

function clearFile() {
  selectedFile.value = null;
  selectedFileName.value = "";
  const inp = fileInputRef.value;
  if (inp) inp.value = "";
}

async function handleSubmit() {
  creating.value = true;
  try {
    if (selectedFile.value) {
      const title = form.value.title.trim() || selectedFileName.value;
      await uploadFile(
        selectedFile.value,
        title,
        form.value.category_id,
        form.value.scope,
        form.value.chunk_strategy,
        form.value.department || undefined,
        form.value.auto_clean,
      );
      clearFile();
    } else {
      await createDocument({
        category_id: form.value.category_id,
        title: form.value.title,
        scope: form.value.scope,
        chunk_strategy: form.value.chunk_strategy,
        chunk_size: form.value.chunk_size,
        chunk_overlap: form.value.chunk_overlap,
        department: form.value.department || undefined,
      });
    }
    form.value.title = "";
    currentPage.value = 1;
    await loadDocs();
    ElMessage.success("文档已创建");
  } catch (e: any) {
    ElMessage.error(e.message || "创建失败");
  }
  creating.value = false;
}

function openUpload(doc: Document) {
  uploadTarget.value = doc;
  uploadContentText.value = "";
  uploadFileType.value = "md";
  uploadVisible.value = true;
}

async function handleUpload() {
  if (!uploadTarget.value || !uploadContentText.value.trim()) return;
  uploading.value = true;
  try {
    const updated = await uploadDocContent(uploadTarget.value.id, uploadContentText.value, uploadFileType.value);
    const idx = docs.value.findIndex(d => d.id === updated.id);
    if (idx !== -1) docs.value[idx] = updated;
    uploadVisible.value = false;
    uploadTarget.value = null;
    ElMessage.success("内容已上传");
  } catch {
    ElMessage.error("上传失败");
  }
  uploading.value = false;
}

async function handleChunk(doc: Document) {
  try {
    await ElMessageBox.confirm(`确定对「${doc.title}」执行分块？\n策略: ${doc.chunk_strategy || 'recursive'}\n分块后系统将自动索引`, "确认分块", { type: "info" });
    const result = await chunkDocument(doc.id);
    const idx = docs.value.findIndex(d => d.id === doc.id);
    if (idx !== -1) docs.value[idx] = { ...docs.value[idx], chunk_count: result.chunk_count };
    ElMessage.success(`分块完成，共 ${result.chunk_count} 块`);
  } catch { /* cancelled */ }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该文档？", "确认删除", { type: "warning" });
    await deleteDocument(id);
    docs.value = docs.value.filter(d => d.id !== id);
    total.value -= 1;
    if (docs.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1;
      await loadDocs();
    }
    ElMessage.success("已删除");
  } catch { /* cancelled */ }
}

async function openChunks(doc: Document) {
  chunkDoc.value = doc;
  chunkVisible.value = true;
  loadingChunks.value = true;
  try {
    chunks.value = await fetchChunks(doc.id);
  } catch {
    ElMessage.error("获取切片列表失败");
  }
  loadingChunks.value = false;
}

async function handleResync(doc: Document) {
  try {
    await ElMessageBox.confirm(
      `确定重新向量化「${doc.title}」？将重新生成嵌入向量并同步到 Milvus 与 Elasticsearch。`,
      "确认重新向量化",
      { type: "info" },
    );
    syncingId.value = doc.id;
    const result = await resyncDocument(doc.id);
    ElMessage.success(`重新向量化完成，已同步 ${result.synced} 条记录`);
  } catch { /* cancelled */ }
  syncingId.value = null;
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  const err = validateFile(file);
  if (err) { ElMessage.error(err); return; }
  selectedFile.value = file;
  selectedFileName.value = file.name;
  if (!form.value.title.trim()) {
    form.value.title = file.name;
  }
}

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 个文档？`, "批量删除", { type: "warning" });
    const result = await batchDeleteDocuments(selectedIds.value);
    if (result.failed.length > 0) {
      ElMessage.warning(`成功 ${result.deleted} 个，失败 ${result.failed.length} 个`);
    } else {
      ElMessage.success(`已删除 ${result.deleted} 个文档`);
    }
    selectedIds.value = [];
    currentPage.value = 1;
    await loadDocs();
  } catch { /* cancelled */ }
}

onMounted(async () => {
  initFormDepartment();
  await Promise.all([loadCategories(), loadDepartments(), loadDocs()]);
});
</script>

<style scoped>
.file-upload-row {
  display: flex;
  align-items: center;
  margin-top: 4px;
}
.selected-file {
  margin-left: 10px;
  color: #409eff;
  font-size: 13px;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
