import { useState, useRef, useEffect, useCallback } from 'react'
import './index.css'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TraceEvent {
  step: number
  type: 'thought' | 'tool_call' | 'tool_result' | 'tool_error' | 'final_result'
  content: string
}

interface HistoryTask {
  id: string
  user_id: string
  raw_input: string
  execution_status: string
  final_output: string | null
  created_at: string
  traces?: TraceEvent[]
}

type View = 'agent' | 'history'

const EXAMPLE_PROMPTS = [
  'What is the SHA-256 hash of today\'s date?',
  'Convert 98.6°F to Celsius',
  'Generate a secure 16-character password',
  'What day is 90 days from today?',
  'Pretty-print this JSON: {"name":"BMO","version":2}',
  'Calculate (3 + 5) * 2 and convert to uppercase',
  'Weather in Tokyo',
]

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('session_token'))
  const [authEmail, setAuthEmail] = useState(() => localStorage.getItem('auth_email') || '')
  const [loginEmail, setLoginEmail] = useState('')
  const [loginToken, setLoginToken] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  const [prompt, setPrompt] = useState('')
  const [traces, setTraces] = useState<TraceEvent[]>([])
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle')
  const [finalOutput, setFinalOutput] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryTask[]>([])
  const [selectedTask, setSelectedTask] = useState<HistoryTask | null>(null)
  const [view, setView] = useState<View>('agent')
  const [placeholderIdx, setPlaceholderIdx] = useState(0)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const eventSourceRef = useRef<EventSource | null>(null)
  const tracesEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    tracesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [traces])

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIdx(prev => (prev + 1) % EXAMPLE_PROMPTS.length)
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault()
        setSidebarOpen(prev => !prev)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks`)
      if (res.ok) setHistory(await res.json())
    } catch (err) {
      console.error('Failed to fetch history:', err)
    }
  }, [])

  const switchView = (v: View) => {
    setView(v)
    if (v === 'history') fetchHistory()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return

    setTraces([])
    setFinalOutput(null)
    setStatus('running')

    try {
      const res = await fetch(`${API_BASE}/api/task`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      })

      if (!res.ok) { setStatus('error'); return }
      const data = await res.json()
      startStreaming(data.task_id)
    } catch {
      setStatus('error')
    }
  }

  const startStreaming = (id: string) => {
    if (eventSourceRef.current) eventSourceRef.current.close()

    const eventSource = new EventSource(`${API_BASE}/api/task/${id}/stream`)
    eventSourceRef.current = eventSource

    eventSource.addEventListener('trace_update', (e) => {
      setTraces(prev => [...prev, JSON.parse(e.data)])
    })

    eventSource.addEventListener('final_result', (e) => {
      const data = JSON.parse(e.data)
      setFinalOutput(data.content)
      setStatus('completed')
      eventSource.close()
    })

    eventSource.onerror = () => {
      setStatus('error')
      eventSource.close()
    }
  }

  const inspectTask = async (task: HistoryTask) => {
    try {
      const res = await fetch(`${API_BASE}/api/task/${task.id}`)
      if (res.ok) setSelectedTask(await res.json())
    } catch (err) {
      console.error('Failed to fetch task details:', err)
    }
  }

  useEffect(() => {
    return () => { if (eventSourceRef.current) eventSourceRef.current.close() }
  }, [])

  const getTraceIcon = (type: string) => {
    const icons: Record<string, string> = {
      thought: 'TH',
      tool_call: 'TC',
      tool_result: 'OK',
      tool_error: 'ER',
      final_result: 'FN',
    }
    return icons[type] || '??'
  }

  const getTraceLabel = (type: string) => {
    const labels: Record<string, string> = {
      thought: 'REASONING',
      tool_call: 'TOOL INVOKE',
      tool_result: 'RESULT',
      tool_error: 'ERROR',
      final_result: 'COMPLETE',
    }
    return labels[type] || type.toUpperCase()
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError('')
    setLoginLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, token: loginToken }),
      })

      if (!res.ok) {
        const data = await res.json()
        setLoginError(data.detail || 'Authentication failed')
        setLoginLoading(false)
        return
      }

      const data = await res.json()
      localStorage.setItem('session_token', data.session_token)
      localStorage.setItem('auth_email', data.email)
      setAuthEmail(data.email)
      setIsAuthenticated(true)
    } catch {
      setLoginError('Connection error. Is the backend running?')
    }
    setLoginLoading(false)
  }

  const handleLogout = () => {
    localStorage.removeItem('session_token')
    localStorage.removeItem('auth_email')
    setIsAuthenticated(false)
    setAuthEmail('')
  }

  if (!isAuthenticated) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div className="login-header">
            <div className="brand-icon">B</div>
            <h1>BMO Agent</h1>
            <p className="login-subtitle">Authenticate to continue</p>
          </div>

          <form onSubmit={handleLogin} className="login-form">
            <div className="form-group">
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                value={loginEmail}
                onChange={e => setLoginEmail(e.target.value)}
                placeholder="your.email@example.com"
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="login-token">Access Token</label>
              <input
                id="login-token"
                type="password"
                value={loginToken}
                onChange={e => setLoginToken(e.target.value)}
                placeholder="Your access token"
                required
              />
            </div>

            {loginError && <div className="login-error">{loginError}</div>}

            <button type="submit" className="login-submit" disabled={loginLoading}>
              {loginLoading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          <div className="login-footer">
            <p>Contact your administrator for access credentials.</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`app-shell ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      <aside className={`sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="sidebar-brand">
          <div className="brand-icon">B</div>
          <div className="brand-text">
            <h1>BMO</h1>
            <span className="brand-tag">Agent Framework</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-btn ${view === 'agent' ? 'active' : ''}`}
            onClick={() => switchView('agent')}
          >
            <span className="nav-icon">&#9654;</span>
            <span className="nav-label">Execute</span>
          </button>
          <button
            className={`nav-btn ${view === 'history' ? 'active' : ''}`}
            onClick={() => switchView('history')}
          >
            <span className="nav-icon">&#9776;</span>
            <span className="nav-label">History</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className={`status-indicator ${status === 'running' ? 'pulse' : ''}`}>
            <span className="status-dot" />
            <span className="status-text">
              {status === 'running' ? 'Processing' : 'Ready'}
            </span>
          </div>
          <div className="sidebar-user">
            <span className="user-email">{authEmail}</span>
            <button className="logout-btn" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        {view === 'agent' && (
          <div className="agent-view">
            <div className="command-section">
              <form onSubmit={handleSubmit} className="command-bar">
                <div className="command-prefix">&gt;_</div>
                <input
                  id="task-input"
                  type="text"
                  className="command-input"
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={EXAMPLE_PROMPTS[placeholderIdx]}
                  disabled={status === 'running'}
                  autoFocus
                />
                <button
                  id="task-submit"
                  type="submit"
                  className="command-submit"
                  disabled={status === 'running' || !prompt.trim()}
                >
                  {status === 'running' ? (
                    <span className="spinner" />
                  ) : (
                    <span className="submit-arrow">&#8594;</span>
                  )}
                </button>
              </form>
            </div>

            {status === 'error' && (
              <div className="error-banner">
                Connection error. Ensure the backend is running on port 8000.
              </div>
            )}

            {(traces.length > 0 || status === 'running') && (
              <div className="timeline-container">
                <div className="timeline-header">
                  <span className="timeline-title">Execution Trace</span>
                  {status === 'running' && (
                    <span className="thinking-indicator">
                      <span className="thinking-dot" />
                      <span className="thinking-dot" />
                      <span className="thinking-dot" />
                    </span>
                  )}
                </div>

                <div className="timeline">
                  {traces.map((trace, i) => (
                    <div
                      key={i}
                      className={`timeline-item timeline-${trace.type}`}
                      style={{ animationDelay: `${i * 0.08}s` }}
                    >
                      <div className="timeline-connector">
                        <div className="timeline-node">
                          <span className="node-icon">{getTraceIcon(trace.type)}</span>
                        </div>
                        {i < traces.length - 1 && <div className="timeline-line" />}
                      </div>
                      <div className="timeline-body">
                        <div className="timeline-meta">
                          <span className="timeline-label">{getTraceLabel(trace.type)}</span>
                          <span className="timeline-step">#{trace.step}</span>
                        </div>
                        <div className="timeline-content">{trace.content}</div>
                      </div>
                    </div>
                  ))}
                  <div ref={tracesEndRef} />
                </div>
              </div>
            )}

            {finalOutput && (
              <div className="result-container">
                <div className="result-header">Output</div>
                <div className="result-body">{finalOutput}</div>
              </div>
            )}
          </div>
        )}

        {view === 'history' && (
          <div className="history-view">
            {selectedTask ? (
              <div className="task-detail-view">
                <button className="back-btn" onClick={() => setSelectedTask(null)}>
                  &#8592; Back to Dashboard
                </button>
                <div className="detail-card">
                  <div className="detail-header">
                    <span className={`status-badge status-${selectedTask.execution_status}`}>
                      {selectedTask.execution_status}
                    </span>
                    <span className="detail-time">
                      {new Date(selectedTask.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="detail-meta-row">
                    <span className="detail-uuid">Task: {selectedTask.id}</span>
                    {selectedTask.user_id && (
                      <span className="detail-uuid">User: {selectedTask.user_id}</span>
                    )}
                  </div>
                  <div className="detail-input">{selectedTask.raw_input}</div>

                  {selectedTask.final_output && (
                    <div className="result-container compact">
                      <div className="result-header">Output</div>
                      <div className="result-body">{selectedTask.final_output}</div>
                    </div>
                  )}

                  {selectedTask.traces && selectedTask.traces.length > 0 && (
                    <div className="timeline-container compact">
                      <div className="timeline">
                        {selectedTask.traces.map((trace, i) => (
                          <div key={i} className={`timeline-item timeline-${trace.type}`}>
                            <div className="timeline-connector">
                              <div className="timeline-node">
                                <span className="node-icon">{getTraceIcon(trace.type)}</span>
                              </div>
                              {i < (selectedTask.traces?.length ?? 0) - 1 && <div className="timeline-line" />}
                            </div>
                            <div className="timeline-body">
                              <div className="timeline-meta">
                                <span className="timeline-label">{getTraceLabel(trace.type)}</span>
                                <span className="timeline-step">#{trace.step}</span>
                              </div>
                              <div className="timeline-content">{trace.content}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <>
                {/* Dashboard Stats */}
                <div className="dashboard-header">
                  <h2 className="dashboard-title">Execution History</h2>
                  <span className="dashboard-count">{history.length} tasks</span>
                </div>

                <div className="stats-grid">
                  <div className="stat-card stat-total">
                    <div className="stat-value">{history.length}</div>
                    <div className="stat-label">Total Runs</div>
                  </div>
                  <div className="stat-card stat-success">
                    <div className="stat-value">
                      {history.filter(t => t.execution_status === 'completed').length}
                    </div>
                    <div className="stat-label">Completed</div>
                  </div>
                  <div className="stat-card stat-fail">
                    <div className="stat-value">
                      {history.filter(t => t.execution_status === 'failed').length}
                    </div>
                    <div className="stat-label">Failed</div>
                  </div>
                  <div className="stat-card stat-pending">
                    <div className="stat-value">
                      {history.filter(t => t.execution_status === 'pending' || t.execution_status === 'running').length}
                    </div>
                    <div className="stat-label">Pending</div>
                  </div>
                </div>

                {history.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">&#9671;</div>
                    <p>No tasks yet. Execute one from the Agent tab.</p>
                  </div>
                ) : (
                  <div className="dashboard-table-wrap">
                    <table className="dashboard-table">
                      <thead>
                        <tr>
                          <th>Status</th>
                          <th>Task ID</th>
                          <th>User</th>
                          <th>Question</th>
                          <th>Answer</th>
                          <th>Timestamp</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map(task => (
                          <tr key={task.id} className="dashboard-row" onClick={() => inspectTask(task)}>
                            <td>
                              <span className={`status-badge status-${task.execution_status}`}>
                                {task.execution_status}
                              </span>
                            </td>
                            <td className="cell-uuid" title={task.id}>
                              {task.id.slice(0, 8)}…
                            </td>
                            <td className="cell-uuid" title={task.user_id}>
                              {task.user_id ? task.user_id.slice(0, 8) + '…' : '—'}
                            </td>
                            <td className="cell-question">{task.raw_input}</td>
                            <td className="cell-answer">
                              {task.final_output
                                ? task.final_output.length > 80
                                  ? task.final_output.slice(0, 80) + '…'
                                  : task.final_output
                                : <span className="text-muted">—</span>}
                            </td>
                            <td className="cell-time">
                              {new Date(task.created_at).toLocaleString(undefined, {
                                month: 'short', day: 'numeric',
                                hour: '2-digit', minute: '2-digit'
                              })}
                            </td>
                            <td>
                              <button
                                className="delete-btn"
                                title="Delete task"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  if (confirm('Delete this task and all its traces?')) {
                                    fetch(`${API_BASE}/api/task/${task.id}`, { method: 'DELETE' })
                                      .then(() => fetchHistory())
                                  }
                                }}
                              >
                                ✕
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
