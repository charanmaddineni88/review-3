import { useEffect, useMemo, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { AreaChart, Area, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import LiveMap from './components/LiveMap'

const API = import.meta.env.VITE_API_BASE_URL || ''
const nav = [
  ['/', '⌂', 'Command Center'],
  ['/map', '⌖', 'Live Map'],
  ['/fires', '🔥', 'Fire Events'],
  ['/environment', '☁', 'Environment'],
  ['/spread', '↗', 'Spread Prediction'],
  ['/alerts', '!', 'Alerts'],
  ['/analytics', '⌁', 'Analytics'],
  ['/system', '⚙', 'System'],
]

async function getJSON(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

function useDashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [live, setLive] = useState(false)
  const load = async () => {
    try { setData(await getJSON('/api/dashboard/summary')); setError('') }
    catch (e) { setError(e.message) }
  }
  useEffect(() => {
    load()
    const wsBase = API ? API.replace(/^http/, 'ws') : `ws://${window.location.host}`
    const ws = new WebSocket(`${wsBase}/ws/live`)
    ws.onopen = () => { setLive(true); ws.send('subscribe') }
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'live_update') {
          setData(prev => prev ? {
            ...prev,
            timestamp: msg.timestamp,
            environment: msg.environment || prev.environment,
            satellite_fires: msg.satellite?.fires || prev.satellite_fires || [],
            satellite_meta: msg.satellite ? Object.fromEntries(Object.entries(msg.satellite).filter(([k]) => k !== 'fires')) : prev.satellite_meta,
            live: { ...prev.live, timestamp: msg.timestamp, sources: {
              ...prev.live?.sources,
              weather: msg.environment?.status || prev.live?.sources?.weather,
              air_quality: msg.environment?.air_quality_status || prev.live?.sources?.air_quality,
              terrain: msg.terrain?.terrain_status || prev.live?.sources?.terrain,
              satellite: msg.satellite?.satellite_status || prev.live?.sources?.satellite,
            }},
            providers: {
              ...prev.providers,
              satellite: msg.satellite?.satellite_status || prev.providers?.satellite,
              terrain: msg.terrain?.terrain_status || prev.providers?.terrain,
            }
          } : prev)
        }
      } catch (_) {}
    }
    ws.onerror = () => setLive(false)
    ws.onclose = () => setLive(false)
    const id = setInterval(load, 60000)
    return () => { clearInterval(id); ws.close() }
  }, [])
  return { data, error, live, refresh: load }
}

function dashboardLive(data) { return data?.live?.timestamp && data?.health?.status === 'healthy' }

function Shell({ children, data, error }) {
  const location = useLocation()
  const status = data?.health?.status === 'healthy'
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">ES</div><div><b>EcoSpread</b><span>YOLO COMMAND</span></div></div>
      <div className="status-pill"><i className={dashboardLive(data) ? 'dot live' : 'dot'} />{data?.health?.demo_mode ? 'DEMO MODE' : dashboardLive(data) ? 'LIVE DATA' : status ? 'API ONLINE' : 'API OFFLINE'}</div>
      <nav>{nav.map(([to, icon, label]) => <NavLink key={to} to={to} className={({isActive}) => isActive ? 'nav-link active' : 'nav-link'}><span>{icon}</span>{label}</NavLink>)}</nav>
      <div className="sidebar-footer">
        <div className="mini-source"><span>Model</span><b>{data?.model?.status || '—'}</b></div>
        <div className="mini-source"><span>Environment</span><b>{data?.environment?.status || '—'}</b></div>
        <small>Research prototype · evidence-first telemetry</small>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><span className="eyebrow">WILDFIRE INTELLIGENCE PLATFORM</span><h1>{nav.find(x => x[0] === location.pathname)?.[2] || 'EcoSpread-YOLO'}</h1></div>
        <div className="top-actions"><span className="fresh">Updated {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : '—'}</span><button onClick={() => window.location.reload()}>↻ Refresh</button></div>
      </header>
      {error && <div className="api-warning">API unavailable: {error}. The dashboard will not fabricate telemetry.</div>}
      {children}
    </main>
  </div>
}

