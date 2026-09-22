<template>
  <div class="citation-renderer">
    <div class="citation-content">
      <template v-for="(seg, i) in renderSegments" :key="i">
        <template v-if="seg.type === 'image-group'">
          <div class="img-group" :class="imgGroupClass(seg.items.length)">
            <div
              v-for="img in seg.items"
              :key="img.id"
              class="img-card"
              :class="{ placeholder: !img.resolved }"
            >
              <el-image
                v-if="img.resolved"
                :src="img.url"
                :preview-src-list="seg.previewUrls"
                preview-teleported
                fit="cover"
                class="chat-image"
                :style="imgStyle(img)"
              >
                <template #error>
                  <div class="img-fallback">图片加载失败</div>
                </template>
              </el-image>
              <div v-else-if="isStreaming" class="img-placeholder">
                <el-icon class="is-loading"><Loading /></el-icon>
              </div>
            </div>
          </div>
          <div class="img-caption" v-if="seg.captionText">
            {{ seg.captionText }}
          </div>
        </template>
        <template v-else-if="seg.type === 'citation'">
          <sup
            class="citation-ref"
            :class="{ placeholder: !isActive }"
            @click="isActive ? scrollToCitation(seg.index) : undefined"
          >[{{ seg.index }}]</sup>
        </template>
        <span v-else v-html="seg.html" />
      </template>
    </div>

    <div v-if="isActive && activeCitations.length > 0" class="citation-references">
      <div class="citation-divider">参考文献</div>
      <div
        v-for="c in activeCitations"
        :key="c.index"
        :id="`cite-ref-${c.index}`"
        class="citation-item"
        :class="{ internal: c.is_internal, external: !c.is_internal }"
      >
        <span class="cite-num">[{{ c.index }}]</span>
        <span class="cite-label">{{ platformLabel(c) }}</span>
        <template v-if="!c.is_internal && c.url">
          <a :href="c.url" target="_blank" rel="noopener noreferrer" class="cite-title">
            《{{ c.title }}》
          </a>
          <a :href="c.url" target="_blank" rel="noopener noreferrer" class="cite-view-link">查看原文</a>
        </template>
        <span v-else class="cite-title">《{{ c.title }}》</span>
        <div v-if="c.images && c.images.length" class="cite-thumbs">
          <el-image
            v-for="(img, idx) in c.images"
            :key="img.id"
            :src="img.url"
            :preview-src-list="c.images.map((x) => x.url)"
            :initial-index="idx"
            preview-teleported
            fit="cover"
            class="cite-thumb"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Loading } from "@element-plus/icons-vue";
import type { Citation, ImageInfo } from "@/api/agent";

const props = defineProps<{
  content: string;
  citations?: Citation[];
  images?: ImageInfo[];
  isStreaming?: boolean;
}>();

interface TextSegment {
  type: "text";
  html: string;
}

interface CitationSegment {
  type: "citation";
  index: number;
}

interface ImageRef {
  id: number;
  url: string;
  resolved: boolean;
}

interface ImageGroupSegment {
  type: "image-group";
  items: ImageRef[];
  previewUrls: string[];
  captionText: string;
}

type Segment = TextSegment | CitationSegment | ImageGroupSegment;

const CITATION_RE = /\[(\d+)\]/g;
const IMG_MARKER_RE = /\[图(\d+)\]/g;
const COMBINED_RE = /\[图(\d+)\]|\[(\d+)\]/g;

const imageMap = computed<Map<number, ImageInfo>>(() => {
  const map = new Map<number, ImageInfo>();
  for (const img of props.images || []) {
    map.set(img.id, img);
  }
  return map;
});

const citationByIndex = computed<Map<number, Citation>>(() => {
  const map = new Map<number, Citation>();
  for (const c of props.citations || []) {
    map.set(c.index, c);
  }
  return map;
});

const segments = computed<Segment[]>(() => {
  const text = props.content || "";
  if (!text) return [];

  const result: Segment[] = [];
  let lastIndex = 0;

  const regex = new RegExp(COMBINED_RE.source, "g");
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push({
        type: "text",
        html: escapeText(text.slice(lastIndex, match.index)),
      });
    }
    if (match[1] !== undefined) {
      const id = parseInt(match[1], 10);
      const info = imageMap.value.get(id);
      result.push({
        type: "image-group",
        items: [
          {
            id,
            url: info?.url || "",
            resolved: !!info,
          },
        ],
        previewUrls: info ? [info.url] : [],
        captionText: "",
      });
    } else {
      result.push({
        type: "citation",
        index: parseInt(match[2], 10),
      });
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    result.push({
      type: "text",
      html: escapeText(text.slice(lastIndex)),
    });
  }

  return mergeConsecutiveImages(result);
});

