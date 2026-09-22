import { useMemo } from 'react'
import { Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Shot {
  no: string
  scene: string
  line: string
  dur: string
}

interface StoryboardEditorProps {
  value: string
  onChange: (text: string) => void
}

function parseStoryboard(text: string): Shot[] {
  return text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const parts = line.split(/[|｜]/).map(s => s.trim())
      return { no: parts[0] || '', scene: parts[1] || '', line: parts[2] || '', dur: parts[3] || '' }
    })
}

function serializeStoryboard(shots: Shot[]): string {
  return shots.map(s => [s.no, s.scene, s.line, s.dur].join('|')).join('\n')
}

export function StoryboardEditor({ value, onChange }: StoryboardEditorProps) {
  const shots = useMemo(() => parseStoryboard(value), [value])

  const update = (i: number, patch: Partial<Shot>) => {
    const next = shots.map((s, j) => (j === i ? { ...s, ...patch } : s))
    onChange(serializeStoryboard(next))
  }

  const addRow = () => {
    const no = String(shots.length + 1)
    onChange(serializeStoryboard([...shots, { no, scene: '', line: '', dur: '' }]))
  }

  const removeRow = (i: number) => {
    onChange(serializeStoryboard(shots.filter((_, j) => j !== i)))
  }

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= shots.length) return
    const next = [...shots]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(serializeStoryboard(next))
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-xs text-muted-foreground">
              <th className="w-14 py-2 px-2 text-center font-medium">序号</th>
              <th className="py-2 px-2 text-left font-medium min-w-[160px]">画面描述</th>
              <th className="py-2 px-2 text-left font-medium min-w-[180px]">台词口播</th>
              <th className="w-20 py-2 px-2 text-center font-medium">时长(秒)</th>
              <th className="w-28 py-2 px-2 text-center font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {shots.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 text-center text-muted-foreground">
                  暂无镜头，点击「添加镜头」开始编排
                </td>
              </tr>
            )}
            {shots.map((s, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-1.5 px-2">
                  <Input
                    value={s.no}
                    onChange={e => update(i, { no: e.target.value })}
                    className="h-8 text-center"
                    placeholder="1"
                  />
                </td>
                <td className="py-1.5 px-2">
                  <Input
                    value={s.scene}
                    onChange={e => update(i, { scene: e.target.value })}
                    className="h-8"
                    placeholder="画面内容..."
                  />
                </td>
                <td className="py-1.5 px-2">
                  <Input
                    value={s.line}
                    onChange={e => update(i, { line: e.target.value })}
                    className="h-8"
                    placeholder="口播台词..."
                  />
                </td>
                <td className="py-1.5 px-2">
                  <Input
                    value={s.dur}
                    onChange={e => update(i, { dur: e.target.value })}
                    className="h-8 text-center"
                    placeholder="3"
                    type="number"
                    min={0}
                  />
                </td>
                <td className="py-1.5 px-2">
                  <div className="flex items-center justify-center gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" disabled={i === 0} onClick={() => move(i, -1)} title="上移">
                      <ArrowUp className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7" disabled={i === shots.length - 1} onClick={() => move(i, 1)} title="下移">
                      <ArrowDown className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive" onClick={() => removeRow(i)} title="删除">
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button variant="outline" size="sm" onClick={addRow}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        添加镜头
      </Button>
    </div>
  )
}
