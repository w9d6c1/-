<template>
  <div>
    <el-card>
      <template #header>
        <el-space>
          <span>操作日志</span>
          <el-button size="small" type="primary" @click="exportCSV">导出 CSV</el-button>
        </el-space>
      </template>

      <el-form :inline="true" style="margin-bottom: 16px">
        <el-form-item label="操作人">
          <el-input v-model="filters.operator_name" placeholder="输入操作人" clearable style="width: 160px" @change="search" />
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="filters.operation_type" clearable style="width: 120px" @change="search">
            <el-option label="新增" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标表">
          <el-select v-model="filters.target_table" clearable style="width: 150px" @change="search">
            <el-option label="文档" value="knowledge_doc" />
            <el-option label="FAQ" value="knowledge_faq" />
            <el-option label="分类" value="knowledge_category" />
            <el-option label="同义词" value="synonym" />
            <el-option label="敏感词" value="sensitive_word" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 250px"
            @change="search"
          />
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="items" stripe v-loading="loading" max-height="600">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="operator_name" label="操作人" width="110" />
        <el-table-column label="操作类型" width="80">
          <template #default="{ row }">
            <el-tag :type="opTypeTag(row.operation_type)" size="small">{{ opTypeLabel(row.operation_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标" width="160">
          <template #default="{ row }">{{ targetLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="操作前" min-width="150">
          <template #default="{ row }">
            <span v-if="row.content_before" style="font-size: 12px; color: #909399">{{ formatJson(row.content_before) }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作后" min-width="150">
          <template #default="{ row }">
            <span v-if="row.content_after" style="font-size: 12px; color: #606266">{{ formatJson(row.content_after) }}</span>
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[10, 20, 50, 100]"
        @current-change="loadData"
        @size-change="handleSizeChange"
        background
        style="margin-top: 16px; justify-content: flex-end"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { fetchOperations, exportOperationsUrl, type OperationLog } from "@/api/audit";
import { getToken } from "@/stores/auth";

const loading = ref(false);
const items = ref<OperationLog[]>([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);

const filters = ref({
  operator_name: "",
  operation_type: "",
  target_table: "",
});

const dateRange = ref<[string, string] | null>(null);

function opTypeTag(t: string) {
  if (t === "create") return "success";
  if (t === "update") return "warning";
  if (t === "delete") return "danger";
  return "info";
}

function opTypeLabel(t: string) {
  if (t === "create") return "新增";
  if (t === "update") return "更新";
  if (t === "delete") return "删除";
  return t;
}

function targetLabel(row: OperationLog) {
  const tableName: Record<string, string> = {
    knowledge_doc: "文档",
    knowledge_faq: "FAQ",
    knowledge_category: "分类",
    synonym: "同义词",
    sensitive_word: "敏感词",
  };
  const name = tableName[row.target_table] || row.target_table;
  return row.target_id ? `${name} #${row.target_id}` : name;
}

function formatJson(obj: Record<string, unknown>) {
  return JSON.stringify(obj).slice(0, 120) + (JSON.stringify(obj).length > 120 ? "…" : "");
}

const queryParams = () => ({
  page: currentPage.value,
  page_size: pageSize.value,
  operator_name: filters.value.operator_name || undefined,
  operation_type: filters.value.operation_type || undefined,
  target_table: filters.value.target_table || undefined,
  start_date: dateRange.value?.[0] || undefined,
  end_date: dateRange.value?.[1] || undefined,
});

async function loadData() {
  loading.value = true;
  try {
    const res = await fetchOperations(queryParams());
    items.value = res.items;
    total.value = res.total;
  } catch { ElMessage.error("加载失败"); }
  loading.value = false;
}

function search() {
  currentPage.value = 1;
  loadData();
}

function handleSizeChange(size: number) {
  pageSize.value = size;
  currentPage.value = 1;
  loadData();
}

function resetFilters() {
  filters.value = { operator_name: "", operation_type: "", target_table: "" };
  dateRange.value = null;
  currentPage.value = 1;
  loadData();
}

function exportCSV() {
  const url = exportOperationsUrl(queryParams());
  const a = document.createElement("a");
  a.href = url;
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  fetch(url, { headers })
    .then(res => res.blob())
    .then(blob => {
      const objUrl = URL.createObjectURL(blob);
      a.href = objUrl;
      a.download = `operations_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(objUrl);
    })
    .catch(() => ElMessage.error("导出失败"));
}

onMounted(loadData);
</script>