function Stat({label, value, unit, tone=''}) {
  return <div className="stat-card"><span>{label}</span><strong className={tone}>{value ?? '—'}{value != null && unit ? <em>{unit}</em> : null}</strong></div>
}

function EnvironmentCards({env}) {
  const items = [
    ['Temperature', env?.temperature, '°C'], ['Humidity', env?.humidity, '%'], ['Wind speed', env?.wind_speed, 'km/h'],
    ['Wind direction', env?.wind_direction, '°'], ['Rainfall', env?.rainfall, 'mm'], ['Pressure', env?.pressure, 'hPa'],
    ['PM2.5', env?.pm25, 'µg/m³'], ['Visibility', env?.visibility, 'km']
  ]
  return <div className="metric-grid">{items.map(([l,v,u]) => <Stat key={l} label={l} value={v} unit={u}/>)}</div>
}

function RiskCard({risk=0, level='LOW'}) {
  return <div className="risk-card"><div className="risk-ring" style={{'--risk': `${risk}%`}}><div><strong>{Math.round(risk)}</strong><span>/100</span></div></div><div><span className="eyebrow">CURRENT FIRE RISK</span><h2>{level}</h2><p>Calculated only from available observations. Missing inputs remain unavailable.</p></div></div>
}

function EmptyState({title, text}) { return <div className="empty"><div className="empty-icon">◎</div><h3>{title}</h3><p>{text}</p></div> }

function CommandCenter({data}) {
  const env = data?.environment || {}
  const fire = data?.fires?.[0]
  const risk = fire?.risk_score || 0
  return <div className="page">
    <section className="hero-grid">
      <div className="panel video-panel">
        <div className="panel-head"><div><span className="eyebrow">LIVE UAV FEED</span><h2>{fire ? fire.camera_id : 'Camera stream'}</h2></div><span className="badge">{fire ? 'DETECTION ACTIVE' : 'NO ACTIVE DETECTION'}</span></div>
        <div className="video-stage"><div className="scanline"/><div className="video-center"><div className="camera-icon">◉</div><b>{fire ? 'Fire event detected' : 'Awaiting configured camera feed'}</b><span>{fire ? `${Math.round((fire.confidence || 0)*100)}% confidence` : 'Connect UAV/CCTV or upload an image for inference'}</span></div></div>
        <div className="video-meta"><span>Temporal verification: {fire ? 'ACTIVE' : 'IDLE'}</span><span>GPS: {fire?.latitude != null ? 'LOCKED' : 'UNAVAILABLE'}</span><span>Source: {fire?.source_type || '—'}</span></div>
      </div>
      <RiskCard risk={risk} level={fire?.risk_level || 'LOW'}/>
    </section>
    <section className="section"><div className="section-head"><div><span className="eyebrow">ENVIRONMENTAL INTELLIGENCE</span><h2>Live conditions</h2></div><span className="source-chip">{env.source || 'UNAVAILABLE'} · {env.freshness || 'UNAVAILABLE'}</span></div><EnvironmentCards env={env}/></section>
    <section className="dashboard-grid">
      <div className="panel">
        <div className="panel-head"><div><span className="eyebrow">FIRE RISK TIMELINE</span><h2>Observed risk trend</h2></div></div>
        <RiskTimeline data={data?.risk_history || []}/>
      </div>
      <div className="panel">
        <div className="panel-head"><div><span className="eyebrow">DATA SOURCES</span><h2>Trust & freshness</h2></div></div>
        <SourceList data={data}/>
      </div>
    </section>
  </div>
}

function RiskTimeline({data}) {
  if (!data?.length) return <EmptyState title="No risk history yet" text="Risk history appears after real fire events or risk observations are recorded."/>
  return <div className="chart"><ResponsiveContainer width="100%" height={260}><AreaChart data={data}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="time"/><YAxis domain={[0,100]}/><Tooltip/><Area type="monotone" dataKey="score" fillOpacity=".18" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
}

