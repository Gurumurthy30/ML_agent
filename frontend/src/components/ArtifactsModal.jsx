import React from 'react';
import { X, FolderArchive, FileCode, Database, Download, Check } from 'lucide-react';

export default function ArtifactsModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const artifacts = [
    {
      name: 'lgb_credit_v1.booster',
      type: 'Model Weights',
      size: '4.2 MB',
      created: '10:42 AM',
      description: 'Trained LightGBM booster with 5-fold out-of-fold validation scores.',
      metric: 'ROC-AUC 0.892',
    },
    {
      name: 'train_lightgbm_credit.py',
      type: 'Python Script',
      size: '6.8 KB',
      created: '10:42 AM',
      description: 'End-to-end training pipeline including StratifiedKFold and preprocessing.',
      metric: 'Exit code 0',
    },
    {
      name: 'shap_waterfall_importance.json',
      type: 'Explainability Export',
      size: '84 KB',
      created: '10:43 AM',
      description: 'Calculated TreeSHAP interaction metrics and base credit threshold values.',
      metric: '28 features',
    },
  ];

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
              <p className="text-xs text-muted">Generated models, scripts, and evaluation outputs</p>
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
          {artifacts.map((art, idx) => (
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
                      {art.name}
                    </span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-border/40 text-muted">
                      {art.type}
                    </span>
                  </div>
                  <p className="text-xs text-muted mt-0.5">{art.description}</p>
                  <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-muted/70">
                    <span>{art.size}</span>
                    <span>•</span>
                    <span>Created {art.created}</span>
                    <span>•</span>
                    <span className="text-success">{art.metric}</span>
                  </div>
                </div>
              </div>

              <button
                className="px-3 py-1.5 rounded-lg bg-border/40 hover:bg-border text-xs text-primary font-medium transition-colors flex items-center gap-1.5 flex-shrink-0 cursor-pointer"
                title="Download artifact"
              >
                <Download className="w-3.5 h-3.5 text-accent" />
                <span>Download</span>
              </button>
            </div>
          ))}
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
