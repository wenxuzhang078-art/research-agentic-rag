import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, KeyboardEvent, ReactNode } from 'react'
import {
  Activity, ArrowRight, ArrowUp, BookMarked, BookOpen, Bot, Check,
  ChevronDown, ChevronRight, CircleHelp, ClipboardCopy, Clock3, CloudUpload,
  Database, ExternalLink, FilePlus2, FileText, FolderOpen, GitBranch,
  Layers3, LoaderCircle, Menu, MessageCircle, Plus, Search, Server,
  Settings2, ShieldCheck, Sparkles, 
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import { chat, getDocuments, getStatus, uploadPdf } from './api.ts'
import type { ChatTurn, ChatResponse, DocumentItem, Mode, ServerStatus, Source } from './types.ts'

type View = 'chat' | 'library'

const EXAMPLES = [
  { title: '解析论文方法', body: '这篇 MVC 论文如何处理不同视图之间的一致性？', icon: Layers3 },
  { title: '追踪关键机制', body: '论文中的高层特征对比损失和聚类标签一致性有什么区别？', icon: Search },
  { title: '查找外部文献', body: '帮我查一下 Transformer 论文的作者，并给出原始来源。', icon: BookOpen },
]

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}

function safeLink(url: string | null): string | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null
  } catch { return null }
}

function Pill({ children, tone = 'neutral' }: { children: ReactNode, tone?: 'neutral' | 'blue' | 'green' | 'amber' }) {
  return <span className={`pill pill-${tone}`}>{children}</span>
}

function SourceItem({ source, open, toggle }: { source: Source, open: boolean, toggle: () => void }) {
  const url = safeLink(source.source_url)
  const rerank = source.score_type === 'rerank_relevance' && source.score != null
  return <div className={`source-card ${open ? 'expanded' : ''}`}>
    <button className="source-head" onClick={toggle} aria-expanded={open}>
      <div className="source-index">{source.index}</div>
      <div className="source-main">
        <div className="source-name" title={source.source}>{source.source}</div>
        <div className="source-tags">
          {source.page != null ? <span>第 {source.page} 页</span> : <span>{source.provider?.startsWith('mcp:') ? '外部学术文献' : '文献资料'}</span>}
          {rerank && <span>相关度 {source.score!.toFixed(3)}</span>}
        </div>
      </div>
      {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
    </button>
    {open && <div className="source-details">
      <p>{source.content || '该来源没有可展示的文本摘要。'}</p>
      <div className="source-actions">
        {url && <a href={url} target="_blank" rel="noreferrer">打开原始来源 <ExternalLink size={13} /></a>}
        {source.chunk_id && <span className="source-id">{source.chunk_id}</span>}
      </div>
    </div>}
  </div>
}

function TraceItem({ step, index }: { step: Record<string, unknown>, index: number }) {
  const node = String(step.node || `步骤 ${index + 1}`)
  const detail = step as { search_query?: string, reason?: string, calls?: unknown[], sufficient?: boolean, selected?: unknown[], missing?: unknown[], stats?: Record<string, unknown> }
  const descriptions: Record<string, string> = {
    plan: '问题分析与执行规划', act: '本地 RAG + ReAct 工具执行', grade: '分数预筛与 LLM 证据审核',
    replan: '根据缺失证据改写策略', generate: '整合证据并生成回答',
  }
  return <details className="trace-item">
    <summary>
      <span className="trace-count">{String(index + 1).padStart(2, '0')}</span>
      <span><strong>{node.toUpperCase()}</strong><small>{descriptions[node] || '执行节点'}</small></span>
      <ChevronDown size={15} className="trace-chevron" />
    </summary>
    <div className="trace-body">
      {detail.search_query && <div className="trace-property"><b>检索式</b><span>{detail.search_query}</span></div>}
      {detail.reason && <div className="trace-property"><b>原因</b><span>{detail.reason}</span></div>}
      {typeof detail.sufficient === 'boolean' && <Pill tone={detail.sufficient ? 'green' : 'amber'}>{detail.sufficient ? '证据充分' : '证据不足'}</Pill>}
      {Array.isArray(detail.calls) && <div className="trace-property"><b>调用工具</b><div>{detail.calls.map((call, i) => <pre className="compact-json" key={i}>{JSON.stringify(call, null, 2)}</pre>)}</div></div>}
      {Array.isArray(detail.missing) && detail.missing.length > 0 && <div className="trace-property"><b>缺失信息</b><span>{detail.missing.join('、')}</span></div>}
      {detail.stats && <div className="trace-property"><b>预筛统计</b><pre className="compact-json">{JSON.stringify(detail.stats, null, 2)}</pre></div>}
      {!detail.search_query && !detail.reason && !detail.calls && !detail.stats && <pre className="compact-json">{JSON.stringify(step, null, 2)}</pre>}
    </div>
  </details>
}

function MarkdownAnswer({ text }: { text: string }) {
  return <div className="markdown-body">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
      {text}
    </ReactMarkdown>
  </div>
}

function AnswerCard({ response, onShowSources }: { response: ChatResponse, onShowSources: () => void }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(response.answer); setCopied(true); setTimeout(() => setCopied(false), 1600) }
    catch { /* clipboard may be blocked by browser policy */ }
  }
  return <article className="answer-card">
    <div className="answer-card-header"><div className="assistant-avatar"><Sparkles size={17} /></div><div><strong>Research Atlas</strong><small>{response.mode === 'agent' ? 'Agentic RAG · LangGraph' : 'Hybrid RAG · RRF + Rerank'}</small></div></div>
    <MarkdownAnswer text={response.answer} />
    <div className="answer-footer">
      <button className="action-link" onClick={copy}>{copied ? <Check size={15} /> : <ClipboardCopy size={15} />}{copied ? '已复制' : '复制回答'}</button>
      {response.sources.length > 0 && <button className="action-link" onClick={onShowSources}><BookMarked size={15} /> {response.sources.length} 条引用证据 <ArrowRight size={13} /></button>}
      <span className="answer-time"><Clock3 size={13} /> {(response.duration_ms / 1000).toFixed(1)} 秒</span>
    </div>
  </article>
}

