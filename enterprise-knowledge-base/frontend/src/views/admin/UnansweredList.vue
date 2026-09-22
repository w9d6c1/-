<template>
  <div>
    <el-card>
      <template #header>
        <el-space>
          <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 130px" @change="fetchList">
            <el-option label="全部" value="" />
            <el-option label="待处理" value="pending" />
            <el-option label="已转换" value="converted" />
            <el-option label="已忽略" value="ignored" />
          </el-select>
          <el-select v-model="filterSource" placeholder="来源" clearable style="width: 130px" @change="fetchList">
            <el-option label="全部" value="" />
            <el-option label="客服" value="customer" />
            <el-option label="内部" value="internal" />
          </el-select>
        </el-space>
      </template>

      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="question" label="问题" min-width="250" show-overflow-tooltip />
        <el-table-column prop="source" label="来源" width="80">
          <template #default="{ row }">{{ row.source === 'customer' ? '客服' : '内部' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="warning">待处理</el-tag>
            <el-tag v-else-if="row.status === 'converted'" type="success">已转换</el-tag>
            <el-tag v-else-if="row.status === 'ignored'" type="info">已忽略</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'pending'" size="small" type="primary" @click="handleConvert(row)" :loading="convertingId === row.id">转为FAQ</el-button>
            <el-button v-if="row.status === 'pending'" size="small" @click="handleIgnore(row)">忽略</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="convertDialogVisible" title="生成FAQ草稿" width="600px">
      <p><strong>问题：</strong>{{ convertQuestion }}</p>
      <p><strong>AI生成答案：</strong></p>
      <el-input v-model="convertAnswer" type="textarea" :rows="6" readonly />
      <template #footer>
        <el-button @click="convertDialogVisible = false">关闭</el-button>
        <el-tag v-if="convertFaqId" type="success">已创建 FAQ #{{ convertFaqId }}</el-tag>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getToken } from "@/stores/auth";

const BASE = "/api/admin";
function h() { return { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" }; }

const list = ref<any[]>([]);
const filterStatus = ref("");
const filterSource = ref("");
const loading = ref(false);
const convertingId = ref<number | null>(null);
const convertDialogVisible = ref(false);
const convertQuestion = ref("");
const convertAnswer = ref("");
const convertFaqId = ref<number | null>(null);

async function fetchList() {
  loading.value = true;
  const params = new URLSearchParams();
  if (filterStatus.value) params.set("status", filterStatus.value);
  if (filterSource.value) params.set("source", filterSource.value);
  const resp = await fetch(`${BASE}/unanswered?${params}`, { headers: h() });
  list.value = await resp.json();
  loading.value = false;
}

async function handleConvert(row: any) {
  convertingId.value = row.id;
  const resp = await fetch(`${BASE}/unanswered/${row.id}/convert`, { method: "POST", headers: h() });
  const data = await resp.json();
  convertQuestion.value = data.question;
  convertAnswer.value = data.generated_answer;
  convertFaqId.value = data.faq_id;
  convertDialogVisible.value = true;
  convertingId.value = null;
  fetchList();
}

async function handleIgnore(row: any) {
  await fetch(`${BASE}/unanswered/${row.id}`, {
    method: "PATCH", headers: h(), body: JSON.stringify({ status: "ignored" }),
  });
  fetchList();
}

onMounted(fetchList);
</script>
