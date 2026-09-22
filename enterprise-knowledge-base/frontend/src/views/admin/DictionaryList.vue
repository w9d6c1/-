<template>
  <div>
    <el-card>
      <el-tabs v-model="activeTab">
        <!-- ═══ 同义词 ═══ -->
        <el-tab-pane label="同义词" name="synonym">
          <el-space style="margin-bottom: 12px" wrap>
            <el-input v-model="synForm.word" placeholder="标准术语" style="width: 140px" />
            <el-input v-model="synForm.synonymsText" placeholder="原始表述（逗号分隔）" style="width: 240px" />
            <el-select v-model="synForm.scope" style="width: 100px">
              <el-option label="公共" value="public" />
              <el-option label="客服" value="customer" />
              <el-option label="内部" value="internal" />
            </el-select>
            <el-button type="primary" :disabled="!synForm.word || !synForm.synonymsText.trim()" @click="addSynonym">{{ editingSynId ? '更新' : '添加' }}</el-button>
            <el-button v-if="editingSynId" @click="cancelSynEdit">取消编辑</el-button>
            <el-divider direction="vertical" />
            <input ref="synFileRef" type="file" accept=".csv" style="display:none" @change="handleSynFile" />
            <el-button @click="synFileRef?.click()" :loading="importingSyn">批量导入 CSV</el-button>
          </el-space>
          <div v-if="selectedSynIds.length > 0" style="margin-bottom:12px">
            <el-button type="danger" @click="handleBatchDelSyn">批量删除 ({{ selectedSynIds.length }})</el-button>
            <el-button @click="selectedSynIds = []">取消选择</el-button>
          </div>
          <el-table :data="synonymItems" stripe v-loading="loadingSyn" @selection-change="handleSynSelectionChange">
            <el-table-column type="selection" width="55" />
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="word" label="标准术语" width="150" />
            <el-table-column label="原始表述" min-width="250">
              <template #default="{ row }">
                <el-tag v-for="s in row.synonyms" :key="s" size="small" style="margin-right: 4px">{{ s }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="范围" width="70">
              <template #default="{ row }">{{ scopeLabel(row.scope) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-button size="small" @click="editSynonym(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="delSynonym(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="synPage"
            :page-size="synPageSize"
            :total="synTotal"
            layout="total, prev, pager, next"
            @current-change="loadSynonyms"
            background
            style="margin-top: 12px; justify-content: flex-end"
          />
        </el-tab-pane>

        <!-- ═══ 敏感词 ═══ -->
        <el-tab-pane label="敏感词" name="sensitive">
          <el-space style="margin-bottom: 12px" wrap>
            <el-input v-model="swForm.word" placeholder="敏感词" style="width: 260px" />
            <el-button type="primary" :disabled="!swForm.word.trim()" @click="addSensitiveWord">添加</el-button>
            <el-divider direction="vertical" />
            <input ref="swFileRef" type="file" accept=".csv" style="display:none" @change="handleSwFile" />
            <el-button @click="swFileRef?.click()" :loading="importingSw">批量导入 CSV</el-button>
          </el-space>
          <div v-if="selectedSwIds.length > 0" style="margin-bottom:12px">
            <el-button type="danger" @click="handleBatchDelSw">批量删除 ({{ selectedSwIds.length }})</el-button>
            <el-button @click="selectedSwIds = []">取消选择</el-button>
          </div>
          <el-table :data="swItems" stripe v-loading="loadingSw" @selection-change="handleSwSelectionChange">
            <el-table-column type="selection" width="55" />
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="word" label="敏感词" min-width="300" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="delSensitiveWord(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="swPage"
            :page-size="swPageSize"
            :total="swTotal"
            layout="total, prev, pager, next"
            @current-change="loadSensitiveWords"
            background
            style="margin-top: 12px; justify-content: flex-end"
          />
        </el-tab-pane>

        <!-- ═══ 禁答词 ═══ -->
        <el-tab-pane label="禁答词" name="forbid">
          <el-space style="margin-bottom: 12px" wrap>
            <el-input v-model="fbForm.word" placeholder="禁答词" style="width: 150px" />
            <el-input v-model="fbForm.answer" placeholder="标准拒绝话术（选填）" style="width: 260px" />
            <el-select v-model="fbForm.scope" style="width: 100px">
              <el-option label="全部" value="all" />
              <el-option label="内部" value="internal" />
              <el-option label="客服" value="customer" />
            </el-select>
            <el-button type="primary" :disabled="!fbForm.word.trim()" @click="addForbidWord">添加</el-button>
            <el-divider direction="vertical" />
            <input ref="fbFileRef" type="file" accept=".csv" style="display:none" @change="handleFbFile" />
            <el-button @click="fbFileRef?.click()" :loading="importingFb">批量导入 CSV</el-button>
          </el-space>
          <div v-if="selectedFbIds.length > 0" style="margin-bottom:12px">
            <el-button type="danger" @click="handleBatchDelFb">批量删除 ({{ selectedFbIds.length }})</el-button>
            <el-button @click="selectedFbIds = []">取消选择</el-button>
          </div>
          <el-table :data="fbItems" stripe v-loading="loadingFb" @selection-change="handleFbSelectionChange">
            <el-table-column type="selection" width="55" />
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="word" label="禁答词" width="150" />
            <el-table-column label="渠道" width="80">
              <template #default="{ row }">
                <el-tag :type="row.scope === 'internal' ? 'warning' : row.scope === 'customer' ? 'success' : 'info'" size="small">
                  {{ row.scope === 'internal' ? '内部' : row.scope === 'customer' ? '客服' : '全部' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="标准拒绝话术" min-width="250" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.answer" style="color:#606266">{{ row.answer }}</span>
                <span v-else style="color:#ccc">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="delForbidWord(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            v-model:current-page="fbPage"
            :page-size="fbPageSize"
            :total="fbTotal"
            layout="total, prev, pager, next"
            @current-change="loadForbidWords"
            background
            style="margin-top: 12px; justify-content: flex-end"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  fetchSynonyms, createSynonym, updateSynonym, deleteSynonym, importSynonymsCsv, batchDeleteSynonyms,
  fetchSensitiveWords, createSensitiveWord, deleteSensitiveWord, importSensitiveWordsCsv, batchDeleteSensitiveWords,
  fetchForbidWords, createForbidWord, deleteForbidWord, importForbidWordsCsv, batchDeleteForbidWords,
  type Synonym, type SensitiveWord,
} from "@/api/dictionary";

function scopeLabel(s: string) { return s === "public" ? "公共" : s === "customer" ? "客服" : "内部"; }

const activeTab = ref("synonym");

// ── 同义词 ──
const synonymItems = ref<Synonym[]>([]);
const loadingSyn = ref(false);
const synPage = ref(1);
const synPageSize = ref(20);
const synTotal = ref(0);
const editingSynId = ref<number | null>(null);
const synForm = ref({ word: "", synonymsText: "", scope: "public" });
const synFileRef = ref<HTMLInputElement | null>(null);
const importingSyn = ref(false);

// ── 敏感词 ──
const swItems = ref<SensitiveWord[]>([]);
const loadingSw = ref(false);
const swPage = ref(1);
const swPageSize = ref(20);
const swTotal = ref(0);
const swForm = ref({ word: "" });
const swFileRef = ref<HTMLInputElement | null>(null);
const importingSw = ref(false);

// ── 禁答词 ──
const fbItems = ref<SensitiveWord[]>([]);
const loadingFb = ref(false);
const fbPage = ref(1);
const fbPageSize = ref(20);
const fbTotal = ref(0);
const fbForm = ref({ word: "", answer: "", scope: "all" });
const fbFileRef = ref<HTMLInputElement | null>(null);
const importingFb = ref(false);

const selectedSynIds = ref<number[]>([]);
const selectedSwIds = ref<number[]>([]);
const selectedFbIds = ref<number[]>([]);

function handleSynSelectionChange(rows: Synonym[]) { selectedSynIds.value = rows.map(r => r.id); }
function handleSwSelectionChange(rows: SensitiveWord[]) { selectedSwIds.value = rows.map(r => r.id); }
function handleFbSelectionChange(rows: SensitiveWord[]) { selectedFbIds.value = rows.map(r => r.id); }

// ── 同义词 CRUD ──

async function loadSynonyms() {
  loadingSyn.value = true;
  try {
    const res = await fetchSynonyms(synPage.value, synPageSize.value);
    synonymItems.value = res.items;
    synTotal.value = res.total;
  } catch { ElMessage.error("加载同义词失败"); }
  loadingSyn.value = false;
}

async function addSynonym() {
  if (!synForm.value.word || !synForm.value.synonymsText.trim()) return;
  const items = synForm.value.synonymsText.split(",").map(s => s.trim()).filter(Boolean);
  try {
    if (editingSynId.value) {
      await updateSynonym(editingSynId.value, {
        word: synForm.value.word, synonyms: items, scope: synForm.value.scope,
      });
      ElMessage.success("同义词已更新");
    } else {
      await createSynonym(synForm.value.word, items, synForm.value.scope);
      ElMessage.success("同义词已添加");
    }
    synForm.value = { word: "", synonymsText: "", scope: "public" };
    editingSynId.value = null;
    synPage.value = 1;
    await loadSynonyms();
  } catch { ElMessage.error("操作失败"); }
}

function editSynonym(row: Synonym) {
  editingSynId.value = row.id;
  synForm.value.word = row.word;
  synForm.value.synonymsText = row.synonyms.join(", ");
  synForm.value.scope = row.scope;
  activeTab.value = "synonym";
}

function cancelSynEdit() {
  editingSynId.value = null;
  synForm.value = { word: "", synonymsText: "", scope: "public" };
}

async function delSynonym(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该同义词？删除后立即生效。", "确认删除", { type: "warning" });
    await deleteSynonym(id);
    await loadSynonyms();
    ElMessage.success("已删除");
  } catch { /* cancelled */ }
}

async function handleSynFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  importingSyn.value = true;
  try {
    const result = await importSynonymsCsv(file);
    ElMessage.success(`导入完成：${result.imported} 条成功，${result.skipped} 条跳过${result.errors.length ? `，${result.errors.length} 条错误` : ""}`);
    synPage.value = 1;
    await loadSynonyms();
  } catch (e: any) { ElMessage.error(e.message || "导入失败"); }
  importingSyn.value = false;
  input.value = "";
}