export default function App() {
  const [view, setView] = useState<View>('chat')
  const [mode, setMode] = useState<Mode>('agent')
  const [topK, setTopK] = useState(5)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<ServerStatus | null>(null)
  const [online, setOnline] = useState(false)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadInfo, setUploadInfo] = useState('')
  const [selectedResponse, setSelectedResponse] = useState<ChatResponse | null>(null)
  const [sourceOpen, setSourceOpen] = useState<number | null>(null)
  const [sidePanel, setSidePanel] = useState<'sources' | 'trace'>('sources')
  const [showMobileMenu, setShowMobileMenu] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const questionInput = useRef<HTMLTextAreaElement>(null)
  const scrollEnd = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getStatus().then(s => { setStatus(s); setOnline(true) }).catch(() => setOnline(false))
    getDocuments().then(d => setDocuments(d.documents)).catch(() => {})
  }, [])

  useEffect(() => { scrollEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [turns, busy])

  async function submit(text = question) {
    const trimmed = text.trim()
    if (!trimmed || busy) return
    const id = crypto.randomUUID()
    const currentMode = mode
    setTurns(previous => [...previous, { id, question: trimmed, mode: currentMode, createdAt: new Date() }])
    setQuestion('')
    setBusy(true)
    setView('chat')
    try {
      const response = await chat(trimmed, currentMode, topK)
      setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, response } : turn))
      setSelectedResponse(response)
      setSourceOpen(response.sources[0]?.index || null)
      setSidePanel('sources')
      setOnline(true)
    } catch (error) {
      setTurns(previous => previous.map(turn => turn.id === id ? { ...turn, error: error instanceof Error ? error.message : '未知错误' } : turn))
    } finally { setBusy(false) }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit() }
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || uploading) return
    if (!file.name.toLowerCase().endsWith('.pdf')) { setUploadInfo('请选择 PDF 文件'); return }
    if (status && file.size > status.max_pdf_mb * 1024 * 1024) { setUploadInfo(`文件不能超过 ${status.max_pdf_mb} MB`); return }
    setUploading(true)
    setUploadInfo(`正在解析并建立向量索引：${file.name}。此过程可能需要模型调用。`)
    try {
      const response = await uploadPdf(file)
      setUploadInfo(`入库完成：${response.result.pages} 页、${response.result.chunks} 个文本块`)
      const list = await getDocuments()
      setDocuments(list.documents)
    } catch (error) { setUploadInfo(`入库失败：${error instanceof Error ? error.message : '未知错误'}`) }
    finally { setUploading(false) }
  }

  const recent = turns.filter(item => item.response)

  return <div className="app-shell">
    <aside className={`sidebar ${showMobileMenu ? 'mobile-open' : ''}`}>
      <div className="logo-block"><div className="brand-symbol"><Layers3 size={21} /></div><div><strong>RESEARCH ATLAS</strong><small>AI Literature Workspace</small></div></div>
      <div className="workspace-label">工作空间 <span className="tiny-dot" /></div>
      <button className="new-chat" onClick={() => { setTurns([]); setSelectedResponse(null); setView('chat'); setShowMobileMenu(false); questionInput.current?.focus() }}><Plus size={17} /> 新建研究对话 <span>⌘ K</span></button>
      <div className="side-group-label">工作台</div>
      <nav className="side-nav">
        <button className={view === 'chat' ? 'active' : ''} onClick={() => { setView('chat'); setShowMobileMenu(false) }}><MessageCircle size={17} /> 科研问答 <span className="nav-selected" /></button>
        <button className={view === 'library' ? 'active' : ''} onClick={() => { setView('library'); setShowMobileMenu(false) }}><FolderOpen size={17} /> 文献知识库 <span className="count-badge">{documents.length}</span></button>
      </nav>
      <div className="side-group-label gap-top">近期会话 <span>仅本次页面</span></div>
      <div className="recent-list">
        {recent.length === 0 ? <div className="empty-recent">暂无研究记录</div> : recent.slice(-5).reverse().map(item => <button key={item.id} onClick={() => { setView('chat'); setSelectedResponse(item.response || null); setShowMobileMenu(false) }}><FileText size={15} /> <span>{item.question}</span></button>)}
      </div>
      <div className="sidebar-bottom">
        <div className="system-card"><span className="system-icon"><Server size={17} /></span><div><strong>本地研究引擎</strong><small>{status?.mcp_status === 'connected' ? `MCP · ${status.mcp_tools.length} 个工具` : 'Milvus · Qwen · LangGraph'}</small></div><span className={`status-light ${online ? 'on' : ''}`} /></div>
        <div className="sidebar-foot"><span>MVC Research Agent</span><span>v1.0</span></div>
      </div>
    </aside>
    {showMobileMenu && <button className="mobile-scrim" aria-label="关闭菜单" onClick={() => setShowMobileMenu(false)} />}

    <main className="main-area">
      <header className="topbar">
        <div className="top-left"><button className="menu-toggle" onClick={() => setShowMobileMenu(true)} aria-label="打开侧边栏"><Menu size={20} /></button><span className="breadcrumb-root">Research Workspace</span><ChevronRight size={14} /><strong>{view === 'chat' ? '科研智能问答' : '文献知识库'}</strong></div>
        <div className="top-right"><span className={`online-label ${online ? '' : 'offline'}`}><span className="status-light on" />{online ? '服务运行中' : '服务未连接'}</span><span className="top-divider" /><Pill tone="blue"><ShieldCheck size={12} /> LOCAL</Pill></div>
      </header>

      {view === 'chat' ? <div className="chat-layout">
        <section className="chat-main">
          <div className="chat-content">
            {turns.length === 0 ? <div className="welcome">
              <div className="eyebrow"><span className="eyebrow-line" /> YOUR RESEARCH CO-PILOT</div>
              <h1>从论文出发，<br /><em>探索更深的答案。</em></h1>
              <p className="welcome-description">以可信文献为依据，让科研探索变得更清晰。融合向量检索、知识重排与多工具 Agent 工作流。</p>
              <div className="capabilities"><Pill><Database size={13} /> Hybrid RAG</Pill><Pill><GitBranch size={13} /> LangGraph Agent</Pill><Pill><Sparkles size={13} /> MCP Tools</Pill></div>
              <div className="prompt-section-heading"><span>探索一些研究问题</span><span className="subtle-sun">✳</span></div>
              <div className="prompt-grid">{EXAMPLES.map(item => <button key={item.title} onClick={() => { setQuestion(item.body); questionInput.current?.focus() }} className="prompt-card"><span className="prompt-icon"><item.icon size={18} /></span><strong>{item.title}</strong><p>{item.body}</p><ArrowUp className="prompt-arrow" size={16} /></button>)}</div>
            </div> : <div className="conversation">
              {turns.map(turn => <div className="conversation-turn" key={turn.id}>
                <div className="user-message"><div className="user-bubble">{turn.question}</div><div className="user-avatar">U</div></div>
                {turn.response ? <AnswerCard response={turn.response} onShowSources={() => { setSelectedResponse(turn.response || null); setSidePanel('sources'); setSourceOpen(turn.response?.sources[0]?.index ?? null) }} /> : turn.error ? <div className="message-error"><CircleHelp size={17} /><span>{turn.error}</span></div> : <div className="thinking"><LoaderCircle size={19} className="spin" /><div><strong>正在检索与分析</strong><small>{turn.mode === 'agent' ? 'Agent 正在规划、调用工具和评估证据…' : '正在执行 Hybrid RAG、RRF 和 Rerank…'}</small></div></div>}
              </div>)}
              <div ref={scrollEnd} />
            </div>}
          </div>
          <div className="composer-outer"><div className="composer-shell"><div className="composer-header">
            <div className="mode-switch" role="group" aria-label="问答模式"><button className={mode === 'agent' ? 'selected' : ''} onClick={() => setMode('agent')}><Bot size={15} /> Agent 模式</button><button className={mode === 'rag' ? 'selected' : ''} onClick={() => setMode('rag')}><Database size={15} /> RAG 模式</button></div>
            <label className="topk-setting"><Settings2 size={14} /> Top K <select aria-label="检索来源数量" value={topK} onChange={event => setTopK(Number(event.target.value))} disabled={mode !== 'rag'}><option value={3}>3</option><option value={5}>5</option><option value={8}>8</option><option value={10}>10</option></select></label>
          </div><div className="composer-main"><textarea ref={questionInput} placeholder="输入关于论文、方法、实验或外部文献的问题…" value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={onKeyDown} rows={2} maxLength={2000} disabled={busy} aria-label="科研问题" /><button className="send-button" onClick={() => void submit()} disabled={!question.trim() || busy} aria-label="发送问题">{busy ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button></div></div><div className="composer-caption"><span><ShieldCheck size={13} /> 基于证据作答 · 请核对原始文献</span><span>Enter 发送 · Shift + Enter 换行</span></div></div>
        </section>
        <aside className="insights-panel"><div className="insights-header"><div><div className="panel-eyebrow">RESEARCH INSIGHTS</div><h3>证据与执行记录</h3></div><Activity size={18} /></div>
          <div className="panel-tabs"><button className={sidePanel === 'sources' ? 'current' : ''} onClick={() => setSidePanel('sources')}>引用来源 {selectedResponse ? `(${selectedResponse.sources.length})` : ''}</button><button className={sidePanel === 'trace' ? 'current' : ''} onClick={() => setSidePanel('trace')}>执行轨迹</button></div>
          <div className="panel-body">{!selectedResponse ? <div className="panel-empty"><span><BookMarked size={23} /></span><h4>证据即将呈现</h4><p>开始一次研究问答，即可查看引用片段、论文来源与 Agent 的推理执行步骤。</p></div> : sidePanel === 'sources' ? <>{selectedResponse.sources.length === 0 ? <div className="panel-empty"><BookOpen size={25} /><h4>暂无有效证据</h4><p>当前结果没有通过证据审核的来源。</p></div> : <div className="source-list">{selectedResponse.sources.map(source => <SourceItem key={`${source.chunk_id}-${source.index}`} source={source} open={sourceOpen === source.index} toggle={() => setSourceOpen(sourceOpen === source.index ? null : source.index)} />)}</div>}</> : selectedResponse.steps.length ? <div className="trace-list">{selectedResponse.steps.map((step, i) => <TraceItem key={i} step={step} index={i} />)}</div> : <div className="panel-empty"><GitBranch size={25} /><h4>无 Agent 轨迹</h4><p>使用 Agent 模式后，这里将展示 Plan、Act、Grade、Replan 的节点记录。</p></div>}</div>
          <div className="insights-footer"><span>RAG 证据与外部 MCP 证据分开标识</span><span><Clock3 size={12} /> {selectedResponse ? `${(selectedResponse.duration_ms / 1000).toFixed(1)}s` : '—'}</span></div>
        </aside>
      </div> : <section className="library-screen"><div className="library-hero"><div className="eyebrow"><span className="eyebrow-line" /> KNOWLEDGE BASE</div><h1>构建你的<span>科研知识库。</span></h1><p>上传英文或中文 PDF 论文，自动解析文本、生成 Embedding 并写入 Milvus Hybrid Collection。</p></div>
          <div className="library-grid"><div className="library-col"><div className="upload-card"><div className="upload-symbol"><CloudUpload size={28} /></div><h2>上传学术论文</h2><p>PDF 解析 → 文本分块 → 向量化 → Milvus 入库</p><input ref={fileInput} type="file" accept=".pdf,application/pdf" hidden onChange={onUpload} /><button className="primary-action" disabled={uploading} onClick={() => fileInput.current?.click()}>{uploading ? <LoaderCircle size={17} className="spin" /> : <FilePlus2 size={17} />}{uploading ? '正在入库…' : '选择 PDF 文件'}</button><small>最大 {status?.max_pdf_mb ?? 20} MB · 入库可能需要数十秒或更久</small>{uploadInfo && <div className="upload-status" role="status">{uploadInfo}</div>}</div><div className="info-card"><h3><CircleHelp size={18} /> 工作方式</h3><p>文档上传后使用既有 <code>ingest_pdf()</code>，写入 <strong>mvc_hybrid_1024</strong>。图表、扫描件和复杂公式的解析质量仍取决于 PDF 文本层。</p></div></div><div className="library-col"><div className="documents-panel"><div className="documents-head"><div><h2>服务器上的 PDF</h2><p>仅展示 data/papers 文件，不代表 Milvus 全部已有记录</p></div><Pill tone="blue">{documents.length} 文件</Pill></div>{documents.length ? <div className="document-list">{documents.map(doc => <div className="document-row" key={doc.filename}><span className="pdf-icon"><FileText size={18} /></span><div className="document-info"><strong title={doc.filename}>{doc.filename}</strong><small>{formatBytes(doc.size_bytes)} · {new Date(doc.modified_at).toLocaleDateString('zh-CN')}</small></div><Check size={16} className="doc-check" /></div>)}</div> : <div className="document-empty"><BookOpen size={30} /><h4>还没有服务器端 PDF 文件</h4><p>上传一篇论文即可开始建立自己的研究知识库。</p></div>}</div></div></div>
        </section>}
    </main>
  </div>
}
