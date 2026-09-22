<template>
  <div>
    <el-card>
      <h3>权限管理</h3>
      <p style="color: #909399; margin-bottom: 12px">
        配置各角色可访问的知识库范围（public / internal / customer）。
        修改后需点击「重载缓存」使 LangGraph Agent 立即生效。
      </p>

      <el-space style="margin-bottom: 12px">
        <el-input v-model="newRole" placeholder="角色（如 operator）" style="width: 140px" />
        <el-select v-model="newScope" style="width: 120px">
          <el-option label="公共" value="public" />
          <el-option label="内部" value="internal" />
          <el-option label="客服" value="customer" />
        </el-select>
        <el-button type="primary" :disabled="!newRole" @click="handleCreate">新增</el-button>
        <el-button @click="handleCreateDefaults">重置为默认</el-button>
        <el-button type="warning" @click="handleReload">重载缓存</el-button>
      </el-space>

      <el-table :data="permissions" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="role" label="角色" width="140" />
        <el-table-column prop="scope" label="范围" width="100" />
        <el-table-column prop="is_active" label="启用" width="80">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              @change="(val: boolean) => handleToggle(row.id, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  fetchPermissions,
  createPermission,
  updatePermission,
  deletePermission,
  createDefaults,
  reloadCache,
  type ScopePermission,
} from "@/api/permission";
import { ElMessage } from "element-plus";

const permissions = ref<ScopePermission[]>([]);
const newRole = ref("");
const newScope = ref("public");

async function load() {
  permissions.value = await fetchPermissions();
}

async function handleCreate() {
  if (!newRole.value) return;
  try {
    await createPermission({ role: newRole.value, scope: newScope.value });
    newRole.value = "";
    ElMessage.success("权限已添加");
    await load();
  } catch (e: any) {
    ElMessage.error(e.message);
  }
}

async function handleToggle(id: number, val: boolean) {
  await updatePermission(id, { is_active: val });
  await load();
}

async function handleDelete(id: number) {
  await deletePermission(id);
  ElMessage.success("已删除");
  await load();
}

async function handleCreateDefaults() {
  try {
    const result = await createDefaults();
    ElMessage.success(`已创建 ${result.created} 条默认权限`);
    await load();
  } catch (e: any) {
    ElMessage.error(e.message);
  }
}

async function handleReload() {
  await reloadCache();
  ElMessage.success("缓存已重载");
}

onMounted(load);
</script>
