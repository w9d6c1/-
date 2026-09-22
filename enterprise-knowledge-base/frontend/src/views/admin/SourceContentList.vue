<template>
  <div>
    <el-card style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>多源内容管理</span>
          <el-button type="primary" size="small" @click="openSyncPanel">同步管理</el-button>
        </div>
      </template>
      <el-space fill :size="12" style="flex-wrap: wrap">
        <el-select v-model="filterSourceType" placeholder="来源平台" clearable style="width: 150px" @change="loadList">
          <el-option label="微信公众号" value="wechat" />
          <el-option label="头条号" value="toutiao" />
          <el-option label="知乎" value="zhihu" />
          <el-option label="B站" value="bilibili" />
          <el-option label="官方网站" value="official_website" />
        </el-select>
        <el-select v-model="filterStatus" placeholder="状态" clearable style="width: 120px" @change="loadList">
          <el-option label="在线" value="online" />
          <el-option label="下线" value="offline" />
        </el-select>
        <el-input
          v-model="filterSearch"
          placeholder="搜索标题..."
          clearable
          style="width: 240px"
          @clear="loadList"
          @keyup.enter="loadList"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :icon="Search" @click="loadList">搜索</el-button>
      </el-space>
    </el-card>

    <el-card>
      <template #header><span>内容列表（共 {{ total }} 条）</span></template>

      <el-table :data="items" stripe v-loading="loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="来源平台" width="120">
          <template #default="{ row }">
            <el-tag :type="platformTagType(row.source_type)" size="small">
              {{ platformLabel(row.source_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源名称" width="120">
          <template #default="{ row }">
            <span v-if="row.source_name">{{ row.source_name }}</span>
            <span v-else style="color: #bbb">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : 'warning'" size="small">
              {{ row.status === 'online' ? '在线' : '下线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="160">
          <template #default="{ row }">
            {{ row.publish_time ? new Date(row.publish_time).toLocaleDateString() : '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="word_count" label="字数" width="70" />
        <el-table-column prop="chunk_count" label="分块" width="60" />
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              size="small"
              :type="row.status === 'online' ? 'warning' : 'success'"
              :loading="togglingId === row.id"
              @click="handleToggleStatus(row)"
            >
              {{ row.status === 'online' ? '下线' : '上线' }}
            </el-button>
            <el-button size="small" type="info" @click="openMerge(row.id)">合并</el-button>
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
        @current-change="loadList"
        @size-change="handleSizeChange"
        background
        style="margin-top: 16px; justify-content: flex-end"
      />

      <div v-if="selectedIds.length > 0" style="margin-top: 12px">
        <el-button type="danger" @click="handleBatchStatus('offline')">
          批量下线 ({{ selectedIds.length }})
        </el-button>
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" :title="`详情 — ${detailItem?.title}`" width="750px">
      <template v-if="detailItem">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="ID">{{ detailItem.id }}</el-descriptions-item>
          <el-descriptions-item label="来源平台">
            <el-tag :type="platformTagType(detailItem.source_type)" size="small">
              {{ platformLabel(detailItem.source_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detailItem.title }}</el-descriptions-item>
          <el-descriptions-item label="来源名称">
            {{ detailItem.source_name || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="detailItem.status === 'online' ? 'success' : 'warning'" size="small">
              {{ detailItem.status === 'online' ? '在线' : '下线' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="原始链接" :span="2">
            <a v-if="detailItem.original_url" :href="detailItem.original_url" target="_blank" rel="noopener noreferrer">
              {{ detailItem.original_url }}
            </a>
            <el-button
              v-else-if="draftLinkOf(detailItem)"
              type="primary"
              link
              :loading="resolvingPreview"
              @click="openPreview(detailItem.id)"
            >
              打开草稿预览（实时解析微信链接）
            </el-button>
            <span v-else style="color: #bbb">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="发布时间">
            {{ detailItem.publish_time ? new Date(detailItem.publish_time).toLocaleString() : '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="字数">{{ detailItem.word_count }}</el-descriptions-item>
          <el-descriptions-item label="分块数">{{ detailItem.chunk_count }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ new Date(detailItem.created_at).toLocaleString() }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ new Date(detailItem.updated_at).toLocaleString() }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detailItem.source_links && detailItem.source_links.length > 0" style="margin-top: 20px">
          <h4 style="margin-bottom: 10px">来源链接 ({{ detailItem.source_links.length }})</h4>
          <el-table :data="detailItem.source_links" stripe size="small">
            <el-table-column prop="platform" label="平台" width="100">
              <template #default="{ row: link }">
                {{ platformLabel(link.platform) }}
              </template>
            </el-table-column>
            <el-table-column prop="external_id" label="外部ID" width="180" show-overflow-tooltip />
            <el-table-column label="来源名称" width="120">
              <template #default="{ row: link }">
                {{ link.source_name || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="发布时间" width="160">
              <template #default="{ row: link }">
                {{ link.publish_time ? new Date(link.publish_time).toLocaleDateString() : '—' }}
              </template>
            </el-table-column>
            <el-table-column label="主源" width="70">
              <template #default="{ row: link }">
                <el-tag v-if="link.is_primary" type="success" size="small">是</el-tag>
                <span v-else style="color: #bbb">否</span>
              </template>
            </el-table-column>
            <el-table-column label="链接" min-width="180">
              <template #default="{ row: link }">
                <a v-if="link.original_url" :href="link.original_url" target="_blank" rel="noopener noreferrer" style="font-size:12px">
                  查看原文
                </a>
                <el-button
                  v-else-if="link.platform === 'wechat' && link.external_id.startsWith('draft:')"
                  type="primary"
                  link
                  size="small"
                  :loading="resolvingPreview"
                  @click="openPreview(detailItem!.id)"
                >
                  查看原文
                </el-button>
                <span v-else style="color: #bbb">—</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mergeVisible" title="合并重复文档" width="500px">
      <el-form label-width="110px">
        <el-form-item label="主文档 ID">
          <el-input-number v-model="mergePrimaryId" :min="1" placeholder="保留的主文档" style="width: 100%" />
        </el-form-item>
        <el-form-item label="重复文档 ID">
          <el-input-number v-model="mergeDuplicateId" :min="1" placeholder="将被删除的重复文档" style="width: 100%" />
        </el-form-item>
      </el-form>
      <div style="color: #909399; font-size: 13px; margin-bottom: 12px">
        合并后，重复文档将被删除，其来源链接将迁移到主文档。
      </div>
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="primary" :loading="merging" :disabled="!mergePrimaryId || !mergeDuplicateId || mergePrimaryId === mergeDuplicateId" @click="handleMerge">
          确认合并
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="syncVisible" title="同步管理" size="650px">
      <div style="margin-bottom: 16px">
        <el-button type="primary" :loading="syncing" @click="handleTriggerSync">
          触发全平台同步
        </el-button>
      </div>

      <h4 style="margin-bottom: 10px">同步状态</h4>
      <div style="display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px">
        <el-card
          v-for="s in syncStates"
          :key="s.platform"
          shadow="hover"
          style="width: 180px"
        >
          <div style="font-weight: 600; margin-bottom: 6px">{{ platformLabel(s.platform) }}</div>
          <div style="font-size: 12px; color: #909399">
            <el-tag
              :type="s.last_status === 'success' ? 'success' : s.last_status === 'failed' ? 'danger' : 'info'"
              size="small"
            >
              {{ s.last_status }}
            </el-tag>
          </div>
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            {{ s.last_sync_at ? new Date(s.last_sync_at).toLocaleString() : '从未同步' }}
          </div>
          <div v-if="s.last_error" style="font-size: 11px; color: #f56c6c; margin-top: 4px; word-break: break-all">
            {{ s.last_error }}
          </div>
        </el-card>
        <el-empty v-if="syncStates.length === 0" description="暂无同步记录" :image-size="60" />
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px">
        <el-space :size="8">
          <h4 style="margin: 0">同步日志</h4>
          <el-select v-model="logPlatformFilter" placeholder="按平台筛选" clearable size="small" style="width: 130px" @change="handleLogPlatformChange">
            <el-option label="微信公众号" value="wechat" />
            <el-option label="头条号" value="toutiao" />
            <el-option label="知乎" value="zhihu" />
            <el-option label="B站" value="bilibili" />
            <el-option label="官方网站" value="official_website" />
          </el-select>
        </el-space>
        <el-button size="small" @click="exportSyncLogs">导出 CSV</el-button>
      </div>
      <el-table :data="syncLogs" stripe size="small" v-loading="loadingLogs">
        <el-table-column prop="id" label="ID" width="50" />
        <el-table-column label="平台" width="100">
          <template #default="{ row }">{{ platformLabel(row.platform) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="150">
          <template #default="{ row }">{{ new Date(row.started_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'running' ? 'warning' : 'danger'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="fetched_count" label="获取" width="60" />
        <el-table-column prop="ingested_count" label="入库" width="60" />
        <el-table-column prop="duplicated_count" label="去重" width="60" />
        <el-table-column label="错误" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error" style="color: #f56c6c; font-size: 12px">{{ row.error }}</span>
            <span v-else style="color: #bbb">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="logPage"
        :page-size="logPageSize"
        :total="logTotal"
        layout="prev, pager, next"
        size="small"
        @current-change="loadSyncLogs"
        style="margin-top: 10px; justify-content: center"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import {
  fetchSourceContents,
  fetchSourceContentDetail,
  updateSourceContentStatus,
  deleteSourceContent,
  mergeSourceContents,
  triggerSync as apiTriggerSync,
  fetchSyncStates,
  fetchSyncLogs,
  fetchPreviewUrl,
  type SourceContent,
  type SourceContentDetail,
  type SourceLink,
  type SyncState,
  type SyncLog,
} from "@/api/sourceContent";

const PLATFORM_LABELS: Record<string, string> = {
  wechat: "微信公众号",
  toutiao: "头条号",
  zhihu: "知乎",
  bilibili: "B站",
  official_website: "官方网站",
};

function platformLabel(type: string): string {
  return PLATFORM_LABELS[type] || type || "未知";
}

function platformTagType(type: string): "" | "success" | "warning" | "info" | "danger" {
  const map: Record<string, "" | "success" | "warning" | "info" | "danger"> = {
    wechat: "success",
    toutiao: "",
    zhihu: "",
    bilibili: "danger",
    official_website: "warning",
  };
  return map[type] || "info";
}

const items = ref<SourceContent[]>([]);
const loading = ref(false);
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);

const filterSourceType = ref("");
const filterStatus = ref("");
const filterSearch = ref("");

const selectedIds = ref<number[]>([]);
const togglingId = ref<number | null>(null);

const detailVisible = ref(false);
const detailItem = ref<SourceContentDetail | null>(null);
const resolvingPreview = ref(false);

function draftLinkOf(item: SourceContentDetail | null): SourceLink | null {
  if (!item?.source_links) return null;
  return (
    item.source_links.find(
      (l) => l.platform === "wechat" && l.external_id.startsWith("draft:"),
    ) ?? null
  );
}

async function openPreview(docId: number) {
  resolvingPreview.value = true;
  try {
    const url = await fetchPreviewUrl(docId);
    window.open(url, "_blank", "noopener");
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "获取预览链接失败");
  } finally {
    resolvingPreview.value = false;
  }
}

const mergeVisible = ref(false);
const mergePrimaryId = ref<number | null>(null);
const mergeDuplicateId = ref<number | null>(null);
const merging = ref(false);

const syncVisible = ref(false);
const syncStates = ref<SyncState[]>([]);
const syncLogs = ref<SyncLog[]>([]);
const loadingLogs = ref(false);
const syncing = ref(false);
const logPage = ref(1);
const logPageSize = ref(10);
const logTotal = ref(0);
const logPlatformFilter = ref("");

function handleSelectionChange(rows: SourceContent[]) {
  selectedIds.value = rows.map((r) => r.id);
}

async function loadList() {
  loading.value = true;
  try {
    const res = await fetchSourceContents({
      page: currentPage.value,
      page_size: pageSize.value,
      source_type: filterSourceType.value || undefined,
      status: filterStatus.value || undefined,
      search: filterSearch.value || undefined,
    });
    items.value = res.items;
    total.value = res.total;
  } catch (e: any) {
    ElMessage.error(e.message || "加载列表失败");
  } finally {
    loading.value = false;
  }
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadList();
}

async function handleToggleStatus(row: SourceContent) {
  const newStatus = row.status === "online" ? "offline" : "online";
  const action = newStatus === "online" ? "上线" : "下线";
  try {
    await ElMessageBox.confirm(`确定将该文档${action}？`, "确认操作", { type: "info" });
    togglingId.value = row.id;
    const updated = await updateSourceContentStatus(row.id, newStatus);
    const idx = items.value.findIndex((d) => d.id === row.id);
    if (idx !== -1) items.value[idx] = updated;
    ElMessage.success(`已${action}`);
  } catch {
    // cancelled
  }
  togglingId.value = null;
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该来源内容？删除后将同时移除切块和索引。", "确认删除", { type: "warning" });
    await deleteSourceContent(id);
    items.value = items.value.filter((d) => d.id !== id);
    total.value -= 1;
    if (items.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1;
      await loadList();
    }
    ElMessage.success("已删除");
  } catch {
    // cancelled
  }
}

async function handleBatchStatus(status: "offline") {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确定将选中的 ${selectedIds.value.length} 个文档批量下线？`, "批量操作", { type: "warning" });
    for (const id of selectedIds.value) {
      await updateSourceContentStatus(id, status);
    }
    ElMessage.success(`已下线 ${selectedIds.value.length} 个文档`);
    selectedIds.value = [];
    await loadList();
  } catch {
    // cancelled
  }
}

async function openDetail(row: SourceContent) {
  try {
    detailItem.value = await fetchSourceContentDetail(row.id);
    detailVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e.message || "获取详情失败");
  }
}

function openMerge(duplicateId: number) {
  mergePrimaryId.value = null;
  mergeDuplicateId.value = duplicateId;
  mergeVisible.value = true;
}

async function handleMerge() {
  if (!mergePrimaryId.value || !mergeDuplicateId.value) return;
  merging.value = true;
  try {
    await mergeSourceContents(mergePrimaryId.value, mergeDuplicateId.value);
    ElMessage.success("合并完成");
    mergeVisible.value = false;
    mergePrimaryId.value = null;
    mergeDuplicateId.value = null;
    await loadList();
  } catch (e: any) {
    ElMessage.error(e.message || "合并失败");
  }
  merging.value = false;
}

async function openSyncPanel() {
  syncVisible.value = true;
  await Promise.all([loadSyncStates(), loadSyncLogs()]);
}

async function loadSyncStates() {
  try {
    syncStates.value = await fetchSyncStates();
  } catch {
    // ignore
  }
}

async function loadSyncLogs() {
  loadingLogs.value = true;
  try {
    const res = await fetchSyncLogs(logPlatformFilter.value || undefined, logPage.value, logPageSize.value);
    syncLogs.value = res.items;
    logTotal.value = res.total;
  } catch {
    // ignore
  }
  loadingLogs.value = false;
}

function handleLogPlatformChange() {
  logPage.value = 1;
  loadSyncLogs();
}

function exportSyncLogs() {
  if (syncLogs.value.length === 0) {
    ElMessage.warning("无日志可导出");
    return;
  }
  const headers = ["ID", "平台", "开始时间", "结束时间", "获取数", "入库数", "去重数", "状态", "错误"];
  const rows = syncLogs.value.map((l) => [
    l.id,
    platformLabel(l.platform),
    l.started_at,
    l.finished_at || "",
    l.fetched_count,
    l.ingested_count,
    l.duplicated_count,
    l.status,
    l.error || "",
  ]);
  const csv = [headers, ...rows]
    .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const bom = "\uFEFF";
  const blob = new Blob([bom + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sync_logs_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  ElMessage.success("导出成功");
}

async function handleTriggerSync() {
  syncing.value = true;
  try {
    const result = await apiTriggerSync();
    if (result.all_ok) {
      ElMessage.success(`同步完成：获取 ${result.total_fetched} 条，入库 ${result.total_ingested} 条`);
    } else {
      ElMessage.warning(
        `同步部分成功：获取 ${result.total_fetched} 条，入库 ${result.total_ingested} 条，失败平台: ${result.failed_platforms.join(", ")}`,
      );
    }
    await Promise.all([loadSyncStates(), loadSyncLogs(), loadList()]);
  } catch (e: any) {
    ElMessage.error(e.message || "同步失败");
  }
  syncing.value = false;
}

onMounted(() => {
  loadList();
});
</script>
