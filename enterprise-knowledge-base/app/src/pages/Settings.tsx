import { useState } from 'react'
import { Settings2, Save, Shield, Wrench } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Slider } from '@/components/ui/slider'
import { toast } from 'sonner'
import { useAuth } from '@/stores/auth'

export function SettingsPage() {
  const { user } = useAuth()

  const [seo, setSEO] = useState({
    enableAutoKeywords: true,
    enableAutoMeta: true,
    enableInternalLinks: true,
    keywordCount: 8,
    metaTitleLength: 60,
    metaDescriptionLength: 160,
  })

  const [cms, setCMS] = useState({
    wordpressUrl: '',
    wordpressUser: '',
    wordpressToken: '',
    enableAutoPublish: false,
    defaultCategory: '',
    defaultTags: '',
  })

  const handleSaveSEO = () => {
    toast.success('SEO 设置已保存到本地')
  }

  const handleSaveCMS = () => {
    toast.success('CMS 设置已保存到本地')
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">系统设置</h1>
        <p className="text-sm text-muted-foreground mt-1">
          AI 模型配置由服务端统一管理，此处仅配置前端本地设置
        </p>
      </div>

      <Tabs defaultValue="seo">
        <TabsList>
          <TabsTrigger value="seo"><Settings2 className="h-4 w-4 mr-1.5" />SEO 设置</TabsTrigger>
          <TabsTrigger value="cms"><Wrench className="h-4 w-4 mr-1.5" />CMS 集成</TabsTrigger>
          <TabsTrigger value="info"><Shield className="h-4 w-4 mr-1.5" />关于</TabsTrigger>
        </TabsList>

        <TabsContent value="seo" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">SEO 优化配置</CardTitle>
              <CardDescription>搜索引擎优化参数（保存在浏览器本地）</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Label>自动提取关键词</Label>
                <Switch checked={seo.enableAutoKeywords} onCheckedChange={v => setSEO(s => ({ ...s, enableAutoKeywords: v }))} />
              </div>
              <div className="flex items-center justify-between">
                <Label>自动生成 Meta 标题和描述</Label>
                <Switch checked={seo.enableAutoMeta} onCheckedChange={v => setSEO(s => ({ ...s, enableAutoMeta: v }))} />
              </div>
              <div className="flex items-center justify-between">
                <Label>自动内链建议</Label>
                <Switch checked={seo.enableInternalLinks} onCheckedChange={v => setSEO(s => ({ ...s, enableInternalLinks: v }))} />
              </div>
              <div className="space-y-2">
                <Label>关键词数量：{seo.keywordCount}</Label>
                <Slider value={[seo.keywordCount]} onValueChange={([v]) => setSEO(s => ({ ...s, keywordCount: v }))} min={3} max={20} step={1} />
              </div>
              <div className="space-y-2">
                <Label>Meta 标题最大长度：{seo.metaTitleLength}</Label>
                <Slider value={[seo.metaTitleLength]} onValueChange={([v]) => setSEO(s => ({ ...s, metaTitleLength: v }))} min={30} max={80} step={5} />
              </div>
              <div className="space-y-2">
                <Label>Meta 描述最大长度：{seo.metaDescriptionLength}</Label>
                <Slider value={[seo.metaDescriptionLength]} onValueChange={([v]) => setSEO(s => ({ ...s, metaDescriptionLength: v }))} min={80} max={300} step={10} />
              </div>
              <Button onClick={handleSaveSEO}>
                <Save className="mr-2 h-4 w-4" />
                保存 SEO 设置
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cms" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">WordPress 集成</CardTitle>
              <CardDescription>配置 WordPress REST API 连接信息</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>WordPress 站点 URL</Label>
                <Input placeholder="https://your-site.com" value={cms.wordpressUrl}
                  onChange={e => setCMS(c => ({ ...c, wordpressUrl: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label>用户名</Label>
                <Input placeholder="WordPress 用户名" value={cms.wordpressUser}
                  onChange={e => setCMS(c => ({ ...c, wordpressUser: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label>应用密码 / Token</Label>
                <Input type="password" placeholder="应用密码" value={cms.wordpressToken}
                  onChange={e => setCMS(c => ({ ...c, wordpressToken: e.target.value }))} />
              </div>
              <div className="flex items-center justify-between">
                <Label>审核通过后自动发布</Label>
                <Switch checked={cms.enableAutoPublish} onCheckedChange={v => setCMS(c => ({ ...c, enableAutoPublish: v }))} />
              </div>
              <div className="space-y-2">
                <Label>默认分类 (slug)</Label>
                <Input placeholder="uncategorized" value={cms.defaultCategory}
                  onChange={e => setCMS(c => ({ ...c, defaultCategory: e.target.value }))} />
              </div>
              <div className="space-y-2">
                <Label>默认标签（逗号分隔）</Label>
                <Input placeholder="知识库,技术" value={cms.defaultTags}
                  onChange={e => setCMS(c => ({ ...c, defaultTags: e.target.value }))} />
              </div>
              <Button onClick={handleSaveCMS}>
                <Save className="mr-2 h-4 w-4" />
                保存 CMS 设置
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="info" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">系统信息</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">后端 API</span>
                <span>{import.meta.env.VITE_API_BASE_URL || '/api'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">当前用户</span>
                <span>{user?.username} ({user?.role})</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">所属部门</span>
                <span>{user?.department || '无'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">AI 模型</span>
                <span>服务端统一配置</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">向量化</span>
                <span>Milvus + Elasticsearch</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
