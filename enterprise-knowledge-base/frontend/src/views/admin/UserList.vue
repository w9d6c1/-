<template>
  <div>
    <el-card>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h3>用户管理</h3>
        <el-button type="primary" @click="showCreateDialog = true">新建用户</el-button>
      </div>

      <div v-if="selectedIds.length > 0" style="margin-bottom:12px">
        <el-button type="danger" @click="handleBatchDisable">批量禁用 ({{ selectedIds.length }})</el-button>
        <el-button @click="selectedIds = []">取消选择</el-button>
      </div>

      <el-table :data="users" stripe style="margin-top: 12px;" v-loading="loading" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="display_name" label="显示名" width="120" />
        <el-table-column label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" width="100" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-switch
              :model-value="row.is_active"
              :disabled="row.id === auth.user?.id"
              @change="(val: boolean) => handleToggleActive(row, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="160">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="row.id === auth.user?.id"
              @click="handleDisable(row)"
            >禁用</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="load"
        />
      </div>
    </el-card>

    <el-dialog v-model="showCreateDialog" title="新建用户" width="460px" @closed="resetCreateForm">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="createForm.password_confirm" type="password" show-password />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="createForm.display_name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="超级管理员" value="superadmin" />
            <el-option label="部门管理员" value="dept_admin" />
            <el-option label="内容运营" value="operator" />
            <el-option label="只读用户" value="readonly" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="createForm.department" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!createForm.username || !createForm.password" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑用户" width="420px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width: 100%" :disabled="editForm.id === auth.user?.id">
            <el-option label="超级管理员" value="superadmin" />
            <el-option label="部门管理员" value="dept_admin" />
            <el-option label="内容运营" value="operator" />
            <el-option label="只读用户" value="readonly" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="editForm.department" />
        </el-form-item>
        <el-form-item label="显示名">
          <el-input v-model="editForm.display_name" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAuthStore } from "@/stores/auth";
import { fetchUsers, createUser, updateUser, disableUser, batchDisableUsers, type UserInfo } from "@/api/user";

const auth = useAuthStore();

const users = ref<UserInfo[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const showCreateDialog = ref(false);
const createForm = ref({
  username: "",
  password: "",
  password_confirm: "",
  display_name: "",
  role: "readonly",
  department: "",
});

const showEditDialog = ref(false);
const selectedIds = ref<number[]>([]);

function handleSelectionChange(rows: UserInfo[]) {
  selectedIds.value = rows.map(r => r.id);
}
const editForm = ref({
  id: 0,
  role: "",
  department: "",
  display_name: "",
});

function roleTagType(role: string) {
  const map: Record<string, string> = {
    superadmin: "danger",
    dept_admin: "warning",
    operator: "success",
    readonly: "info",
  };
  return map[role] || "info";
}

function roleLabel(role: string) {
  const map: Record<string, string> = {
    superadmin: "超级管理员",
    dept_admin: "部门管理员",
    operator: "内容运营",
    readonly: "只读用户",
  };
  return map[role] || role;
}

function formatTime(ts: string) {
  if (!ts) return "";
  return new Date(ts).toLocaleString("zh-CN");
}

async function load() {
  loading.value = true;
  try {
    const data = await fetchUsers(page.value, pageSize.value);
    users.value = data.items;
    total.value = data.total;
  } catch (e: any) {
    ElMessage.error(e.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  if (createForm.value.password !== createForm.value.password_confirm) {
    ElMessage.error("两次密码不一致");
    return;
  }
  try {
    await createUser({
      username: createForm.value.username,
      password: createForm.value.password,
      password_confirm: createForm.value.password_confirm,
      display_name: createForm.value.display_name || undefined,
      role: createForm.value.role,
      department: createForm.value.department || undefined,
    });
    ElMessage.success("用户已创建");
    showCreateDialog.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e.message || "创建失败");
  }
}

function resetCreateForm() {
  createForm.value = {
    username: "",
    password: "",
    password_confirm: "",
    display_name: "",
    role: "readonly",
    department: "",
  };
}

function openEdit(row: UserInfo) {
  editForm.value = {
    id: row.id,
    role: row.role,
    department: row.department || "",
    display_name: row.display_name || "",
  };
  showEditDialog.value = true;
}

async function handleSaveEdit() {
  try {
    await updateUser(editForm.value.id, {
      role: editForm.value.role,
      department: editForm.value.department || undefined,
      display_name: editForm.value.display_name || undefined,
    });
    ElMessage.success("已更新");
    showEditDialog.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e.message || "更新失败");
  }
}

async function handleToggleActive(row: UserInfo, val: boolean) {
  try {
    await updateUser(row.id, { is_active: val });
    ElMessage.success(val ? "已启用" : "已禁用");
    await load();
  } catch (e: any) {
    ElMessage.error(e.message || "操作失败");
  }
}

async function handleDisable(row: UserInfo) {
  try {
    await ElMessageBox.confirm(`确定要禁用用户「${row.display_name || row.username || row.id}」吗？`, "确认禁用", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    await disableUser(row.id);
    ElMessage.success("已禁用");
    await load();
  } catch {
    // 取消操作
  }
}

async function handleBatchDisable() {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认禁用选中的 ${selectedIds.value.length} 个用户？`, "批量禁用", { type: "warning" });
    const result = await batchDisableUsers(selectedIds.value);
    if (result.failed.length > 0) {
      ElMessage.warning(`成功 ${result.deleted} 个，失败 ${result.failed.length} 个`);
    } else {
      ElMessage.success(`已禁用 ${result.deleted} 个用户`);
    }
    selectedIds.value = [];
    await load();
  } catch { /* cancelled */ }
}

onMounted(load);
</script>
