// ========== Enums ==========

export type ArticleStatus = 'draft' | 'reviewing' | 'published' | 'rejected'

export type UserRole = 'admin' | 'editor' | 'writer'

export type BatchTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'scheduled'

export type BatchItemStatus = 'pending' | 'generating' | 'completed' | 'failed'

export type AIModelProvider = 'deepseek' | 'qwen' | 'ernie' | 'mock'

export type ScheduleType = 'once' | 'daily' | 'weekly' | 'monthly'

// ========== Core Types ==========

export interface User {
  id: string
  name: string
  email: string
  role: UserRole
  avatar?: string
  createdAt: string
}

export interface SEOInfo {
  metaTitle: string
  metaDescription: string
  keywords: string[]
  internalLinks: string[]
  slug: string
}

export interface Article {
  id: string
  title: string
  content: string
  excerpt: string
  htmlContent: string
  status: ArticleStatus
  seo: SEOInfo
  knowledgeRefs: string[]
  photos: string[]
  wordCount: number
  originalityScore: number
  authorId: string
  authorName: string
  modelUsed: string
  createdAt: string
  updatedAt: string
  publishedAt?: string
  tags: string[]
  category: string
}

export interface KnowledgeChunk {
  id: string
  docId: string
  text: string
  index: number
  embedding?: number[]
}

export interface KnowledgeDoc {
  id: string
  title: string
  content: string
  chunks: KnowledgeChunk[]
  tags: string[]
  wordCount: number
  createdAt: string
}

export interface BatchItem {
  id: string
  title: string
  photoName?: string
  photoData?: string
  status: BatchItemStatus
  articleId?: string
  error?: string
  generatedAt?: string
}

export interface BatchTask {
  id: string
  name: string
  items: BatchItem[]
  status: BatchTaskStatus
  config: GenerationConfig
  knowledgeDocIds: string[]
  progress: number
  scheduleType: ScheduleType
  scheduledAt?: string
  createdAt: string
  completedAt?: string
}

export interface GenerationConfig {
  provider: AIModelProvider
  model: string
  wordCount: number
  tone: string
  enableSEO: boolean
  enableOriginalityCheck: boolean
  temperature: number
  systemPrompt: string
}

export interface AISettings {
  provider: AIModelProvider
  apiKey: string
  model: string
  endpoint: string
  defaultWordCount: number
  defaultTone: string
  defaultTemperature: number
  systemPrompt: string
  embeddingProvider?: 'qwen' | 'openai' | 'local'
  embeddingModel?: string
  embeddingEndpoint?: string
}

export interface SEOSettings {
  enableAutoKeywords: boolean
  enableAutoMeta: boolean
  enableInternalLinks: boolean
  keywordCount: number
  metaTitleLength: number
  metaDescriptionLength: number
}

export interface CMSSettings {
  wordpressUrl: string
  wordpressUser: string
  wordpressToken: string
  enableAutoPublish: boolean
  defaultCategory: string
  defaultTags: string[]
}

export interface AppSettings {
  ai: AISettings
  seo: SEOSettings
  cms: CMSSettings
}

export interface DashboardStats {
  totalArticles: number
  publishedArticles: number
  draftArticles: number
  reviewingArticles: number
  totalKnowledgeDocs: number
  totalKnowledgeWords: number
  totalBatchTasks: number
  completedTasks: number
  scheduledTasks: number
  recentArticles: Article[]
  recentTasks: BatchTask[]
}

// ========== Defaults ==========

export const DEFAULT_AI_SETTINGS: AISettings = {
  provider: 'mock',
  apiKey: '',
  model: 'deepseek-chat',
  endpoint: 'https://api.deepseek.com/v1',
  defaultWordCount: 1500,
  defaultTone: '专业',
  defaultTemperature: 0.7,
  systemPrompt: '你是一位专业的内容创作者，擅长撰写结构清晰、内容丰富的文章。请根据给定的标题、照片描述和知识库素材，生成一篇高质量、SEO友好的原创文章。',
}

export const DEFAULT_SEO_SETTINGS: SEOSettings = {
  enableAutoKeywords: true,
  enableAutoMeta: true,
  enableInternalLinks: true,
  keywordCount: 8,
  metaTitleLength: 60,
  metaDescriptionLength: 160,
}

export const DEFAULT_CMS_SETTINGS: CMSSettings = {
  wordpressUrl: '',
  wordpressUser: '',
  wordpressToken: '',
  enableAutoPublish: false,
  defaultCategory: '',
  defaultTags: [],
}

export const DEFAULT_SETTINGS: AppSettings = {
  ai: DEFAULT_AI_SETTINGS,
  seo: DEFAULT_SEO_SETTINGS,
  cms: DEFAULT_CMS_SETTINGS,
}
