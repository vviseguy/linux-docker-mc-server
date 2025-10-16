import React from 'react'
import { Toaster, toast } from 'sonner'
import { Play, Square, RotateCcw } from 'lucide-react'
import './styles.css'

function useChat() {
    const [messages, setMessages] = React.useState<string[]>([])
    const wsRef = React.useRef<WebSocket | null>(null)
    const connectedRef = React.useRef(false)

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
        ws.onopen = () => { connectedRef.current = true; toast.success('Chat connected') }
        ws.onclose = () => { connectedRef.current = false; toast.error('Chat disconnected') }
    }, [])

    const send = React.useCallback((text: string) => {
        if (!text.trim()) return
        if (!connectedRef.current) {
            toast.error('Chat is not connected yet')
            return
        }
        try {
            wsRef.current?.send(text)
            toast.success('Message sent')
        } catch {
            toast.error('Failed to send message')
        }
    }, [])

    const disconnect = React.useCallback(() => {
        wsRef.current?.close()
        wsRef.current = null
    }, [])

    return { messages, connect, send, disconnect }
}

type Status = { running: boolean; online: boolean; status?: string; docker_available?: boolean }

function Badge({ label, kind }: { label: string; kind: 'ok' | 'warn' | 'err' | undefined }) {
    const cls = kind ? `badge ${kind}` : 'badge'
    return <span className={cls}>{label}</span>
}

