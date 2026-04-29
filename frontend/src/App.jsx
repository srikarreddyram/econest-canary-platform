import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend
} from 'chart.js';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const API = 'http://127.0.0.1:5001';

const STAGE_MAP = [
  { name: 'Checkout', icon: '📦', key: 'Checkout' },
  { name: 'Install Deps', icon: '🔧', key: 'Install Dependencies' },
  { name: 'Verify DB', icon: '🗄️', key: 'Verify DB Structure' },
  { name: 'Canary 10%', icon: '🐤', key: 'Canary 10%' },
  { name: 'Risk Score', icon: '🤖', key: 'Evaluate Risk' },
  { name: 'Promote 50%', icon: '🚦', key: 'Promote 50%' },
  { name: 'Promote 100%', icon: '🚀', key: 'Promote 100%' },
];

const TRAFFIC_BY_STAGE = { 'Canary 10%': 10, 'Promote 50%': 50, 'Promote 100%': 100 };

function App() {
  const [repoUrl, setRepoUrl] = useState('https://github.com/srikarreddyram/econest-canary-platform.git');
  const [apiOnline, setApiOnline] = useState(false);
  const [chaos, setChaos] = useState(false);
  
  const [state, setState] = useState({
    stages: [], building: false, result: null, number: null, trafficPct: 0
  });
  
  const [metrics, setMetrics] = useState([]);
  const [consoleLog, setConsoleLog] = useState('Waiting for build...');
  const [history, setHistory] = useState([]);

  const consoleEndRef = useRef(null);

  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [consoleLog]);

  useEffect(() => {
    const socket = io(API);
    
    socket.on('connect', () => {
      setApiOnline(true);
      fetch(`${API}/api/history`).then(r => r.json()).then(setHistory).catch(console.error);
      fetch(`${API}/api/chaos/status`).then(r => r.json()).then(d => setChaos(d.chaos_mode)).catch(console.error);
    });

    socket.on('disconnect', () => setApiOnline(false));

    socket.on('status', (status) => {
      let traffic = 0;
      (status.stages || []).forEach(s => {
        if (s.status === 'SUCCESS' && TRAFFIC_BY_STAGE[s.name] !== undefined) {
          traffic = Math.max(traffic, TRAFFIC_BY_STAGE[s.name]);
        }
      });
      setState({
        building: status.building,
        result: status.result,
        number: status.number,
        stages: status.stages || [],
        trafficPct: traffic
      });
    });

    socket.on('metrics', (data) => {
      if (data && data.length > 0) {
        setMetrics([...data].sort((a, b) => a.timestamp - b.timestamp).slice(-20));
      }
    });

    socket.on('console', (c) => setConsoleLog(c.log || ''));
    
    socket.on('refresh', (data) => {
      if (data.type === 'history') {
        fetch(`${API}/api/history`).then(r => r.json()).then(setHistory).catch(console.error);
      }
    });

    socket.on('chaos_status', (data) => setChaos(data.chaos_mode));

    return () => socket.disconnect();
  }, []);

  const triggerDeploy = async () => {
    await fetch(`${API}/api/deploy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ repo_url: repoUrl })
    });
  };

  const triggerRollback = async () => {
    await fetch(`${API}/api/rollback`, { method: 'POST' });
  };

  const toggleChaos = async () => {
    await fetch(`${API}/api/chaos/toggle`, { method: 'POST' });
  };

  const chartData = {
    labels: metrics.map(m => new Date(m.timestamp * 1000).toLocaleTimeString()),
    datasets: [{
      label: 'Canary Latency (ms)',
      data: metrics.map(m => m.metrics.latency_p95 || 0),
      borderColor: '#45f3ff',
      backgroundColor: 'rgba(69, 243, 255, 0.1)',
      borderWidth: 2,
      fill: true,
      tension: 0.4
    }]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#8B949E' } },
      x: { grid: { display: false }, ticks: { color: '#8B949E' } }
    },
    plugins: { legend: { labels: { color: '#fff' } } },
    animation: { duration: 0 }
  };

  return (
    <div className="font-sans max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          🦅 Econest <span className="text-brand">Canary V4</span>
        </h1>
        <div className="flex gap-4 items-center">
          <span className={`px-4 py-1 rounded-full text-sm font-semibold border ${apiOnline ? 'bg-success/10 text-success border-success' : 'bg-danger/10 text-danger border-danger'}`}>
            {apiOnline ? 'API ONLINE' : 'API OFFLINE'}
          </span>
          <button 
            onClick={toggleChaos}
            className={`px-5 py-2 rounded-lg font-semibold border transition-all ${chaos ? 'bg-danger text-white border-danger shadow-[0_0_15px_rgba(255,0,85,0.5)]' : 'border-danger text-danger hover:bg-danger hover:text-white hover:shadow-[0_0_15px_rgba(255,0,85,0.5)]'}`}
          >
            {chaos ? '🔥 Disable Chaos Mode' : '🔥 Enable Chaos Mode'}
          </button>
        </div>
      </header>

      {/* Main Control Panel */}
      <div className="glass-panel mb-6">
        <div className="flex gap-4 mb-8">
          <input 
            type="text" 
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            className="flex-1 bg-black/30 border border-border-color rounded-lg px-4 py-3 text-white font-mono focus:outline-none focus:border-brand transition-colors"
          />
          <button onClick={triggerDeploy} className="px-6 py-3 rounded-lg font-semibold border border-brand text-brand hover:bg-brand hover:text-bg-dark hover:shadow-[0_0_15px_var(--brand-glow)] transition-all">
            🚀 Trigger Deployment
          </button>
          <button onClick={triggerRollback} className="px-6 py-3 rounded-lg font-semibold border border-danger text-danger hover:bg-danger hover:text-white hover:shadow-[0_0_15px_rgba(255,0,85,0.5)] transition-all">
            🛑 Abort & Rollback
          </button>
        </div>

        <div className="text-text-secondary uppercase tracking-widest text-sm font-semibold mb-4">
          Deployment Pipeline — Build <span className="text-white">#{state.number || '—'}</span> 
          <span className={`ml-3 ${state.building ? 'text-warning' : state.result === 'SUCCESS' ? 'text-success' : state.result === 'FAILURE' ? 'text-danger' : 'text-text-secondary'}`}>
            {state.building ? 'RUNNING…' : (state.result || '—')}
          </span>
        </div>
        
        {/* Pipeline Rail */}
        <div className="relative py-8 flex justify-between">
          <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-border-color z-0"></div>
          {STAGE_MAP.map((sm, idx) => {
            const jenkinsStage = state.stages.find(s => s.name === sm.key);
            let status = 'pending';
            if (jenkinsStage) {
              if (jenkinsStage.status === 'SUCCESS') status = 'success';
              else if (jenkinsStage.status === 'IN_PROGRESS') status = 'running';
              else if (jenkinsStage.status === 'FAILED') status = 'failed';
            }
            
            return (
              <div key={idx} className="relative z-10 flex flex-col items-center gap-3 w-20">
                <div className={`w-10 h-10 rounded-full bg-bg-dark border-2 flex items-center justify-center text-xl transition-all duration-300
                  ${status === 'success' ? 'border-success shadow-[0_0_15px_rgba(57,255,20,0.4)]' : 
                    status === 'running' ? 'border-brand shadow-[0_0_15px_var(--brand-glow)] animate-pulse' : 
                    status === 'failed' ? 'border-danger shadow-[0_0_15px_rgba(255,0,85,0.4)]' : 'border-border-color'}
                `}>
                  {sm.icon}
                </div>
                <div className={`text-xs text-center font-medium
                  ${status === 'success' ? 'text-success' : 
                    status === 'running' ? 'text-brand' : 
                    status === 'failed' ? 'text-danger' : 'text-text-secondary'}
                `}>
                  {sm.name}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Metrics & Traffic Grid */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="glass-panel flex flex-col justify-center items-center">
          <div className="text-text-secondary uppercase tracking-widest text-sm font-semibold mb-2">Live Canary Traffic</div>
          <div className="text-6xl font-extrabold text-brand drop-shadow-[0_0_20px_var(--brand-glow)] my-4">
            {state.trafficPct}%
          </div>
          <div className="text-text-secondary text-sm">Probabilistic Split Weight</div>
        </div>
        
        <div className="glass-panel h-64 flex flex-col">
          <div className="text-text-secondary uppercase tracking-widest text-sm font-semibold mb-4">Telemetry Chart (P95 Latency)</div>
          <div className="flex-1 relative w-full">
            <Line data={chartData} options={chartOptions} />
          </div>
        </div>
      </div>

      {/* Terminal & History */}
      <div className="grid grid-cols-2 gap-6">
        <div className="glass-panel">
          <div className="text-text-secondary uppercase tracking-widest text-sm font-semibold mb-4">Jenkins Live Console</div>
          <div className="bg-black rounded-lg p-4 border border-gray-800 font-mono text-success text-sm h-64 overflow-y-auto">
            <pre className="whitespace-pre-wrap break-words">{consoleLog}</pre>
            <div ref={consoleEndRef} />
          </div>
        </div>
        
        <div className="glass-panel">
          <div className="text-text-secondary uppercase tracking-widest text-sm font-semibold mb-4">Deployment History</div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border-color text-text-secondary text-sm font-medium">
                  <th className="pb-3 pl-2">ID</th>
                  <th className="pb-3">Status</th>
                  <th className="pb-3">Time</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 5).map((h, i) => (
                  <tr key={i} className="border-b border-border-color/50">
                    <td className="py-4 pl-2 font-mono">#{h.id.slice(-6)}</td>
                    <td className="py-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase
                        ${h.status === 'success' ? 'bg-success/10 text-success' : 
                          h.status === 'failed' ? 'bg-danger/10 text-danger' : 
                          'bg-brand/10 text-brand'}
                      `}>
                        {h.status}
                      </span>
                    </td>
                    <td className="py-4 text-text-secondary text-sm">{new Date(h.triggered).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
