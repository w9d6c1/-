import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import { loginByPassword, sendCode, phoneLogin } from '@/api/auth'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, Smartphone, KeyRound } from 'lucide-react'

export function Login() {
  const [tab, setTab] = useState<'phone' | 'password'>('phone')

  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [countdown, setCountdown] = useState(0)
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const { login } = useAuth()
  const navigate = useNavigate()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (countdown > 0) {
      timerRef.current = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current)
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [countdown])

  const handleSendCode = async () => {
    if (!phone || phone.length < 11) {
      toast.error('请输入正确的手机号')
      return
    }
    if (countdown > 0) return

    setSending(true)
    try {
      const result = await sendCode(phone)
      if (result.code) {
        toast.success(`验证码：${result.code}`)
      } else {
        toast.success('验证码已发送')
      }
      setCountdown(60)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '发送失败'
      toast.error(msg)
    } finally {
      setSending(false)
    }
  }

  const handlePhoneLogin = async () => {
    if (!phone || !code) {
      toast.error('请输入手机号和验证码')
      return
    }
    setLoading(true)
    try {
      const result = await phoneLogin(phone, code)
      login(result.access_token, {
        id: result.user.id,
        username: result.user.username || result.user.phone || phone,
        role: result.user.role,
        department: result.user.department || '',
      })
      toast.success('登录成功')
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '登录失败'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true)
    try {
      const result = await loginByPassword({ username, password })
      login(result.access_token, {
        id: result.user.id,
        username: result.user.username,
        role: result.user.role,
        department: result.user.department || '',
      })
      toast.success('登录成功')
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '登录失败'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">企业知识库系统</CardTitle>
          <CardDescription>管理后台登录</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={tab} onValueChange={(v) => setTab(v as 'phone' | 'password')}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="phone" className="gap-1.5">
                <Smartphone className="h-4 w-4" />
                手机登录
              </TabsTrigger>
              <TabsTrigger value="password" className="gap-1.5">
                <KeyRound className="h-4 w-4" />
                密码登录
              </TabsTrigger>
            </TabsList>

            <TabsContent value="phone" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label htmlFor="phone">手机号</Label>
                <Input
                  id="phone"
                  type="tel"
                  maxLength={11}
                  placeholder="请输入手机号"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value.replace(/\D/g, ''))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="code">验证码</Label>
                <div className="flex gap-2">
                  <Input
                    id="code"
                    maxLength={6}
                    placeholder="6位验证码"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    className="flex-1"
                  />
                  <Button
                    variant="outline"
                    onClick={handleSendCode}
                    disabled={countdown > 0 || sending}
                    className="shrink-0 w-28"
                  >
                    {sending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : countdown > 0 ? (
                      `${countdown}s`
                    ) : (
                      '获取验证码'
                    )}
                  </Button>
                </div>
              </div>
              <Button
                className="w-full"
                disabled={loading || !phone || code.length < 6}
                onClick={handlePhoneLogin}
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                登录 / 注册
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                未注册的手机号验证后自动创建账号
              </p>
            </TabsContent>

            <TabsContent value="password" className="space-y-4 mt-4">
              <form onSubmit={handlePasswordLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">用户名</Label>
                  <Input
                    id="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="请输入用户名"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">密码</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="请输入密码"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  登 录
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
