import React, { useState } from 'react';
import {
  Download,
  FileCode,
  Check,
  ExternalLink,
  Cpu,
  BarChart2,
  Box,
  Copy,
  ChevronRight,
} from 'lucide-react';

export default function ArtifactCard({ artifact }) {
  const [downloaded, setDownloaded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [viewScript, setViewScript] = useState(false);

  if (!artifact) return null;

  const handleDownload = async () => {
    try {
      const expId = artifact.experiment_id || artifact.id || 'exp_001';
      const sessId = artifact.session_id || 'default';
      const downloadUrl = `/api/sessions/${sessId}/artifacts/${expId}`;

      const res = await fetch(downloadUrl);
      if (!res.ok) {
        throw new Error(`Artifact download returned status ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact.filename || `${expId}_model.booster`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setDownloaded(true);
      setTimeout(() => setDownloaded(false), 2500);
    } catch (err) {
      console.error('Artifact download failed:', err);
      alert('Unable to download artifact from backend: ' + err.message);
    }
  };

  const handleCopyCode = () => {
    if (artifact.codeSnippet) {
      navigator.clipboard.writeText(artifact.codeSnippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="my-4 rounded-xl border border-border bg-[#242321] overflow-hidden shadow-lg select-text transition-all">
      {/* Top Bar / Card Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1D1C1B] border-b border-border/70">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center flex-shrink-0">
            <Box className="w-4 h-4 text-accent" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[13.5px] font-semibold text-primary truncate">
                {artifact.name}
              </span>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-border/50 text-muted border border-border/60">
                {artifact.type || 'Model Weights'}
              </span>
            </div>
            <div className="text-[11.5px] text-muted truncate">
              {artifact.description || 'Deliverable ready for production inference'}
            </div>
          </div>
        </div>

        {/* Primary Download Button */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-medium transition-all shadow-sm cursor-pointer active:scale-95"
            title="Download model file"
          >
            {downloaded ? <Check className="w-3.5 h-3.5" /> : <Download className="w-3.5 h-3.5" />}
            <span>{downloaded ? 'Downloaded!' : 'Download (.booster)'}</span>
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      {artifact.metrics && (
        <div className="px-4 py-2.5 bg-[#201F1D] border-b border-border/50 flex flex-wrap items-center gap-3 text-xs">
          <span className="text-muted/70 uppercase tracking-wider text-[10.5px] font-mono">
            Validated Metrics:
          </span>
          {Object.entries(artifact.metrics).map(([key, val], idx) => (
            <div
              key={idx}
              className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#181716] border border-border/40 font-mono text-[11.5px]"
            >
              <span className="text-muted">{key}:</span>
              <span className="text-accent font-semibold">{val}</span>
            </div>
          ))}
          {artifact.size && (
            <div className="ml-auto text-muted font-mono text-[11.5px]">
              Size: {artifact.size}
            </div>
          )}
        </div>
      )}

      {/* Secondary Actions Row */}
      <div className="p-3 bg-[#242321] flex flex-wrap items-center gap-2 text-xs">
        {artifact.codeSnippet && (
          <button
            onClick={() => setViewScript(!viewScript)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#181716] hover:bg-[#2D2C2A] border border-border/70 text-muted hover:text-primary transition-colors cursor-pointer"
          >
            <FileCode className="w-3.5 h-3.5 text-accent" />
            <span>{viewScript ? 'Hide inference code' : 'View inference code'}</span>
            <ChevronRight className={`w-3 h-3 transition-transform ${viewScript ? 'rotate-90' : ''}`} />
          </button>
        )}

        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#181716] hover:bg-[#2D2C2A] border border-border/70 text-muted hover:text-primary transition-colors cursor-pointer"
        >
          <Cpu className="w-3.5 h-3.5 text-muted/80" />
          <span>Export ONNX Runtime</span>
        </button>

        <button
          onClick={() => alert("TreeSHAP summary interactive feature attribution view is available in Artifacts modal.")}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#181716] hover:bg-[#2D2C2A] border border-border/70 text-muted hover:text-primary transition-colors cursor-pointer"
        >
          <BarChart2 className="w-3.5 h-3.5 text-muted/80" />
          <span>Feature Importance (TreeSHAP)</span>
        </button>
      </div>

      {/* Collapsible Python Inference Code */}
      {viewScript && artifact.codeSnippet && (
        <div className="border-t border-border/60 bg-[#181716] p-3 text-xs font-mono">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/40 text-muted">
            <span>Inference Code Snippet (Python)</span>
            <button
              onClick={handleCopyCode}
              className="flex items-center gap-1 hover:text-primary transition-colors cursor-pointer"
            >
              {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <pre className="text-[#C8C7C3] overflow-x-auto terminal-scroll leading-relaxed p-1">
            {artifact.codeSnippet}
          </pre>
        </div>
      )}
    </div>
  );
}