// ── 敏感词 CRUD ──

async function loadSensitiveWords() {
  loadingSw.value = true;
  try {
    const res = await fetchSensitiveWords(swPage.value, swPageSize.value);
    swItems.value = res.items;
    swTotal.value = res.total;
  } catch { ElMessage.error("加载敏感词失败"); }
  loadingSw.value = false;
}

async function addSensitiveWord() {
  if (!swForm.value.word.trim()) return;
  try {
    await createSensitiveWord(swForm.value.word.trim());
    swForm.value.word = "";
    swPage.value = 1;
    await loadSensitiveWords();
    ElMessage.success("敏感词已添加");
  } catch { ElMessage.error("添加失败"); }
}

async function delSensitiveWord(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该敏感词？删除后立即生效。", "确认删除", { type: "warning" });
    await deleteSensitiveWord(id);
    await loadSensitiveWords();
    ElMessage.success("已删除");
  } catch { /* cancelled */ }
}

async function handleSwFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  importingSw.value = true;
  try {
    const result = await importSensitiveWordsCsv(file);
    ElMessage.success(`导入完成：${result.imported} 条成功，${result.skipped} 条跳过${result.errors.length ? `，${result.errors.length} 条错误` : ""}`);
    swPage.value = 1;
    await loadSensitiveWords();
  } catch (e: any) { ElMessage.error(e.message || "导入失败"); }
  importingSw.value = false;
  input.value = "";
}

