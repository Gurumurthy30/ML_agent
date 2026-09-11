import React, { useState, useRef, useEffect } from 'react';
import { Plus, ArrowUp, X, FileText, Sparkles } from 'lucide-react';

export default function MessageInput({ onSendMessage, isGenerating = false }) {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState([]);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [text]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    const newAttachments = files.map((file) => ({
      name: file.name,
      size: formatFileSize(file.size),
      type: file.type || 'file',
    }));

    setAttachments((prev) => [...prev, ...newAttachments]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (index) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isGenerating) return;

    onSendMessage({
      content: trimmed,
      attachments: attachments,
    });

    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isGenerating;

  return (
    <div className="sticky bottom-0 w-full bg-gradient-to-t from-chat via-chat to-transparent pt-4 pb-4 px-4 select-text">
      <div className="max-w-chat mx-auto">
        {/* Input box */}
        <div className="bg-[#2D2C2A] border border-border focus-within:border-[#DA7756]/80 focus-within:ring-1 focus-within:ring-[#DA7756]/40 rounded-2xl p-2.5 transition-all shadow-lg">
          {/* Attachment preview chips */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-2 pt-1 pb-2 border-b border-border/50 mb-2">
              {attachments.map((file, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#1F1E1D] border border-border/70 text-xs text-primary"
                >
                  <FileText className="w-3.5 h-3.5 text-accent" />
                  <span className="max-w-[140px] truncate font-sans">{file.name}</span>
                  <span className="text-[10.5px] text-muted font-mono">{file.size}</span>
                  <button
                    onClick={() => removeAttachment(idx)}
                    className="p-0.5 rounded-full hover:bg-border/60 text-muted hover:text-primary transition-colors ml-0.5 cursor-pointer"
                    title="Remove file"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Composer row */}
          <div className="flex items-end gap-2 px-1">
            {/* Attachment Button */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-muted hover:text-primary hover:bg-[#3A3936]/60 transition-colors flex-shrink-0 cursor-pointer mb-0.5"
              title="Attach files or datasets"
            >
              <Plus className="w-4 h-4" />
            </button>

            {/* Textarea */}
            <textarea
              ref={textareaRef}
              rows={1}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message the agent…"
              className="flex-1 bg-transparent border-0 focus:outline-none focus:ring-0 text-[15px] leading-relaxed text-primary placeholder-muted/80 resize-none py-1.5 max-h-[200px]"
            />

            {/* Send Button */}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSend}
              className={`w-8 h-8 flex items-center justify-center rounded-xl transition-all flex-shrink-0 mb-0.5 cursor-pointer ${
                canSend
                  ? 'bg-accent text-white hover:bg-accent-hover shadow-sm active:scale-95'
                  : 'bg-border/40 text-muted/40 cursor-not-allowed'
              }`}
              title={canSend ? 'Send message (Enter)' : 'Type a message to send'}
            >
              {isGenerating ? (
                <Sparkles className="w-4 h-4 animate-spin text-accent" />
              ) : (
                <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
              )}
            </button>
          </div>
        </div>

        {/* Disclaimer */}
        <p className="text-center text-[11.5px] text-muted/70 mt-2 tracking-normal select-none">
          Agents can make mistakes. Verify important output.
        </p>
      </div>
    </div>
  );
}
