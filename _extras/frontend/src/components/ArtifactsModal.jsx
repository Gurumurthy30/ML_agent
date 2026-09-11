import React, { useState, useEffect } from 'react';
import { X, FolderArchive, FileCode, Download, Check, Box } from 'lucide-react';

export default function ArtifactsModal({ isOpen, onClose, sessionId = 'default', experiments = [] }) {
  const [downloadingId, setDownloadingId] = useState(null);
  const [sessionLogs, setSessionLogs] = useState([]);

  useEffect(() => {
    if (isOpen && sessionId) {
      fetch(`/api/sessions/${sessionId}/log`)
        .then((res) => res.json())
        .then((data) => {
          if (data && data.experiments) {
            setSessionLogs(data.experiments);
          }
        })
        .catch((err) => console.warn('Could not fetch session log:', err));
    }
  }, [isOpen, sessionId]);

  if (!isOpen) return null;

  // Combine live experiments from hook with log entries from server
  const items = sessionLogs.length > 0 ? sessionLogs : experiments;

  const handleDownload = async (expId) => {
    setDownloadingId(expId);
    try {
      const res = await fetch(`/api/sessions/${sessionId}/artifacts/${expId}`);
      if (!res.ok) throw new Error('Artifact file not found');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${expId}_model.booster`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download error:', err);
      alert('Unable to download artifact from backend: ' + err.message);
    } finally {
      setTimeout(() => setDownloadingId(null), 1500);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center">
              <FolderArchive className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold text-primary">Session Artifacts</h2>
              <p className="text-xs text-muted">Trained models, deliverables, and validated pipelines</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Artifacts List */}
        <div className="overflow-y-auto py-4 space-y-3 flex-1 pr-1">
          {items.length === 0 ? (
            <div className="text-center py-10 text-xs text-muted font-sans space-y-2">
              <Box className="w-8 h-8 text-muted/50 mx-auto" />
              <p>No model artifacts generated yet in this session.</p>
              <p className="text-[11px] text-muted/70">
                Send a dataset or task instructions to start training models.
              </p>
            </div>
          ) : (
            items.map((art, idx) => {
              const expId = art.experiment_id || `exp_${String(idx + 1).padStart(3, '0')}`;
              const modelType = art.model_type || 'Trained Model';
              const cvMean = typeof art.cv_mean === 'number' ? art.cv_mean.toFixed(4) : '0.0000';
              const cvStd = typeof art.cv_std === 'number' ? art.cv_std.toFixed(4) : '0.0000';
              const isDownloading = downloadingId === expId;

              return (
                <div
                  key={idx}
                  className="bg-[#242321] border border-border/80 rounded-xl p-4 flex items-center justify-between gap-4 hover:border-border-strong transition-all"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="p-2 rounded-lg bg-[#181716] border border-border/60 flex-shrink-0">
                      <FileCode className="w-4 h-4 text-accent" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[13.5px] font-medium text-primary truncate">
                          {expId}_model.booster
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-border/40 text-muted">
                          {modelType}
                        </span>
                      </div>
                      <p className="text-xs text-muted mt-0.5 truncate">
                        {art.approach_summary || 'Standard pipeline model serialized to workspace.'}
                      </p>
                      <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-muted/70">
                        <span>CV: <span className="text-accent font-semibold">{cvMean}</span> (±{cvStd})</span>
                        <span>•</span>
                        <span className="text-success">{art.status || 'success'}</span>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => handleDownload(expId)}
                    disabled={isDownloading}
                    className="px-3 py-1.5 rounded-lg bg-border/40 hover:bg-border text-xs text-primary font-medium transition-colors flex items-center gap-1.5 flex-shrink-0 cursor-pointer disabled:opacity-50"
                    title="Download model file from backend"
                  >
                    {isDownloading ? (
                      <Check className="w-3.5 h-3.5 text-success" />
                    ) : (
                      <Download className="w-3.5 h-3.5 text-accent" />
                    )}
                    <span>{isDownloading ? 'Downloaded' : 'Download'}</span>
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-border/60 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-border/60 hover:bg-border text-xs text-primary font-medium transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
