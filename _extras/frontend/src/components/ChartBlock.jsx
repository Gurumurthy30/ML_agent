import React, { useState } from 'react';
import { BarChart3, Download, Maximize2, X, Image as ImageIcon } from 'lucide-react';

export default function ChartBlock({ chart, edaCharts }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  // ── Render generated plot (base64 image from execute node) ──
  if (chart && chart.image_base64) {
    const dataUri = `data:image/png;base64,${chart.image_base64}`;

    const handleDownload = () => {
      const a = document.createElement('a');
      a.href = dataUri;
      a.download = chart.filename || `${chart.title || 'plot'}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    };

    return (
      <div className="my-3 rounded-xl border border-border bg-card overflow-hidden shadow-md select-text">
        {/* Header */}
        <div className="flex items-center justify-between px-3.5 py-2.5 bg-[#201F1D] border-b border-border/80">
          <div className="flex items-center gap-2">
            <ImageIcon className="w-4 h-4 text-accent" />
            <span className="font-sans font-medium text-xs text-primary">
              {chart.title || 'Visualization Plot'}
            </span>
            {chart.experiment_id && (
              <span className="px-1.5 py-0.5 rounded bg-border/40 font-mono text-[10.5px] text-muted">
                {chart.experiment_id}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setIsModalOpen(true)}
              className="p-1 rounded text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
              title="Enlarge plot"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleDownload}
              className="p-1 rounded text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
              title="Download image"
            >
              <Download className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Inline Image */}
        <div
          className="p-3 bg-[#181716] flex items-center justify-center cursor-pointer group"
          onClick={() => setIsModalOpen(true)}
        >
          <img
            src={dataUri}
            alt={chart.title || 'Generated Plot'}
            className="max-h-[380px] w-auto max-w-full rounded-lg border border-border/50 object-contain transition-transform group-hover:scale-[1.01]"
          />
        </div>

        {/* Fullscreen Lightbox Modal */}
        {isModalOpen && (
          <div
            className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in"
            onClick={() => setIsModalOpen(false)}
          >
            <div
              className="relative max-w-4xl max-h-[90vh] bg-card p-4 rounded-2xl border border-border flex flex-col gap-3 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between border-b border-border/60 pb-2">
                <span className="text-sm font-medium text-primary font-sans">{chart.title}</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDownload}
                    className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
                    title="Download image"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setIsModalOpen(false)}
                    className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div className="overflow-auto flex items-center justify-center p-2 bg-[#181716] rounded-xl">
                <img
                  src={dataUri}
                  alt={chart.title}
                  className="max-h-[75vh] w-auto object-contain rounded-lg"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Render structured EDA charts (class balance & correlations) ──
  if (edaCharts) {
    const classBalance = edaCharts.class_balance || {};
    const correlations = edaCharts.target_correlations || [];

    const hasClassBalance = Object.keys(classBalance).length > 0;
    const hasCorrelations = correlations.length > 0;

    if (!hasClassBalance && !hasCorrelations) return null;

    // Calculate total for class balance percentages
    const totalClassSamples = Object.values(classBalance).reduce((acc, v) => acc + Number(v), 0);

    return (
      <div className="my-3 rounded-xl border border-border bg-[#242321] overflow-hidden shadow-sm select-text text-xs">
        <div className="px-3.5 py-2.5 bg-[#1D1C1B] border-b border-border/80 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-accent" />
          <span className="font-sans font-medium text-primary">Interactive EDA Charts</span>
          <span className="text-[11px] font-mono text-muted">Computed from dataset profile</span>
        </div>

        <div className="p-3.5 space-y-4 bg-[#242321]">
          {/* 1. Target Correlations Bar Chart */}
          {hasCorrelations && (
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted font-mono mb-2">
                Top Target Correlations (|r|)
              </div>
              <div className="space-y-1.5 font-mono">
                {correlations.slice(0, 8).map((item, idx) => {
                  const corrVal = Number(item.corr) || 0;
                  const absPct = Math.min(Math.abs(corrVal) * 100, 100);
                  const isPositive = corrVal >= 0;

                  return (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="w-32 truncate text-right text-muted text-[11.5px]" title={item.feature}>
                        {item.feature}
                      </span>
                      <div className="flex-1 bg-[#181716] h-4 rounded-md overflow-hidden flex items-center px-1 relative border border-border/40">
                        <div
                          className={`h-2.5 rounded-sm transition-all duration-300 ${
                            isPositive ? 'bg-accent' : 'bg-[#E5484D]'
                          }`}
                          style={{ width: `${absPct}%` }}
                        />
                      </div>
                      <span
                        className={`w-14 text-right text-[11px] font-semibold ${
                          isPositive ? 'text-accent' : 'text-[#E5484D]'
                        }`}
                      >
                        {corrVal > 0 ? `+${corrVal.toFixed(3)}` : corrVal.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 2. Class Balance Horizontal Bars */}
          {hasClassBalance && (
            <div className="pt-2 border-t border-border/60">
              <div className="text-[11px] uppercase tracking-wider text-muted font-mono mb-2">
                Class Distribution
              </div>
              <div className="space-y-2 font-mono">
                {Object.entries(classBalance).map(([label, count], idx) => {
                  const numCount = Number(count);
                  const pct = totalClassSamples > 0 ? (numCount / totalClassSamples) * 100 : 0;
                  const barColors = ['bg-accent', 'bg-[#46A758]', 'bg-[#F7CE46]', 'bg-[#3E63DD]'];
                  const color = barColors[idx % barColors.length];

                  return (
                    <div key={idx} className="space-y-0.5">
                      <div className="flex items-center justify-between text-[11.5px]">
                        <span className="text-primary font-medium">Class "{label}"</span>
                        <span className="text-muted">
                          {numCount.toLocaleString()} samples ({pct.toFixed(1)}%)
                        </span>
                      </div>
                      <div className="w-full bg-[#181716] h-3 rounded-full overflow-hidden border border-border/40">
                        <div
                          className={`h-full ${color} rounded-full transition-all duration-500`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}