export default function App() {
    const { messages, connect, send } = useChat()
    const [input, setInput] = React.useState('')
    const inputRef = React.useRef<HTMLInputElement | null>(null)
    const [xms, setXms] = React.useState(2)
    const [xmx, setXmx] = React.useState(4)
    const [adminToken, setAdminToken] = React.useState<string>(() => localStorage.getItem('adminToken') || '')
    const [status, setStatus] = React.useState<Status | null>(null)
    const [players, setPlayers] = React.useState<string[]>([])
    const [cfg, setCfg] = React.useState<any>(null)

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
    React.useEffect(() => {
        // focus input on load
        inputRef.current?.focus()
    }, [])

    // Poll server status and info
    React.useEffect(() => {
        let cancelled = false
        const tick = async () => {
            try {
                const [st, info, conf] = await Promise.all([
                    fetch('/api/server/status').then(r => r.json()),
                    fetch('/api/server/info').then(r => r.json()),
                    fetch('/api/config').then(r => r.json()),
                ])
                if (!cancelled) {
                    setStatus(st)
                    setPlayers(info.players ?? [])
                    setCfg(conf)
                }
            } catch {
                // ignore
            }
        }
        tick()
        const id = setInterval(tick, 5000)
        return () => { cancelled = true; clearInterval(id) }
    }, [])

    const dockerOk = status?.docker_available
    const running = !!status?.running
    const online = !!status?.online
    const statusLabel = online ? 'Online' : (running ? 'Starting...' : (status?.status ?? 'Stopped'))
    const statusKind: 'ok' | 'warn' | 'err' | undefined = online ? 'ok' : (running ? 'warn' : undefined)

    return (
        <div style={{ height: '100vh', display: 'grid', gridTemplateRows: '80px 1fr 56px', background: 'var(--bg2)', color: 'var(--text)' }}>
            <Toaster richColors position="top-right" />
            <header className="header" style={{ padding: '0 16px', borderBottom: '1px solid var(--border)' }}>
                <div className="header-row header-center"><h1 className="minecraft-title" style={{ fontSize: 18 }}>Minecraft Dashboard</h1></div>
                <div className="header-row" style={{ justifyContent: 'space-between' }}>
                    <div className="row" style={{ gap: 10 }}>
                        <Badge label={`Status: ${statusLabel}`} kind={statusKind} />
                        <Badge label={dockerOk ? 'Docker: ready' : 'Docker: unavailable'} kind={dockerOk ? 'ok' : 'err'} />
                        <div>Players: {players.length}</div>
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                        <div title="Admin token for protected API calls" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <input
                                placeholder="Admin token (optional)"
                                value={adminToken}
                                onChange={(e: any) => { setAdminToken(e.target.value); localStorage.setItem('adminToken', e.target.value) }}
                                className="input" style={{ width: 240 }}
                            />
                        </div>
                        <button title="Start server with current settings" onClick={() => { start().then(() => toast.message('Starting...')) }} className="btn green" disabled={!dockerOk}><Play size={18} /> Start</button>
                        <button title="Stop" onClick={() => { stop().then(() => toast.message('Stopping...')) }} className="btn red" disabled={!dockerOk}><Square size={18} /> Stop</button>
                        <button title="Restart" onClick={() => { restart().then(() => toast.message('Restarting...')) }} className="btn amber" disabled={!dockerOk}><RotateCcw size={18} /> Restart</button>
                    </div>
                </div>
            </header>

            <main className="grid grid-cols" style={{ padding: 12, alignItems: 'stretch' }}>
                <section className="panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    <div className="panel-title">Chat</div>
                    <div className="panel-body chat">
                        {!dockerOk && (
                            <div className="banner">
                                Docker is not available. Start Docker Desktop to run the server. You can still view info and chat history.
                            </div>
                        )}
                        <div className="chat-inner">
                            {messages.map((m, i) => (
                                <div key={i} style={{ marginBottom: 6 }}>
                                    <span>{m}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
                <aside className="panel sidebar" style={{ position: 'relative' }}>
                    <div className="panel-title">
                        <span className="title-text">Controls & Info</span>
                        <button
                            className="caret-btn"
                            onClick={(e) => {
                                const root = (e.currentTarget.closest('.panel') as HTMLElement)
                                const body = root.querySelector('.slide-content') as HTMLElement
                                const collapsed = body.classList.toggle('collapsed')
                                root.classList.toggle('collapsed', collapsed)
                                const caret = e.currentTarget.querySelector('.caret-icon') as HTMLElement
                                if (collapsed) {
                                    root.style.width = '48px'
                                    caret?.classList.add('caret-open')
                                } else {
                                    root.style.width = ''
                                    caret?.classList.remove('caret-open')
                                }
                            }}
                            aria-label="Toggle controls"
                        >
                            <span className="caret-icon">◀</span>
                        </button>
                    </div>
                    <div className="panel-body slide-wrap" style={{ fontSize: 14, color: 'var(--muted)' }}>
                        <div className="slide-content">
                            <div className="grid" style={{ gap: 8 }}>
                                <label title="Initial heap size (Xms)">Xms (GB)
                                    <input className="input" type="number" min={1} max={64} value={xms} onChange={(e: any) => setXms(Number(e.target.value))} />
                                </label>
                                <label title="Maximum heap size (Xmx)">Xmx (GB)
                                    <input className="input" type="number" min={1} max={64} value={xmx} onChange={(e: any) => setXmx(Number(e.target.value))} />
                                </label>
                                <small>These values override backend config for this start.</small>
                                <div style={{ height: 1, background: 'var(--border)', margin: '8px 0' }} />
                                <div>
                                    <div>Players ({players.length}): {players.join(', ') || '—'}</div>
                                    <div style={{ marginTop: 8 }}>
                                        <button
                                            title="Manual save (flush and commit/push)"
                                            onClick={async () => {
                                                const headers: Record<string, string> = {}
                                                if (adminToken) headers['X-Admin-Token'] = adminToken
                                                const r = await fetch('/api/server/save', { method: 'POST', headers })
                                                r.ok ? toast.success('Save requested') : toast.error('Save failed')
                                            }}
                                            className="btn cyan" disabled={!dockerOk}
                                        >Save Now</button>
                                    </div>
                                </div>
                                <div style={{ height: 1, background: 'var(--border)', margin: '8px 0' }} />
                                <div>
                                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Config</div>
                                    <div>Repo: {cfg?.repo?.url || '—'}</div>
                                    <div>Branch: {cfg?.repo?.branch || '—'}</div>
                                    <div>Path: {cfg?.repo?.path || '—'}</div>
                                    <div>RCON: {cfg?.rcon?.enable ? `${cfg?.rcon?.host}:${cfg?.rcon?.port}` : 'disabled'}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </aside>
            </main>

            <footer className="footer" style={{ display: 'flex', gap: 8, padding: 8 }}>
                <input
                    placeholder="Type to chat or run /command"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter' && input.trim()) { send(input); setInput('') } }}
                    className="input" style={{ flex: 1, padding: '8px 10px' }}
                    ref={inputRef}
                />
                <button onClick={() => { if (input.trim()) { send(input); setInput('') } }} className="btn">Send</button>
            </footer>
        </div>
    )
}
// end