function SourceList({data}) {
  const rows = [
    ['YOLO model', data?.model?.status, data?.model?.device],
    ['Weather', data?.environment?.status, data?.environment?.source],
    ['Satellite / FIRMS', data?.providers?.satellite, data?.live?.sources?.satellite || 'Provider'],
    ['Terrain / DEM', data?.providers?.terrain, 'Provider'],
    ['Vegetation', data?.providers?.vegetation, 'Provider'],
    ['GPU', data?.gpu?.device, data?.gpu?.status],
  ]
  return <div className="source-list">{rows.map(([a,b,c]) => <div key={a}><span>{a}</span><b className={String(b).includes('UNAVAILABLE') ? 'muted' : ''}>{b || 'UNAVAILABLE'}</b><small>{c || '—'}</small></div>)}</div>
}

function SatelliteBanner({meta}) {
  if (!meta) return null
  const s = meta.satellite_status
  const msgs = {
    CONFIG_REQUIRED: 'NASA FIRMS hotspots are off: set FIREGUARD_FIRMS_MAP_KEY on the API server (free key). The NASA GIBS imagery layers above still work without a key.',
    INVALID_KEY: 'NASA FIRMS rejected the configured MAP_KEY. Check FIREGUARD_FIRMS_MAP_KEY.',
    RATE_LIMITED: 'NASA FIRMS rate limit reached; hotspots will refresh on the next successful poll.',
    UNAVAILABLE: `NASA FIRMS is unreachable${meta.satellite_message ? ': ' + meta.satellite_message : ''}.`,
    STALE: meta.satellite_message || 'Showing the last successful FIRMS refresh.',
    PARTIAL: meta.satellite_message || 'Some FIRMS satellite feeds failed.',
  }
  const text = msgs[s]
  const ok = ['LIVE','PARTIAL','STALE'].includes(s)
  return <div className={text ? 'api-warning' : 'notice'} style={{marginTop:12}}>
    {text || null}{text && ok ? ' ' : ''}
    {ok && <span>{meta.total_detections ?? 0} detections within {meta.radius_km ?? '—'} km · last {meta.days} day(s) · {(meta.sources || []).join(', ')} · fetched {meta.satellite_timestamp ? new Date(meta.satellite_timestamp).toLocaleTimeString() : '—'}</span>}
  </div>
}

function MapPage() {
  const {data} = useDashboard()
  const fire = data?.fires?.[0]
  return <div className="page"><section className="map-layout"><div className="panel map-panel"><div className="panel-head"><div><span className="eyebrow">GEOSPATIAL COMMAND</span><h2>Live operational map</h2></div><div className="layer-row"><span>🔥 Fire</span><span>🟠 FIRMS hotspot</span><span>🛰 NASA GIBS thermal</span><span>→ Wind</span></div></div><div className="map-canvas"><LiveMap location={data?.live?.location} radiusKm={data?.satellite_meta?.radius_km} fire={fire} satelliteFires={data?.satellite_fires || []} environment={data?.environment}/></div><SatelliteBanner meta={data?.satellite_meta}/></div><div className="panel"><span className="eyebrow">LAYERS</span><h2>Data availability</h2><div className="layer-list">{[['Current detection',!!fire],['FIRMS hotspots (API)',['LIVE','PARTIAL','STALE'].includes(data?.providers?.satellite)],['Terrain / DEM',data?.providers?.terrain==='LIVE'],['Vegetation / NDVI',data?.providers?.vegetation==='AVAILABLE'],['Monitoring site configured', data?.live?.location?.latitude != null],['NASA GIBS imagery (keyless)', true]].map(([x,on])=><div key={x}><i className={on?'dot live':'dot'}/><span>{x}</span><b>{on?'AVAILABLE':'UNAVAILABLE'}</b></div>)}</div></div></section></div>
}

