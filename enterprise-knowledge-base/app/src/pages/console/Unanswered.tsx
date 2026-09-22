import { useEffect, useState } from 'react'
import { Loader2, RefreshCw, Sparkles, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { toast } from 'sonner'
import { fetchUnanswered, updateUnanswered, convertUnanswered, type Unanswered as UnansweredItem } from '@/api/unanswered'

const STATUS_LABEL: Record<string, string> = { pending: '待处理', converted: '已转FAQ', resolved: '已解决', ignored: '已忽略' }

export function Unanswered() {
  const [rows, setRows] = useState<UnansweredItem[]>([])
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [convertId, setConvertId] = useState<number | null>(null)
  const [converting, setConverting] = useState(false)

  useEffect(() => {
    let active = true
    fetchUnanswered({ status: status || undefined, per_page: 100 })
      .then(r => { if (active) setRows(r) })
      .catch(() => toast.error('加载未命中问题失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [status, reloadKey])

  const reload = () => { setLoading(true); setReloadKey(k => k + 1) }

  const handleConvert = async () => {
    if (!convertId) return
    setConverting(true)
    try {
      const res = await convertUnanswered(convertId)
      toast.success(`已生成 FAQ 草稿 #${res.faq_id}`)
      setConvertId(null)
      reload()
    } catch {
      toast.error('转换失败')
    } finally {
      setConverting(false)
    }
  }

  const markResolved = async (id: number) => {
    try { await updateUnanswered(id, 'resolved'); reload() } catch { toast.error('操作失败') }
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">未命中问题</h1>
          <p className="text-sm text-muted-foreground mt-1">低置信度问答，可一键转为 FAQ</p>
        </div>
        <Button variant="outline" onClick={reload}><RefreshCw className="mr-2 h-4 w-4" />刷新</Button>
      </div>

      <div className="flex gap-2">
        {[{ v: '', l: '全部' }, { v: 'pending', l: '待处理' }, { v: 'converted', l: '已转FAQ' }, { v: 'resolved', l: '已解决' }].map(o => (
          <Button key={o.v} size="sm" variant={status === o.v ? 'default' : 'outline'} onClick={() => { setLoading(true); setStatus(o.v) }}>
            {o.l}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无记录</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>问题</TableHead>
                  <TableHead className="w-24">来源</TableHead>
                  <TableHead className="w-24">状态</TableHead>
                  <TableHead className="w-40 text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(r => (
                  <TableRow key={r.id}>
                    <TableCell className="text-sm">{r.question}</TableCell>
                    <TableCell><Badge variant="outline">{r.source}</Badge></TableCell>
                    <TableCell><Badge variant={r.status === 'pending' ? 'secondary' : 'default'}>{STATUS_LABEL[r.status] || r.status}</Badge></TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setConvertId(r.id)}>
                          <Sparkles className="mr-1 h-3 w-3" />转 FAQ
                        </Button>
                        {r.status === 'pending' && (
                          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => markResolved(r.id)}>
                            <CheckCircle2 className="mr-1 h-3 w-3" />标记解决
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={convertId !== null} onOpenChange={open => !open && setConvertId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>转为 FAQ</AlertDialogTitle>
            <AlertDialogDescription>系统将调用 AI 生成建议答案并创建一条 FAQ 草稿，确定继续吗？</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={converting}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleConvert} disabled={converting}>
              {converting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}确认转换
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