async function handleBatchDelSyn() {
  if (selectedSynIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedSynIds.value.length} 条同义词？`, "批量删除", { type: "warning" });
    const result = await batchDeleteSynonyms(selectedSynIds.value);
    ElMessage.success(`已删除 ${result.deleted} 条`);
    selectedSynIds.value = [];
    synPage.value = 1;
    await loadSynonyms();
  } catch { /* cancelled */ }
}

async function handleBatchDelSw() {
  if (selectedSwIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedSwIds.value.length} 条敏感词？`, "批量删除", { type: "warning" });
    const result = await batchDeleteSensitiveWords(selectedSwIds.value);
    ElMessage.success(`已删除 ${result.deleted} 条`);
    selectedSwIds.value = [];
    swPage.value = 1;
    await loadSensitiveWords();
  } catch { /* cancelled */ }
}

// ── 禁答词 CRUD ──

async function loadForbidWords() {
  loadingFb.value = true;
  try {
    const res = await fetchForbidWords(fbPage.value, fbPageSize.value);
    fbItems.value = res.items;
    fbTotal.value = res.total;
  } catch { ElMessage.error("加载禁答词失败"); }
  loadingFb.value = false;
}

async function addForbidWord() {
  if (!fbForm.value.word.trim()) return;
  try {
    await createForbidWord(fbForm.value.word.trim(), fbForm.value.answer.trim() || undefined, fbForm.value.scope);
    fbForm.value.word = "";
    fbForm.value.answer = "";
    fbForm.value.scope = "all";
    fbPage.value = 1;
    await loadForbidWords();
    ElMessage.success("禁答词已添加");
  } catch { ElMessage.error("添加失败"); }
}

async function delForbidWord(id: number) {
  try {
    await ElMessageBox.confirm("确定删除该禁答词？删除后立即生效。", "确认删除", { type: "warning" });
    await deleteForbidWord(id);
    await loadForbidWords();
    ElMessage.success("已删除");
  } catch { /* cancelled */ }
}

async function handleFbFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  importingFb.value = true;
  try {
    const result = await importForbidWordsCsv(file);
    ElMessage.success(`导入完成：${result.imported} 条成功，${result.skipped} 条跳过${result.errors.length ? `，${result.errors.length} 条错误` : ""}`);
    fbPage.value = 1;
    await loadForbidWords();
  } catch (e: any) { ElMessage.error(e.message || "导入失败"); }
  importingFb.value = false;
  input.value = "";
}

async function handleBatchDelFb() {
  if (selectedFbIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确认删除选中的 ${selectedFbIds.value.length} 条禁答词？`, "批量删除", { type: "warning" });
    const result = await batchDeleteForbidWords(selectedFbIds.value);
    ElMessage.success(`已删除 ${result.deleted} 条`);
    selectedFbIds.value = [];
    fbPage.value = 1;
    await loadForbidWords();
  } catch { /* cancelled */ }
}

onMounted(async () => {
  await Promise.all([loadSynonyms(), loadSensitiveWords(), loadForbidWords()]);
});
</script>
