import { useEffect, useState } from "react";
import { X, Copy, Check, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useUIStore } from "../../store/uiStore";
import { api } from "../../services/api";
import { ArtifactContent } from "../../types";

interface ArtifactViewerModalProps {
  projectId: string;
}

export function ArtifactViewerModal({ projectId }: ArtifactViewerModalProps) {
  const { viewingArtifact, setViewingArtifact } = useUIStore();
  const [content, setContent] = useState<ArtifactContent | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [tablePage, setTablePage] = useState(0);
  const pageSize = 20;

  useEffect(() => {
    if (!viewingArtifact) {
      setContent(null);
      return;
    }

    setIsLoading(true);
    api
      .getArtifactContent(projectId, viewingArtifact.id)
      .then((data) => setContent(data))
      .catch((err) => {
        setContent({ type: "text", content: `Error loading artifact content: ${err.message}` });
      })
      .finally(() => setIsLoading(false));
  }, [projectId, viewingArtifact]);

  if (!viewingArtifact) return null;

  const filePath = viewingArtifact.file_path || viewingArtifact.path || "";
  const filename = filePath.split(/[\\/]/).pop() || viewingArtifact.id;

  const handleCopy = () => {
    let textToCopy = "";
    if (content?.type === "json") textToCopy = JSON.stringify(content.data, null, 2);
    else if (content?.type === "markdown" || content?.type === "code" || content?.type === "text")
      textToCopy = content.content || "";
    else if (content?.type === "table" && content.rows)
      textToCopy = JSON.stringify(content.rows, null, 2);

    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0f172a] border border-slate-700 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-2.5">
            <FileText className="w-4 h-4 text-sky-400" />
            <div>
              <div className="font-mono text-sm font-semibold text-slate-100">{filename}</div>
              <div className="text-[11px] text-slate-400 font-mono">Stage: {viewingArtifact.stage}</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
              title="Copy Content"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>
            <button
              onClick={() => setViewingArtifact(null)}
              className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 text-sm">
          {isLoading && (
            <div className="py-16 text-center text-slate-400 animate-pulse font-mono text-xs">
              Loading artifact contents...
            </div>
          )}

          {!isLoading && content && (
            <>
              {content.type === "markdown" && (
                <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-headings:text-slate-200 prose-p:text-slate-300">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content.content || ""}</ReactMarkdown>
                </div>
              )}

              {content.type === "json" && (
                <pre className="bg-[#090d16] p-4 rounded-lg border border-slate-800 font-mono text-xs text-emerald-300 overflow-x-auto">
                  {JSON.stringify(content.data, null, 2)}
                </pre>
              )}

              {content.type === "code" && (
                <pre className="bg-[#090d16] p-4 rounded-lg border border-slate-800 font-mono text-xs text-sky-300 overflow-x-auto">
                  {content.content}
                </pre>
              )}

              {content.type === "table" && content.columns && content.rows && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                    <span>
                      Showing rows {tablePage * pageSize + 1} -{" "}
                      {Math.min((tablePage + 1) * pageSize, content.rows.length)} of {content.total_rows || content.rows.length}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        disabled={tablePage === 0}
                        onClick={() => setTablePage((p) => Math.max(0, p - 1))}
                        className="px-2 py-1 rounded bg-slate-800 disabled:opacity-40 text-slate-300"
                      >
                        Prev
                      </button>
                      <button
                        disabled={(tablePage + 1) * pageSize >= content.rows.length}
                        onClick={() => setTablePage((p) => p + 1)}
                        className="px-2 py-1 rounded bg-slate-800 disabled:opacity-40 text-slate-300"
                      >
                        Next
                      </button>
                    </div>
                  </div>

                  <div className="border border-slate-800 rounded-lg overflow-x-auto">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead className="bg-slate-800/60 font-mono text-slate-300 border-b border-slate-800">
                        <tr>
                          {content.columns.map((col) => (
                            <th key={col} className="p-2 font-medium truncate max-w-[180px]">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800 font-mono">
                        {content.rows
                          .slice(tablePage * pageSize, (tablePage + 1) * pageSize)
                          .map((row, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/30">
                              {content.columns!.map((col) => (
                                <td key={col} className="p-2 text-slate-300 truncate max-w-[180px]">
                                  {String(row[col] ?? "")}
                                </td>
                              ))}
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {content.type === "text" && (
                <pre className="bg-[#090d16] p-4 rounded-lg border border-slate-800 font-mono text-xs text-slate-300 whitespace-pre-wrap">
                  {content.content}
                </pre>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