function FiresPage() {
  const {data} = useDashboard()
  const fires = data?.fires || []
  return <div className="page"><div className="section-head"><div><span className="eyebrow">EVENT REGISTER</span><h2>Fire digital twin</h2></div><span className="source-chip">{fires.length} active events</span></div>{fires.length ? <div className="fire-table">{fires.map(f => <div className="fire-row" key={f.event_id}><div><b>{f.event_id}</b><small>{f.status} · {f.camera_id}</small></div><strong>{Math.round((f.confidence||0)*100)}%</strong><span>{f.visual_area_proxy != null ? `${Math.round(f.visual_area_proxy)} px² proxy` : 'Area proxy unavailable'}</span><span>{f.growth_rate != null ? `${f.growth_rate}%/min` : 'Growth unavailable'}</span><span className="risk-text">{f.risk_level || 'LOW'} · {Math.round(f.risk_score||0)}</span></div>)}</div> : <EmptyState title="No active fire events" text="This is a real-data view. Events will appear after a detector creates them; no synthetic events are shown."/>}</div>
}

function EnvironmentPage() {
  const {data} = useDashboard()
  return <div className="page"><div className="section-head"><div><span className="eyebrow">WEATHER + SENSOR FUSION</span><h2>Environmental intelligence</h2></div><span className="source-chip">{data?.environment?.message || data?.environment?.source || 'UNAVAILABLE'}</span></div><EnvironmentCards env={data?.environment}/><div className="panel"><div className="panel-head"><div><span className="eyebrow">HISTORY</span><h2>Environmental timeline</h2></div></div><RiskTimeline data={data?.environment_history?.map(x => ({time:new Date(x.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),score:x.temperature ?? 0})) || []}/><p className="disclaimer">The chart above is intentionally unavailable when no history has been collected. It does not substitute invented measurements.</p></div></div>
}

function SpreadPage() {
  const {data} = useDashboard(); const [horizon,setHorizon]=useState(30); const fire=data?.fires?.[0]
  return <div className="page"><div className="section-head"><div><span className="eyebrow">SHORT-HORIZON FORECAST</span><h2>Spread prediction</h2></div><div className="segmented">{[0,30,60].map(v=><button key={v} className={(horizon===v?'selected ':'')} onClick={()=>setHorizon(v)}>{v===0?'Current':`+${v} min`}</button>)}</div></div><div className="forecast-grid"><div className="panel forecast-map"><div className="map-canvas">{fire ? <LiveMap location={data?.live?.location} radiusKm={data?.satellite_meta?.radius_km} fire={fire} satelliteFires={data?.satellite_fires || []} environment={data?.environment} forecastMinutes={horizon}/> : <div className="map-empty"><b>Forecast unavailable</b><span>A confirmed fire event and forecasting inputs are required.</span></div>}</div></div><div className="panel"><span className="eyebrow">FORECAST STATUS</span><h2>{horizon===0?'Current observation':`+${horizon} minute horizon`}</h2><div className="forecast-facts"><div><span>Event</span><b>{fire?.event_id || 'UNAVAILABLE'}</b></div><div><span>Wind input</span><b>{data?.environment?.wind_speed != null ? `${data.environment.wind_speed} km/h` : 'UNAVAILABLE'}</b></div><div><span>Terrain</span><b>{data?.providers?.terrain || 'UNAVAILABLE'}</b></div><div><span>Vegetation</span><b>{data?.providers?.vegetation || 'UNAVAILABLE'}</b></div><div><span>Forecast model</span><b>{fire ? 'CONFIGURED' : 'UNAVAILABLE'}</b></div></div><div className="notice">The shaded radius is a wind-speed-scaled visual estimate for orientation only, computed live from the current wind reading — it is not a validated fire-perimeter forecast, and nothing is drawn when there is no confirmed fire event or wind reading.</div></div></div></div>
}

