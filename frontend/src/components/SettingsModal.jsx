import React, { useState } from 'react';
import { X, Settings, Sliders, HardDrive, Shield, Check } from 'lucide-react';

export default function SettingsModal({ isOpen, onClose }) {
  const [model, setModel] = useState('qwen2.5-coder:32b');
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 800);
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 select-none">
      <div className="bg-card border border-border rounded-2xl max-w-xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center">
              <Settings className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold text-primary">System Settings</h2>
              <p className="text-xs text-muted">Local Ollama endpoints, context windows, and execution permissions</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="py-4 space-y-4 text-xs">
          {/* Ollama Endpoint */}
          <div>
            <label className="block text-muted font-medium mb-1">Ollama Host URL</label>
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              className="w-full bg-[#181716] border border-border rounded-lg px-3 py-2 text-primary font-mono text-xs focus:outline-none focus:border-accent"
            />
          </div>

          {/* Model selection */}
          <div>
            <label className="block text-muted font-medium mb-1">Primary Code & Reasoning Model</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-[#181716] border border-border rounded-lg px-3 py-2 text-primary font-mono text-xs focus:outline-none focus:border-accent cursor-pointer"
            >
              <option value="qwen2.5-coder:32b">qwen2.5-coder:32b (Recommended)</option>
              <option value="qwen2.5-coder:14b">qwen2.5-coder:14b (Fast)</option>
              <option value="deepseek-r1:32b">deepseek-r1:32b (Deep Reasoning)</option>
              <option value="llama3.3:70b">llama3.3:70b</option>
            </select>
          </div>

          {/* Temperature slider */}
          <div>
            <div className="flex justify-between text-muted mb-1 font-medium">
              <span>Sampling Temperature: {temperature}</span>
              <span className="text-[11px] font-mono text-muted/70">Deterministic for Code</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              className="w-full accent-accent bg-[#181716] h-1.5 rounded-lg cursor-pointer"
            />
          </div>

          {/* Max Tokens */}
          <div>
            <label className="block text-muted font-medium mb-1">Max Generation Tokens: {maxTokens}</label>
            <input
              type="range"
              min="1024"
              max="8192"
              step="512"
              value={maxTokens}
              onChange={(e) => setMaxTokens(parseInt(e.target.value))}
              className="w-full accent-accent bg-[#181716] h-1.5 rounded-lg cursor-pointer"
            />
          </div>

          {/* Sandbox Security */}
          <div className="p-3 rounded-xl bg-[#181716] border border-border/70 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Shield className="w-4 h-4 text-accent" />
              <div>
                <div className="font-medium text-primary">Local Sandbox Isolation</div>
                <div className="text-[11px] text-muted">Restrict file I/O to project workspace directory</div>
              </div>
            </div>
            <input
              type="checkbox"
              defaultChecked
              className="w-4 h-4 rounded border-border text-accent focus:ring-0 accent-accent cursor-pointer"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-border/60 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-muted hover:text-primary hover:bg-border/30 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 rounded-xl bg-accent text-white font-medium hover:bg-accent-hover transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            {saved ? <Check className="w-3.5 h-3.5" /> : null}
            <span>{saved ? 'Saved!' : 'Save preferences'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
