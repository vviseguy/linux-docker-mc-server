import React from 'react'
import { Toaster, toast } from 'sonner'
import { Play, Square, RotateCcw } from 'lucide-react'

function useChat() {
    const [messages, setMessages] = React.useState<string[]>([])
    const wsRef = React.useRef<WebSocket | null>(null)

    const connect = React.useCallback(() => {
        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/chat/ws`)
        wsRef.current = ws
        ws.onmessage = (ev) => {
            const text = ev.data as string
            if (text.includes('Done (') && text.includes(')! For help, type')) {
                toast.success('Server is online')
            }
            setMessages((m) => [...m, text])
        }
        ws.onopen = () => toast.success('Chat connected')
        ws.onclose = () => toast.error('Chat disconnected')
    }, [])

    const send = React.useCallback((text: string) => {
        wsRef.current?.send(text)
    }, [])

    const disconnect = React.useCallback(() => {
        wsRef.current?.close()
        wsRef.current = null
    }, [])

    return { messages, connect, send, disconnect }
}

export default function App() {
    const { messages, connect, send } = useChat()
    const [input, setInput] = React.useState('')
    const [xms, setXms] = React.useState(2)
    const [xmx, setXmx] = React.useState(4)
    const [adminToken, setAdminToken] = React.useState<string>(() => localStorage.getItem('adminToken') || '')
    const [status, setStatus] = React.useState<{ running: boolean; online: boolean; status?: string } | null>(null)
    const [players, setPlayers] = React.useState<string[]>([])

    const start = async () => {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (adminToken) headers['X-Admin-Token'] = adminToken
        const res = await fetch('/api/server/start', { method: 'POST', headers, body: JSON.stringify({ xms_gb: xms, xmx_gb: xmx }) })
        if (!res.ok) {
            toast.error('Failed to start')
            return
        }
        const data = await res.json()
        toast.message('Starting server', {
            description: `Image: ${data.java_image}\nCmd: ${data.command.join(' ')}\nPorts: ${Object.keys(data.ports).join(', ')}`,
        })
    }
    const stop = async () => {
        const headers: Record<string, string> = {}
        if (adminToken) headers['X-Admin-Token'] = adminToken
        try {
            const info = await fetch('/api/server/info').then(r => r.json())
            const onlinePlayers: string[] = info.players ?? []
            let url = '/api/server/stop'
            if (onlinePlayers.length > 0) {
                const confirmStop = window.confirm(`Players online: ${onlinePlayers.join(', ')}. Force stop?`)
                if (!confirmStop) return
                url = '/api/server/stop?force=true'
            }
            const r = await fetch(url, { method: 'POST', headers })
            r.ok ? toast.success('Server stopping') : toast.error('Failed to stop')
        } catch (e) {
            toast.error('Failed to stop')
        }
    }
    const restart = async () => {
        const headers: Record<string, string> = {}
        if (adminToken) headers['X-Admin-Token'] = adminToken
        const r = await fetch('/api/server/restart', { method: 'POST', headers })
        r.ok ? toast.success('Server restarting') : toast.error('Failed to restart')
    }

    React.useEffect(() => {
        connect()
    }, [connect])

    // Poll server status and info
    React.useEffect(() => {
        let cancelled = false
        const tick = async () => {
            try {
                const [st, info] = await Promise.all([
                    fetch('/api/server/status').then(r => r.json()),
                    fetch('/api/server/info').then(r => r.json()),
                ])
                if (!cancelled) {
                    setStatus(st)
                    setPlayers(info.players ?? [])
                }
            } catch {
                // ignore
            }
        }
        tick()
        const id = setInterval(tick, 5000)
        return () => { cancelled = true; clearInterval(id) }
    }, [])

    return (
        <div style={{ height: '100vh', display: 'grid', gridTemplateRows: '56px 1fr 56px', background: '#0f172a', color: '#e2e8f0' }}>
            <Toaster richColors position="top-right" />
            <header style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px', borderBottom: '1px solid #1f2937' }}>
                <h1 style={{ fontSize: 18, fontWeight: 600 }}>Minecraft Dashboard</h1>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                    <div title="Admin token for protected API calls" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input
                            placeholder="Admin token (optional)"
                            value={adminToken}
                            onChange={(e: any) => { setAdminToken(e.target.value); localStorage.setItem('adminToken', e.target.value) }}
                            style={{ ...inputStyle(), width: 220 }}
                        />
                    </div>
                    <button title="Start server with current settings" onClick={start} style={btnStyle('#16a34a')}><Play size={18} /> Start</button>
                    <button title="Stop" onClick={stop} style={btnStyle('#dc2626')}><Square size={18} /> Stop</button>
                    <button title="Restart" onClick={restart} style={btnStyle('#f59e0b')}><RotateCcw size={18} /> Restart</button>
                </div>
            </header>

            <main style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 12, padding: 12 }}>
                <section style={{ border: '1px solid #1f2937', borderRadius: 8, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <div style={{ padding: 8, background: '#111827', borderBottom: '1px solid #1f2937' }}>Chat</div>
                    <div style={{ flex: 1, padding: 12, overflowY: 'auto' }}>
                        {messages.map((m, i) => (
                            <div key={i} style={{ marginBottom: 6 }}>
                                <span>{m}</span>
                            </div>
                        ))}
                    </div>
                </section>
                <aside style={{ border: '1px solid #1f2937', borderRadius: 8 }}>
                    <div style={{ padding: 8, background: '#111827', borderBottom: '1px solid #1f2937' }}>Panel</div>
                    <div style={{ padding: 12, fontSize: 14, color: '#94a3b8' }}>
                        <div style={{ display: 'grid', gap: 8 }}>
                            <label title="Initial heap size (Xms)">Xms (GB)
                                <input type="number" min={1} max={64} value={xms} onChange={(e: any) => setXms(Number(e.target.value))} style={inputStyle()} />
                            </label>
                            <label title="Maximum heap size (Xmx)">Xmx (GB)
                                <input type="number" min={1} max={64} value={xmx} onChange={(e: any) => setXmx(Number(e.target.value))} style={inputStyle()} />
                            </label>
                            <small>These values override backend config for this start.</small>
                            <div style={{ height: 1, background: '#1f2937', margin: '8px 0' }} />
                            <div>
                                <div>Status: {status ? (status.online ? 'Online' : (status.running ? 'Starting...' : 'Stopped')) : 'Unknown'}</div>
                                <div>Players ({players.length}): {players.join(', ')}</div>
                                <div style={{ marginTop: 8 }}>
                                    <button
                                        title="Manual save (flush and commit/push)"
                                        onClick={async () => {
                                            const headers: Record<string, string> = {}
                                            if (adminToken) headers['X-Admin-Token'] = adminToken
                                            const r = await fetch('/api/server/save', { method: 'POST', headers })
                                            r.ok ? toast.success('Save requested') : toast.error('Save failed')
                                        }}
                                        style={btnStyle('#0ea5e9')}
                                    >Save Now</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </aside>
            </main>

            <footer style={{ display: 'flex', gap: 8, padding: 8, borderTop: '1px solid #1f2937' }}>
                <input
                    placeholder="Type to chat or run /command"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && input.trim()) { send(input); setInput('') } }}
                    style={{ flex: 1, background: '#111827', color: '#e2e8f0', border: '1px solid #1f2937', borderRadius: 6, padding: '8px 10px' }}
                />
                <button onClick={() => { if (input.trim()) { send(input); setInput('') } }} style={btnStyle('#2563eb')}>Send</button>
            </footer>
        </div>
    )
}

function btnStyle(color: string): React.CSSProperties {
    return {
        display: 'inline-flex', alignItems: 'center', gap: 6,
        background: color, color: 'white', padding: '8px 12px',
        border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600
    }
}

function inputStyle(): React.CSSProperties {
    return {
        width: '100%',
        background: '#0b1220',
        color: '#e2e8f0',
        border: '1px solid #1f2937',
        borderRadius: 6,
        padding: '6px 8px',
        marginTop: 4,
    }
}