function AlertsPage() { const {data}=useDashboard(); const alerts=data?.alerts||[]; return <div className="page"><div className="section-head"><div><span className="eyebrow">RESPONSE WORKFLOW</span><h2>Alert center</h2></div><span className="source-chip">{alerts.length} alerts</span></div>{alerts.length ? <div className="alerts">{alerts.map(a=><div className="alert-card" key={a.alert_id}><div className="alert-level">{a.level}</div><div><b>{a.title}</b><p>{a.message}</p><small>{new Date(a.created_at).toLocaleString()}</small></div></div>)}</div> : <EmptyState title="No alerts" text="Observation → early warning → warning → high risk → critical alerts will be generated from actual events."/>}</div> }

function AnalyticsPage() { const {data}=useDashboard(); const a=data?.analytics||{}; return <div className="page"><div className="section-head"><div><span className="eyebrow">RESEARCH METRICS</span><h2>System analytics</h2></div></div><div className="metric-grid"><Stat label="Total events" value={a.total_events}/><Stat label="Active events" value={a.active_events}/><Stat label="Alerts" value={a.alert_count}/><Stat label="Risk state" value={a.risk_level}/></div><div className="dashboard-grid"><div className="panel"><span className="eyebrow">MODEL PERFORMANCE</span><h2>Measured metrics only</h2><div className="facts"><div><span>mAP@50</span><b>{a.model_metrics?.mAP50 ?? 'NOT REPORTED'}</b></div><div><span>mAP@50:95</span><b>{a.model_metrics?.mAP50_95 ?? 'NOT REPORTED'}</b></div><div><span>Precision</span><b>{a.model_metrics?.precision ?? 'NOT REPORTED'}</b></div><div><span>Recall</span><b>{a.model_metrics?.recall ?? 'NOT REPORTED'}</b></div><div><span>FPS</span><b>{a.model_metrics?.fps ?? 'NOT REPORTED'}</b></div><div><span>Latency</span><b>{a.model_metrics?.latency_ms ?? 'NOT REPORTED'}</b></div></div></div><div className="panel"><span className="eyebrow">EXPLAINABILITY</span><h2>Why did risk change?</h2><EmptyState title="Waiting for event evidence" text="When a risk score exists, contributing factors such as confidence, persistence, growth, wind, temperature and humidity are displayed here." /></div></div></div> }

function SystemPage() { const {data}=useDashboard(); const g=data?.gpu||{}; return <div className="page"><div className="section-head"><div><span className="eyebrow">RUNTIME OBSERVABILITY</span><h2>System health</h2></div></div><div className="metric-grid"><Stat label="Device" value={g.device}/><Stat label="Precision" value={g.precision}/><Stat label="GPU utilization" value={g.gpu_utilization} unit="%"/><Stat label="GPU memory" value={g.gpu_memory?.used_mb != null ? `${g.gpu_memory.used_mb}/${g.gpu_memory.total_mb} MB` : '—'}/></div><div className="dashboard-grid"><div className="panel"><span className="eyebrow">MODEL RUNTIME</span><h2>{data?.model?.status || 'UNAVAILABLE'}</h2><div className="facts"><div><span>Weights</span><b>{data?.model?.model_path || 'NOT CONFIGURED'}</b></div><div><span>Device</span><b>{data?.model?.device || '—'}</b></div><div><span>Mode</span><b>{data?.health?.demo_mode ? 'DEMO' : 'LIVE / CONFIGURED'}</b></div></div></div><div className="panel"><span className="eyebrow">PROVIDERS</span><h2>Integration status</h2><SourceList data={data}/></div></div></div> }

function App() {
  const dashboard = useDashboard()
  return <BrowserRouter><Shell data={dashboard.data} error={dashboard.error}><Routes>
    <Route path="/" element={<CommandCenter data={dashboard.data}/>}/>
    <Route path="/map" element={<MapPage/>}/><Route path="/fires" element={<FiresPage/>}/>
    <Route path="/environment" element={<EnvironmentPage/>}/><Route path="/spread" element={<SpreadPage/>}/>
    <Route path="/alerts" element={<AlertsPage/>}/><Route path="/analytics" element={<AnalyticsPage/>}/><Route path="/system" element={<SystemPage/>}/>
  </Routes></Shell></BrowserRouter>
}
export default App