function mergeConsecutiveImages(input: Segment[]): Segment[] {
  const out: Segment[] = [];
  for (const seg of input) {
    if (seg.type === "image-group") {
      const last = out[out.length - 1];
      if (last && last.type === "image-group") {
        last.items.push(...seg.items);
        last.previewUrls.push(...seg.previewUrls);
        continue;
      }
    }
    out.push(seg.type === "image-group" ? { ...seg, items: [...seg.items], previewUrls: [...seg.previewUrls] } : seg);
  }
  for (const seg of out) {
    if (seg.type === "image-group" && seg.items.length > 0) {
      const first = seg.items[0];
      const info = imageMap.value.get(first.id);
      if (info) {
        const cite = citationByIndex.value.get(info.doc_index);
        if (cite) {
          seg.captionText = `来自《${cite.title}》`;
        }
      }
    }
  }
  return out;
}

const renderSegments = computed<Segment[]>(() => {
  return segments.value.filter((seg) => {
    if (seg.type === "image-group") {
      const visible = seg.items.some((img) => img.resolved || props.isStreaming);
      if (!visible) return false;
    }
    return true;
  });
});

const isActive = computed(() => {
  return !!props.citations && props.citations.length > 0;
});

const citedIndices = computed(() => {
  const set = new Set<number>();
  for (const seg of segments.value) {
    if (seg.type === "citation") set.add(seg.index);
  }
  return set;
});

const activeCitations = computed(() => {
  if (!props.citations) return [];
  return props.citations
    .filter((c) => citedIndices.value.has(c.index))
    .sort((a, b) => a.index - b.index);
});

function escapeText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
}

function platformLabel(c: Citation): string {
  if (c.is_internal) return "内部文档";
  return c.source_name || c.platform || "外部来源";
}

function imgGroupClass(count: number): string {
  if (count <= 1) return "img-count-1";
  if (count === 2) return "img-count-2";
  return "img-count-many";
}

function imgStyle(img: ImageRef) {
  const info = imageMap.value.get(img.id);
  if (info && info.height && info.width && info.width > 0) {
    const ratio = Math.min(info.height / info.width, 2.2);
    return { aspectRatio: `1 / ${ratio.toFixed(2)}` };
  }
  return { aspectRatio: "4 / 3" };
}

function scrollToCitation(index: number) {
  const el = document.getElementById(`cite-ref-${index}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}
</script>

<style scoped>
.citation-renderer {
  word-break: break-word;
}

.citation-content {
  line-height: 1.7;
}

.citation-ref {
  font-size: 0.75em;
  vertical-align: super;
  cursor: pointer;
  color: #409eff;
  font-weight: 600;
  margin: 0 1px;
  transition: color 0.2s;
}

.citation-ref:hover {
  color: #337ecc;
  text-decoration: underline;
}

.citation-ref.placeholder {
  cursor: default;
  color: #c0c4cc;
}

.citation-ref.placeholder:hover {
  color: #c0c4cc;
  text-decoration: none;
}

/* ── 内嵌图片组（豆包式卡片布局） ── */
.img-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 4px;
}

.img-count-1 {
  max-width: 60%;
}

.img-count-2 {
  max-width: 90%;
}

.img-count-many {
  max-width: 100%;
}

.img-card {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  background: #f5f7fa;
  flex-shrink: 0;
}

.img-count-1 .img-card {
  width: 100%;
}

.img-count-2 .img-card {
  width: calc(50% - 4px);
}

.img-count-many .img-card {
  width: calc(33.333% - 6px);
}

.chat-image {
  display: block;
  width: 100%;
  min-height: 120px;
  max-height: 420px;
}

.img-card.placeholder .chat-image {
  min-height: 120px;
}

.img-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: #c0c4cc;
  background: linear-gradient(90deg, #f5f7fa 25%, #e8ecf1 37%, #f5f7fa 63%);
  background-size: 400% 100%;
  animation: imgShimmer 1.4s ease infinite;
}

.img-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  color: #909399;
  font-size: 12px;
  background: #f5f7fa;
}

@keyframes imgShimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.img-caption {
  font-size: 12px;
  color: #909399;
  margin: 2px 0 8px;
  cursor: pointer;
}

.img-caption:hover {
  color: #409eff;
}

/* ── 参考文献 ── */
.citation-references {
  margin-top: 20px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.citation-divider {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 12px;
}

.citation-item {
  padding: 8px 0;
  font-size: 13px;
  line-height: 1.6;
  border-bottom: 1px dashed #ebeef5;
}

.citation-item:last-child {
  border-bottom: none;
}

.cite-num {
  font-weight: 600;
  color: #409eff;
  margin-right: 8px;
  font-size: 12px;
}

.cite-label {
  color: #909399;
  margin-right: 6px;
}

.cite-title {
  color: #303133;
  font-weight: 500;
}

.citation-item.external .cite-title {
  color: #409eff;
  text-decoration: none;
}

.citation-item.external .cite-title:hover {
  text-decoration: underline;
}

.cite-view-link {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
  text-decoration: none;
}

.cite-view-link:hover {
  color: #409eff;
  text-decoration: underline;
}

.cite-thumbs {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.cite-thumb {
  width: 64px;
  height: 48px;
  border-radius: 4px;
  border: 1px solid #ebeef5;
  cursor: pointer;
}
</style>
