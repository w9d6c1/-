import { useState, useEffect } from 'react'
import {
  Plus, Trash2, RefreshCw,
  Loader2, ShieldCheck, Cable, Layers,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import {
  getAccounts, createAccount, deleteAccount, verifyAccount, getPlatforms,
  type PlatformAccountItem, type PlatformInfo,
} from '@/api/articles'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

const PLATFORM_LABELS: Record<string, string> = {
  toutiao: '头条号',
  baijia: '百家号',
  zhihu: '知乎',
  wangyi: '网易号',
  csdn: 'CSDN',
  jianshu: '简书',
  weibo: '微博',
  xiaohongshu: '小红书',
  yidianhao: '一点号',
  douyin_tuwen: '抖音图文',
}

const CRED_TYPE_LABELS: Record<string, string> = {
  token: '桥接器 Token',
  appid_secret: 'AppID / Secret',
  cookie_token: 'Cookie / Token',
  custom: '自定义',
}

const GROUP_CONFIG: Record<string, { ws: string; label: string }> = {
  '2113': { ws: 'ws://localhost:9531', label: '2113 组' },
  '2114': { ws: 'ws://localhost:9533', label: '2114 组' },
  '2119': { ws: 'ws://localhost:9535', label: '2119 组' },
  '9023': { ws: 'ws://localhost:9537', label: '9023 组' },
}

export function Accounts() {
  const [accounts, setAccounts] = useState<PlatformAccountItem[]>([])
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [verifying, setVerifying] = useState<number | null>(null)

  const [form, setForm] = useState({
    platform_id: 'zhihu',
    account_name: '',
    account_group: '2113',
    ws_token: '',
    credentials: '',
    credentials_type: 'token' as string,
  })

  const loadData = async () => {
    const [accs, plats] = await Promise.all([getAccounts(), getPlatforms()])
    setAccounts(accs)
    setPlatforms(plats)
    setLoading(false)
  }

  useEffect(() => { loadData() }, [])

  const handleCreate = async () => {
    if (!form.account_name.trim()) {
      toast.error('请填写账号名称')
      return
    }
    if (form.credentials_type === 'token' && !form.ws_token.trim()) {
      toast.error('请填写 Chrome 扩展 Token')
      return
    }
    if (form.credentials_type === 'appid_secret' && !form.credentials.trim()) {
      toast.error('请填写凭证')
      return
    }
    try {
      await createAccount({
        platform_id: form.platform_id,
        account_name: form.account_name,
        account_group: form.credentials_type === 'token' ? form.account_group : '',
        ws_token: form.credentials_type === 'token' ? form.ws_token : '',
        credentials: form.credentials_type !== 'token' ? form.credentials : undefined,
        credentials_type: form.credentials_type,
      })
      toast.success('账号创建成功')
      setDialogOpen(false)
      setForm({
        platform_id: 'zhihu',
        account_name: '',
        account_group: '2113',
        ws_token: '',
        credentials: '',
        credentials_type: 'token',
      })
      loadData()
    } catch {
      toast.error('创建失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除此账号？')) return
    try {
      await deleteAccount(id)
      toast.success('已删除')
      loadData()
    } catch {
      toast.error('删除失败')
    }
  }

  const handleVerify = async (id: number) => {
    setVerifying(id)
    try {
      const result = await verifyAccount(id)
      if (result.success) {
        toast.success(`验证成功：${result.message}`)
      } else {
        toast.error(`验证失败：${result.message}`)
      }
      loadData()
    } catch {
      toast.error('验证异常')
    } finally {
      setVerifying(null)
    }
  }

  const isBridgePlatform = (_platformId: string) => {
    return true
  }

  const getCredsPlaceholder = (_type: string, _platform: string) => {
    return '{"cookie": "...", "token": "..."}'
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">平台账号</h1>
          <p className="text-sm text-muted-foreground">管理各发布平台的认证账号，支持同平台多账号。桥接器模式通过 Chrome 扩展发布。</p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          添加账号
        </Button>
      </div>

      <Card>
        <CardContent className="pt-6">
          {accounts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShieldCheck className="mx-auto h-12 w-12 mb-3 opacity-30" />
              <p>暂无平台账号</p>
              <p className="text-xs mt-1">点击右上角"添加账号"开始绑定</p>
            </div>
          ) : (
            <div className="space-y-3">
              {accounts.map(acc => (
                <div key={acc.id} className="flex items-center justify-between p-3 rounded-lg border">
                  <div className="flex items-center gap-3 min-w-0">
                    {acc.account_group && (
                      <Badge variant="outline" className="text-xs font-mono shrink-0">
                        {acc.account_group}
                      </Badge>
                    )}
                    <Badge variant={acc.status === 'active' ? 'default' : 'destructive'} className="shrink-0">
                      {PLATFORM_LABELS[acc.platform_id] || acc.platform_id}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{acc.account_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {CRED_TYPE_LABELS[acc.credentials_type] || acc.credentials_type}
                        {acc.last_verified_at && (
                          <> · 上次验证 {new Date(acc.last_verified_at).toLocaleString('zh-CN')}</>
                        )}
                      </p>
                    </div>
                    {acc.error_message && (
                      <span className="text-xs text-destructive truncate max-w-[200px]">
                        {acc.error_message}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => handleVerify(acc.id)}
                      disabled={verifying === acc.id}
                    >
                      {verifying === acc.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3 w-3 mr-1" />
                      )}
                      验证
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs text-destructive hover:text-destructive"
                      onClick={() => handleDelete(acc.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加平台账号</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div>
              <Label className="text-sm mb-1.5 block">选择平台</Label>
              <div className="flex flex-wrap gap-2">
                {platforms.map(p => (
                  <button
                    key={p.platform}
                    onClick={() => setForm(prev => ({
                      ...prev,
                      platform_id: p.platform,
                      credentials_type: isBridgePlatform(p.platform) ? 'token' : prev.credentials_type,
                    }))}
                    className={`px-3 py-1.5 rounded-md text-xs border transition-colors ${
                      form.platform_id === p.platform
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-muted hover:border-muted-foreground/30'
                    }`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <Label className="text-sm mb-1.5 block">凭证类型</Label>
              <div className="flex flex-wrap gap-2">
                {isBridgePlatform(form.platform_id) ? (
                  <span className="px-3 py-1.5 rounded-md text-xs bg-primary/5 text-primary border border-primary/20">
                    <Cable className="h-3 w-3 inline mr-1" />
                    桥接器 Token — 通过 Chrome 扩展发布，无需平台密码
                  </span>
                ) : (
                  (['appid_secret', 'cookie_token', 'custom'] as const).map(type => (
                    <button
                      key={type}
                      onClick={() => setForm(prev => ({ ...prev, credentials_type: type }))}
                      className={`px-3 py-1.5 rounded-md text-xs border transition-colors ${
                        form.credentials_type === type
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-muted hover:border-muted-foreground/30'
                      }`}
                    >
                      {CRED_TYPE_LABELS[type]}
                    </button>
                  ))
                )}
              </div>
            </div>

            {isBridgePlatform(form.platform_id) && (
              <>
                <div>
                  <Label className="text-sm mb-1.5 block">账号组（浏览器身份）</Label>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(GROUP_CONFIG).map(([group, cfg]) => (
                      <button
                        key={group}
                        onClick={() => setForm(prev => ({ ...prev, account_group: group }))}
                        className={`px-3 py-1.5 rounded-md text-xs border transition-colors ${
                          form.account_group === group
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'border-muted hover:border-muted-foreground/30'
                        }`}
                      >
                        <Layers className="h-3 w-3 inline mr-1" />
                        {cfg.label}
                      </button>
                    ))}
                  </div>
                  {form.account_group && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Chrome 扩展地址：{GROUP_CONFIG[form.account_group]?.ws}
                    </p>
                  )}
                </div>

                <div>
                  <Label className="text-sm mb-1.5 block">Chrome 扩展 Token</Label>
                  <div className="relative">
                    <Input
                      type="password"
                      placeholder="从 Chrome 文章同步助手中获取"
                      value={form.ws_token}
                      onChange={e => setForm(prev => ({ ...prev, ws_token: e.target.value }))}
                      className="font-mono text-xs"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Token 将加密存储，列表不返回明文。与账号组严格一一对应，不可共用。
                  </p>
                </div>
              </>
            )}

            <div>
              <Label className="text-sm mb-1.5 block">账号名称</Label>
              <Input
                placeholder='例如"2113知乎号"、"公司主号"'
                value={form.account_name}
                onChange={e => setForm(prev => ({ ...prev, account_name: e.target.value }))}
              />
            </div>

            {!isBridgePlatform(form.platform_id) && (
              <div>
                <Label className="text-sm mb-1.5 block">凭证 (JSON)</Label>
                <div className="relative">
                  <Textarea
                    placeholder={getCredsPlaceholder(form.credentials_type, form.platform_id)}
                    value={form.credentials}
                    onChange={e => setForm(prev => ({ ...prev, credentials: e.target.value }))}
                    rows={4}
                    className="font-mono text-xs"
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  凭证将加密存储，仅供发布时解密使用
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
              <Button onClick={handleCreate}>创建账号</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
