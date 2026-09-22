import { useEffect, useState } from 'react'
import { Loader2, Search, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from 'sonner'
import { fetchOperations, exportOperationsUrl, type OperationLog, type OperationFilters } from '@/api/audit'

const PAGE_SIZE = 20

export function AuditLog() {
  const [rows, setRows] = useState<OperationLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<OperationFilters>({})
  const [draft, setDraft] = useState({ operator_name: '', operation_type: '', target_table: '' })

  useEffect(() => {
    let active = true
    fetchOperations({ ...filters, page, page_size: PAGE_SIZE })
      .then(res => { if (active) { setRows(res.items); setTotal(res.total) } })
      .catch(() => toast.error('加载操作日志失败'))
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [filters, page])

  const applyFilters = () => {
    setLoading(true)
    setPage(1)
    setFilters({
      operator_name: draft.operator_name || undefined,
      operation_type: draft.operation_type || undefined,
      target_table: draft.target_table || undefined,
    })
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">操作日志</h1>
          <p className="text-sm text-muted-foreground mt-1">系统操作审计记录</p>
        </div>
        <a href={exportOperationsUrl(filters)} target="_blank" rel="noopener noreferrer">
          <Button variant="outline"><Download className="mr-2 h-4 w-4" />导出 CSV</Button>
        </a>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1"><label className="text-xs text-muted-foreground">操作人</label><Input value={draft.operator_name} onChange={e => setDraft(d => ({ ...d, operator_name: e.target.value }))} className="w-40" /></div>
        <div className="space-y-1"><label className="text-xs text-muted-foreground">操作类型</label><Input value={draft.operation_type} onChange={e => setDraft(d => ({ ...d, operation_type: e.target.value }))} className="w-32" /></div>
        <div className="space-y-1"><label className="text-xs text-muted-foreground">目标表</label><Input value={draft.target_table} onChange={e => setDraft(d => ({ ...d, target_table: e.target.value }))} className="w-40" /></div>
        <Button onClick={applyFilters}><Search className="mr-2 h-4 w-4" />查询</Button>
        <Badge variant="secondary">{total} 条</Badge>
      </div>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="py-16 flex justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
          ) : rows.length === 0 ? (
            <p className="py-16 text-center text-sm text-muted-foreground">暂无日志</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>操作人</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>目标</TableHead>
                  <TableHead>IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map(r => (
                  <TableRow key={r.id}>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">{new Date(r.created_at).toLocaleString('zh-CN')}</TableCell>
                    <TableCell className="text-sm">{r.operator_name || '—'}</TableCell>
                    <TableCell><Badge variant="outline">{r.operation_type}</Badge></TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.target_table}{r.target_id ? `#${r.target_id}` : ''}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{r.ip_address || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {total > PAGE_SIZE && (
        <div className="flex justify-center items-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => { setLoading(true); setPage(p => p - 1) }}>上一页</Button>
          <span className="text-sm text-muted-foreground">第 {page} / {totalPages} 页</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => { setLoading(true); setPage(p => p + 1) }}>下一页</Button>
        </div>
      )}
    </div>
  )
}
