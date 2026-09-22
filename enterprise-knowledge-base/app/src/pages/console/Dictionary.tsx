import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { toast } from 'sonner'
import {
  fetchSynonyms, createSynonym, deleteSynonym, importSynonymsCsv,
  fetchSensitiveWords, createSensitiveWord, deleteSensitiveWord, importSensitiveWordsCsv,
  fetchForbidWords, createForbidWord, deleteForbidWord, importForbidWordsCsv,
} from '@/api/dictionary'

type Kind = 'synonym' | 'sensitive' | 'forbid'

interface Row { id: number; word: string; extra: string }

const KIND_META: Record<Kind, { title: string; wordLabel: string; extraLabel: string }> = {
  synonym: { title: '同义词', wordLabel: '词', extraLabel: '同义词（分号或逗号分隔）' },
  sensitive: { title: '敏感词', wordLabel: '词', extraLabel: '回答（可选）' },
  forbid: { title: '禁答词', wordLabel: '词', extraLabel: '回答（可选）' },
}

async function fetchDictRows(k: Kind): Promise<Row[]> {
  if (k === 'synonym') {
    const res = await fetchSynonyms(1, 500)
    return res.items.map(s => ({ id: s.id, word: s.word, extra: (s.synonyms || []).join('；') }))
  }
  if (k === 'sensitive') {
    const res = await fetchSensitiveWords(1, 500)
    return res.items.map(s => ({ id: s.id, word: s.word, extra: s.answer || '' }))
  }
  const res = await fetchForbidWords(1, 500)
  return res.items.map(s => ({ id: s.id, word: s.word, extra: s.answer || '' }))
}

export function Dictionary() {
  const [kind, setKind] = useState<Kind>('synonym')
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [word, setWord] = useState('')
  const [extra, setExtra] = useState('')
  const [saving, setSaving] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const [reloadKey, setReloadKey] = useState(0)
  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  useEffect(() => {
    let active = true
    fetchDictRows(kind)
      .then(r => { if (active) setRows(r) })
      .catch(() => toast.error('加载失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [kind, reloadKey])

  const handleAdd = async () => {
    if (!word.trim()) { toast.error('请输入词'); return }
    setSaving(true)
    try {
      if (kind === 'synonym') {
        const list = extra.split(/[;；,，]/).map(s => s.trim()).filter(Boolean)
        await createSynonym(word.trim(), list)
      } else if (kind === 'sensitive') {
        await createSensitiveWord(word.trim(), extra.trim() || undefined)
      } else {
        await createForbidWord(word.trim(), extra.trim() || undefined)
      }
      toast.success('已添加')
      setShowAdd(false); setWord(''); setExtra(''); reload()
    } catch {
      toast.error('添加失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      if (kind === 'synonym') await deleteSynonym(id)
      else if (kind === 'sensitive') await deleteSensitiveWord(id)
      else await deleteForbidWord(id)
      reload()
    } catch { toast.error('删除失败') }
  }

  const handleImport = async (file: File) => {
    try {
      const res = kind === 'synonym' ? await importSynonymsCsv(file)
        : kind === 'sensitive' ? await importSensitiveWordsCsv(file)
        : await importForbidWordsCsv(file)
      toast.success(`导入 ${res.imported} 条，跳过 ${res.skipped} 条`)
      reload()
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '导入失败')
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const meta = KIND_META[kind]

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">词库管理</h1>
        <p className="text-sm text-muted-foreground mt-1">同义词、敏感词与禁答词维护</p>
      </div>

      <Tabs value={kind} onValueChange={v => { setLoading(true); setKind(v as Kind) }}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="synonym">同义词</TabsTrigger>
            <TabsTrigger value="sensitive">敏感词</TabsTrigger>
            <TabsTrigger value="forbid">禁答词</TabsTrigger>
          </TabsList>
          <div className="flex gap-2">
            <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handleImport(f) }} />
            <Button variant="outline" onClick={() => fileRef.current?.click()}><Upload className="mr-2 h-4 w-4" />CSV 导入</Button>
            <Button onClick={() => setShowAdd(true)}><Plus className="mr-2 h-4 w-4" />新增</Button>
          </div>
        </div>

        <TabsContent value={kind} className="mt-4">
          <Card>
            <CardContent className="p-0">
              {loading ? (
                <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
              ) : rows.length === 0 ? (
                <p className="py-16 text-center text-sm text-muted-foreground">暂无数据</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{meta.wordLabel}</TableHead>
                      <TableHead>{meta.extraLabel}</TableHead>
                      <TableHead className="text-right w-20">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map(r => (
                      <TableRow key={r.id}>
                        <TableCell className="font-medium">{r.word}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{r.extra || '—'}</TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => handleDelete(r.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
          <div className="mt-3"><Badge variant="secondary">共 {rows.length} 条</Badge></div>
        </TabsContent>
      </Tabs>

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent>
          <DialogHeader><DialogTitle>新增{meta.title}</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2"><Label>{meta.wordLabel}</Label><Input value={word} onChange={e => setWord(e.target.value)} /></div>
            <div className="space-y-2"><Label>{meta.extraLabel}</Label><Input value={extra} onChange={e => setExtra(e.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAdd(false)}>取消</Button>
            <Button onClick={handleAdd} disabled={saving}>{saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
