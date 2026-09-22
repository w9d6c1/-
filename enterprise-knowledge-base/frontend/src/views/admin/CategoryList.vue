<template>
  <div>
    <el-card>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px">
        <h3 style="margin:0">分类管理</h3>
        <el-button type="primary" @click="openCreate(null)">新建根分类</el-button>
      </div>

      <div v-if="selectedIds.length > 0" style="margin-bottom:12px">
        <el-button type="danger" @click="handleBatchDelete">批量删除 ({{ selectedIds.length }})</el-button>
        <el-button @click="selectedIds = []">取消选择</el-button>
      </div>

      <el-table
        :data="tree"
        row-key="id"
        default-expand-all
        :tree-props="{ children: 'children' }"
        stripe
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="name" label="名称" min-width="220" />
        <el-table-column label="范围" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="scopeTagType(row.scope)">{{ scopeLabel(row.scope) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'disabled' ? 'info' : 'success'">
              {{ row.status === 'disabled' ? '已禁用' : '启用中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="部门" width="120" />
        <el-table-column label="操作" width="300">
          <template #default="{ row }">
            <el-button size="small" @click="openCreate(row)">新增子级</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.status === 'disabled' ? 'success' : 'warning'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'disabled' ? '启用' : '禁用' }}
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="460px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="分类名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="范围" required>
          <el-select v-model="form.scope" style="width:100%" placeholder="必选，不可为空">
            <el-option label="公共 (public)" value="public" />
            <el-option label="客服 (customer)" value="customer" />
            <el-option label="内部 (internal)" value="internal" />
          </el-select>
        </el-form-item>
        <el-form-item label="父级分类">
          <el-select v-model="form.parent_id" style="width:100%" clearable placeholder="不选则为根分类">
            <el-option
              v-for="opt in parentOptions"
              :key="opt.id"
              :label="opt.name"
              :value="opt.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canSubmit" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  fetchCategoryTree,
  fetchCategories,
  createCategory,
  updateCategory,
  setCategoryStatus,
  deleteCategory,
  batchDeleteCategories,
  type Category,
  type CategoryScope,
} from "@/api/category";

const tree = ref<Category[]>([]);
const flat = ref<Category[]>([]);
const loading = ref(false);
const selectedIds = ref<number[]>([]);

function handleSelectionChange(rows: Category[]) {
  selectedIds.value = rows.map(r => r.id);
}

const dialogVisible = ref(false);
const editingId = ref<number | null>(null);
const form = ref<{ name: string; scope: CategoryScope; parent_id: number | null; sort_order: number }>({
  name: "",
  scope: "public",
  parent_id: null,
  sort_order: 0,
});

const dialogTitle = computed(() => (editingId.value === null ? "新建分类" : "编辑分类"));
const canSubmit = computed(() => !!form.value.name.trim() && !!form.value.scope);

// 编辑时父级下拉需排除自身，避免形成环 (后端亦有防环校验)
const parentOptions = computed(() =>
  flat.value.filter((c) => c.id !== editingId.value)
);

function scopeLabel(s: string) {
  return s === "public" ? "公共" : s === "customer" ? "客服" : "内部";
}
function scopeTagType(s: string) {
  return s === "internal" ? "danger" : s === "customer" ? "warning" : "primary";
}

async function load() {
  loading.value = true;
  try {
    [tree.value, flat.value] = await Promise.all([fetchCategoryTree(), fetchCategories()]);
  } finally {
    loading.value = false;
  }
}

function openCreate(parent: Category | null) {
  editingId.value = null;
  form.value = { name: "", scope: "public", parent_id: parent ? parent.id : null, sort_order: 0 };
  dialogVisible.value = true;
}

function openEdit(row: Category) {
  editingId.value = row.id;
  form.value = {
    name: row.name,
    scope: row.scope as CategoryScope,
    parent_id: row.parent_id,
    sort_order: row.sort_order,
  };
  dialogVisible.value = true;
}

async function handleSubmit() {
  if (!canSubmit.value) {
    ElMessage.warning("名称与范围为必填，范围不可为空");
    return;
  }
  try {
    if (editingId.value === null) {
      await createCategory({
        name: form.value.name.trim(),
        scope: form.value.scope,
        parent_id: form.value.parent_id,
        sort_order: form.value.sort_order,
      });
      ElMessage.success("分类已创建");
    } else {
      await updateCategory(editingId.value, {
        name: form.value.name.trim(),
        scope: form.value.scope,
        parent_id: form.value.parent_id,
        sort_order: form.value.sort_order,
      });
      ElMessage.success("分类已更新");
    }
    dialogVisible.value = false;
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message || "保存失败");
  }
}

async function toggleStatus(row: Category) {
  const next = row.status === "disabled" ? "enabled" : "disabled";
  try {
    await setCategoryStatus(row.id, next);
    ElMessage.success(next === "disabled" ? "已禁用，该分类下知识将不可被检索" : "已启用");
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message || "操作失败");
  }
}

async function handleDelete(row: Category) {
  try {
    await ElMessageBox.confirm(`确认删除分类「${row.name}」？`, "提示", { type: "warning" });
  } catch {
    return;
  }
  try {
    await deleteCategory(row.id);
    ElMessage.success("已删除");
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message || "删除失败");
  }
}

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedIds.value.length} 个分类？`, "批量删除", { type: "warning" });
    const result = await batchDeleteCategories(selectedIds.value);
    if (result.failed.length > 0) {
      ElMessage.warning(`成功 ${result.deleted} 个，失败 ${result.failed.length} 个`);
    } else {
      ElMessage.success(`已删除 ${result.deleted} 个分类`);
    }
    selectedIds.value = [];
    await load();
  } catch { /* cancelled */ }
}

onMounted(load);
</script>
