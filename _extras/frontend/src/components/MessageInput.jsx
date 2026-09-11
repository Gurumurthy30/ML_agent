import React, { useState, useRef, useEffect } from 'react';
import { Plus, ArrowUp, X, FileText, Sparkles, Loader2 } from 'lucide-react';

export default function MessageInput({
  onSendMessage,
  uploadFile,
  isGenerating = false,
  placeholder = 'Message the agent…',
  prefilledText = '',
  onClearPrefill,
  variant = 'sticky', // 'sticky' | 'centered'
}) {
  const [text, setText] = useState(prefilledText || '');
  const [attachments, setAttachments] = useState([]); // [{ handle, name, size, isUploading }]
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // Sync prefilled text from parent
  useEffect(() => {
    if (prefilledText) {
      setText(prefilledText);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
      if (onClearPrefill) onClearPrefill();
    }
  }, [prefilledText, onClearPrefill]);

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

  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  };

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;

    for (const file of files) {
      const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const pendingItem = {
        id: tempId,
        name: file.name,
        size: formatFileSize(file.size),
        isUploading: true,
      };

      setAttachments((prev) => [...prev, pendingItem]);

      try {
        let uploaded;
        if (uploadFile) {
          uploaded = await uploadFile(file);
        } else {
          const formData = new FormData();
          formData.append('file', file);
          const res = await fetch('/upload', { method: 'POST', body: formData });
          if (!res.ok) throw new Error('Upload failed');
          uploaded = await res.json();
        }

        setAttachments((prev) =>
          prev.map((item) =>
            item.id === tempId
              ? {
                  ...item,
                  handle: uploaded.handle,
                  name: uploaded.filename || file.name,
                  size: formatFileSize(uploaded.size || file.size),
                  isUploading: false,
                }
              : item
          )
        );
      } catch (err) {
        console.error('File upload failed:', err);
        setAttachments((prev) => prev.filter((item) => item.id !== tempId));
        alert(`Failed to upload ${file.name}`);
      }
    }

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeAttachment = (index) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    const hasUploading = attachments.some((a) => a.isUploading);
    if (hasUploading) return;
    if ((!trimmed && attachments.length === 0) || isGenerating) return;

    const handles = attachments.map((a) => a.handle).filter(Boolean);
    const details = attachments.map((a) => ({ name: a.name, size: a.size }));

    onSendMessage({
      content: trimmed,
      attachments: handles,
      attachmentDetails: details,
    });

    setText('');
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const isUploadingAny = attachments.some((a) => a.isUploading);
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isGenerating && !isUploadingAny;

  const containerClasses =
    variant === 'centered'
      ? 'w-full'
      : 'sticky bottom-0 w-full bg-gradient-to-t from-chat via-chat to-transparent pt-4 pb-4 px-4 select-text';

  return (
    <div className={containerClasses}>
      <div className={variant === 'centered' ? 'w-full' : 'max-w-chat mx-auto'}>
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
                  {file.isUploading ? (
                    <Loader2 className="w-3.5 h-3.5 text-accent animate-spin" />
                  ) : (
                    <FileText className="w-3.5 h-3.5 text-accent" />
                  )}
                  <span className="max-w-[150px] truncate font-sans">{file.name}</span>
                  {file.size && <span className="text-[10.5px] text-muted font-mono">{file.size}</span>}
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
              title="Attach dataset files (CSV, Parquet, JSON, etc.)"
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
              placeholder={placeholder}
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
              title={canSend ? 'Send message (Enter)' : 'Type a message or attach a file'}
            >
              {isGenerating ? (
                <Sparkles className="w-4 h-4 animate-spin text-white" />
              ) : (
                <ArrowUp className="w-4 h-4" strokeWidth={2.5} />
              )}
            </button>
          </div>
        </div>

        {/* Disclaimer */}
        <p className="text-center text-[11.5px] text-muted/70 mt-2 tracking-normal select-none">
          ML Agent autonomously profiles data, engineers features, and executes cross-validation.
        </p>
      </div>
    </div>
  );
}
