import React, { useState, useEffect } from 'react';

const steps = [
  { id: 'pending', label: '等待中', icon: '⏳' },
  { id: 'downloading', label: '影片下載', icon: '📥' },
  { id: 'analyzing', label: 'AI 分析', icon: '🧠' },
  { id: 'transcribing', label: '語音轉錄', icon: '✍️' },
  { id: 'completed', label: '完成', icon: '✅' }
];

function App() {
  const [url, setUrl] = useState('');
  const [genSubs, setGenSubs] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const startJob = async () => {
    if (!url) return;
    setError(null);
    setResult(null);
    setStatus('pending');

    try {
      const apiBase = `http://${window.location.hostname}:8000`;
      console.log('正在請求 API:', `${apiBase}/process`);
      const resp = await fetch(`${apiBase}/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, generate_subtitles: genSubs })
      });
      const data = await resp.json();
      if (resp.ok) {
        setJobId(data.job_id);
      } else {
        throw new Error(data.detail || '啟動失敗');
      }
    } catch (err) {
      console.error('API 請求失敗:', err);
      setError(`連線失敗: ${err.message} (請檢查 Console 查看詳細錯誤)`);
      setStatus('failed');
    }
  };

  useEffect(() => {
    let interval;
    if (jobId && (status !== 'completed' && status !== 'failed')) {
      interval = setInterval(async () => {
        try {
          const apiBase = `http://${window.location.hostname}:8000`;
          const resp = await fetch(`${apiBase}/status/${jobId}`);
          const data = await resp.json();
          setStatus(data.status);
          if (data.status === 'completed') {
            setResult(data.result);
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setError(data.error || '處理失敗');
            clearInterval(interval);
          }
        } catch (err) {
          console.error('輪詢出錯:', err);
          setError(`輪詢狀態失敗: ${err.message}`);
          clearInterval(interval);
          setStatus('failed');
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [jobId, status]);

  const currentStepIndex = steps.findIndex(s => s.id === status);

  return (
    <div className="container">
      <h1 className="title-gradient">YouTube 助手</h1>
      <p className="subtitle">AI 驅動的影片分析與字幕生成專家</p>

      <div className="glass-card">
        <div className="input-group">
          <input
            type="text"
            placeholder="請輸入 YouTube 影片網址..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={status !== 'idle' && status !== 'completed' && status !== 'failed'}
          />
          <button
            onClick={startJob}
            disabled={!url || (status !== 'idle' && status !== 'completed' && status !== 'failed')}
          >
            {status !== 'idle' && status !== 'completed' && status !== 'failed' ? '處理中...' : '開始分析'}
          </button>
        </div>

        <div className="checkbox-group">
          <input
            type="checkbox"
            id="subs"
            checked={genSubs}
            onChange={(e) => setGenSubs(e.target.checked)}
            disabled={status !== 'idle' && status !== 'completed' && status !== 'failed'}
          />
          <label htmlFor="subs">生成影片字幕 (使用 Faster Whisper)</label>
        </div>

        {status !== 'idle' && (
          <div className="status-section">
            <div className="progress-stepper">
              {steps.map((step, index) => (
                <div key={step.id} className={`step ${index === currentStepIndex ? 'active' : ''} ${index < currentStepIndex ? 'completed' : ''}`}>
                  <div className="step-icon">{step.icon}</div>
                  <span style={{ fontSize: '0.8rem', color: index <= currentStepIndex ? 'var(--text-main)' : 'var(--text-muted)' }}>{step.label}</span>
                </div>
              ))}
            </div>
            {error && <p style={{ color: '#f87171', textAlign: 'center' }}>{error}</p>}
          </div>
        )}
      </div>

      {result && (
        <div className="result-card glass-card">
          <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>
            {result.title}
          </h2>

          <div style={{ marginBottom: '2rem' }}>
            <h3 style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>影片描述</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{result.description}</p>
          </div>

          <div style={{ marginBottom: '2rem' }}>
            <h3 style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>標籤</h3>
            <div>
              {result.tags.split(',').map(tag => (
                <span key={tag} className="tag">#{tag.trim()}</span>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: '2rem' }}>
            <h3 style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>影片章節</h3>
            <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem' }}>
              {result.chapters.map((ch, i) => {
                const [time, name] = ch.split(' - ');
                return (
                  <div key={i} className="chapter-item">
                    <span className="chapter-time">{time}</span>
                    <span>{name}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {result.subtitles && (
            <div>
              <h3 style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>SRT 字幕</h3>
              <div className="subtitles-box">
                {result.subtitles}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
