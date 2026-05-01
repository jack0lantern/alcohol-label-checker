import { useEffect, useMemo, useRef, useState } from "react";

import { apiUrl, batchEventsWebSocketUrl, unreachableApiHint } from "../apiClient";
import { pairFiles, type DroppedFile, type PairingResult } from "../lib/pairing";

type BatchReportResponse = {
  job_id: string;
  status: "queued" | "running" | "completed" | "completed_with_failures";
  summary: { processed: number; total: number; pass: number; fail: number; review_required: number };
  items: Array<Record<string, unknown>>;
};

type WorkingState = {
  fileById: Map<string, DroppedFile>;
  itemPdfFileId: Map<string, string>; // itemId -> pdf fileId
  itemLabelFileIds: Map<string, string[]>;
  itemOverLimit: Map<string, boolean>;
  orphanPdfFileIds: string[];
  orphanImageFileIds: string[];
  ignoredFileIds: string[];
};

const EMPTY_STATE: WorkingState = {
  fileById: new Map(),
  itemPdfFileId: new Map(),
  itemLabelFileIds: new Map(),
  itemOverLimit: new Map(),
  orphanPdfFileIds: [],
  orphanImageFileIds: [],
  ignoredFileIds: [],
};

let nextFileId = 0;
function generateFileId(): string {
  nextFileId += 1;
  return `f${nextFileId}`;
}

function normalizeRelativePath(file: File): string {
  const wkrp = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath ?? "";
  if (wkrp) return wkrp;
  return file.name;
}

function mergePairing(prev: WorkingState, addition: PairingResult, fileIds: Map<DroppedFile, string>): WorkingState {
  const next: WorkingState = {
    fileById: new Map(prev.fileById),
    itemPdfFileId: new Map(prev.itemPdfFileId),
    itemLabelFileIds: new Map(prev.itemLabelFileIds),
    itemOverLimit: new Map(prev.itemOverLimit),
    orphanPdfFileIds: [...prev.orphanPdfFileIds],
    orphanImageFileIds: [...prev.orphanImageFileIds],
    ignoredFileIds: [...prev.ignoredFileIds],
  };

  for (const [df, id] of fileIds) {
    next.fileById.set(id, df);
  }

  const usedIds = new Set(next.itemPdfFileId.keys());
  for (const item of addition.items) {
    let candidate = item.itemId;
    let suffix = 1;
    while (usedIds.has(candidate)) {
      suffix += 1;
      candidate = `${item.itemId}-${suffix}`;
    }
    usedIds.add(candidate);
    next.itemPdfFileId.set(candidate, fileIds.get(item.pdf)!);
    next.itemLabelFileIds.set(
      candidate,
      item.labels.map((l) => fileIds.get(l)!),
    );
    next.itemOverLimit.set(candidate, item.isOverLabelLimit);
  }

  for (const orphan of addition.orphanPdfs) {
    next.orphanPdfFileIds.push(fileIds.get(orphan)!);
  }
  for (const orphan of addition.orphanImages) {
    next.orphanImageFileIds.push(fileIds.get(orphan)!);
  }
  for (const ignored of addition.ignoredFiles) {
    next.ignoredFileIds.push(fileIds.get(ignored)!);
  }

  return next;
}

function BatchUpload() {
  const [state, setState] = useState<WorkingState>(EMPTY_STATE);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const filesInputRef = useRef<HTMLInputElement | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [reportReady, setReportReady] = useState(false);
  const websocketRef = useRef<WebSocket | null>(null);

  useEffect(() => () => {
    websocketRef.current?.close();
    websocketRef.current = null;
  }, []);

  const summary = useMemo(() => {
    let pdfCount = 0;
    let imageCount = 0;
    for (const f of state.fileById.values()) {
      const ext = f.relativePath.toLowerCase();
      if (ext.endsWith(".pdf")) pdfCount += 1;
      else if (ext.match(/\.(png|jpe?g|webp)$/)) imageCount += 1;
    }
    return { total: state.fileById.size, pdfCount, imageCount };
  }, [state.fileById]);

  const ingestFiles = (rawFiles: FileList | File[]) => {
    setErrorMessage(null);
    const droppedFiles: DroppedFile[] = [];
    const fileIds = new Map<DroppedFile, string>();
    for (const f of Array.from(rawFiles)) {
      const df: DroppedFile = { file: f, relativePath: normalizeRelativePath(f) };
      droppedFiles.push(df);
      fileIds.set(df, generateFileId());
    }
    const result = pairFiles(droppedFiles);
    setState((prev) => mergePairing(prev, result, fileIds));
  };

  const onFolderPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files;
    if (files) ingestFiles(files);
    event.currentTarget.value = "";
  };

  const onFilesPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.currentTarget.files;
    if (files) ingestFiles(files);
    event.currentTarget.value = "";
  };

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const items = event.dataTransfer.items;
    if (items && items.length > 0) {
      const collected: File[] = [];
      const promises: Promise<void>[] = [];
      for (const it of Array.from(items)) {
        const entry = (it as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntry | null }).webkitGetAsEntry?.();
        if (entry) {
          promises.push(walkEntry(entry, "", collected));
        } else {
          const file = it.getAsFile();
          if (file) collected.push(file);
        }
      }
      Promise.all(promises).then(() => ingestFiles(collected));
    } else if (event.dataTransfer.files) {
      ingestFiles(event.dataTransfer.files);
    }
  };

  const removeLabelFromItem = (itemId: string, labelId: string) => {
    setState((prev) => {
      const newLabelIds = (prev.itemLabelFileIds.get(itemId) ?? []).filter((id) => id !== labelId);
      const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
      newItemLabelFileIds.set(itemId, newLabelIds);
      const newItemOverLimit = new Map(prev.itemOverLimit);
      newItemOverLimit.set(itemId, newLabelIds.length > 10);
      return {
        ...prev,
        itemLabelFileIds: newItemLabelFileIds,
        itemOverLimit: newItemOverLimit,
        orphanImageFileIds: [...prev.orphanImageFileIds, labelId],
      };
    });
  };

  const discardOrphanPdf = (fileId: string) => {
    setState((prev) => {
      const fileById = new Map(prev.fileById);
      fileById.delete(fileId);
      return {
        ...prev,
        fileById,
        orphanPdfFileIds: prev.orphanPdfFileIds.filter((id) => id !== fileId),
      };
    });
  };

  const discardOrphanImage = (fileId: string) => {
    setState((prev) => {
      const fileById = new Map(prev.fileById);
      fileById.delete(fileId);
      return {
        ...prev,
        fileById,
        orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== fileId),
      };
    });
  };

  const attachOrphanImageToItem = (imageFileId: string, itemId: string) => {
    setState((prev) => {
      if (!prev.itemPdfFileId.has(itemId)) return prev;
      const newLabelIds = [...(prev.itemLabelFileIds.get(itemId) ?? []), imageFileId];
      const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
      newItemLabelFileIds.set(itemId, newLabelIds);
      const newItemOverLimit = new Map(prev.itemOverLimit);
      newItemOverLimit.set(itemId, newLabelIds.length > 10);
      return {
        ...prev,
        itemLabelFileIds: newItemLabelFileIds,
        itemOverLimit: newItemOverLimit,
        orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== imageFileId),
      };
    });
  };

  const promoteOrphanPdfWithImage = (pdfFileId: string, imageFileId: string) => {
    setState((prev) => {
      if (!prev.fileById.has(pdfFileId) || !prev.fileById.has(imageFileId)) return prev;
      const pdfFile = prev.fileById.get(pdfFileId)!;
      const filename = pdfFile.relativePath.split("/").pop() ?? pdfFile.relativePath;
      const baseId = filename.replace(/\.[^.]+$/, "");
      let candidate = baseId;
      let suffix = 1;
      while (prev.itemPdfFileId.has(candidate)) {
        suffix += 1;
        candidate = `${baseId}-${suffix}`;
      }
      const newItemPdfFileId = new Map(prev.itemPdfFileId);
      newItemPdfFileId.set(candidate, pdfFileId);
      const newItemLabelFileIds = new Map(prev.itemLabelFileIds);
      newItemLabelFileIds.set(candidate, [imageFileId]);
      const newItemOverLimit = new Map(prev.itemOverLimit);
      newItemOverLimit.set(candidate, false);
      return {
        ...prev,
        itemPdfFileId: newItemPdfFileId,
        itemLabelFileIds: newItemLabelFileIds,
        itemOverLimit: newItemOverLimit,
        orphanPdfFileIds: prev.orphanPdfFileIds.filter((id) => id !== pdfFileId),
        orphanImageFileIds: prev.orphanImageFileIds.filter((id) => id !== imageFileId),
      };
    });
  };

  const blockingReason = (() => {
    if (state.itemPdfFileId.size === 0) return "Add at least one form-and-label item.";
    for (const [, overLimit] of state.itemOverLimit) {
      if (overLimit) return "Trim items with more than 10 labels.";
    }
    if (state.orphanPdfFileIds.length + state.orphanImageFileIds.length > 0) {
      return "Resolve all items in the Needs Review tray.";
    }
    return null;
  })();

  const startBatch = async () => {
    if (blockingReason !== null || isSubmitting) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    setJobId(null);
    setReportReady(false);
    setProgressText(null);

    try {
      const formData = new FormData();
      const usedFilenames = new Set<string>();
      const itemSpecs: Array<{ item_id: string; form_filename: string; label_filenames: string[] }> = [];
      for (const [itemId, pdfFileId] of state.itemPdfFileId) {
        const pdfFile = state.fileById.get(pdfFileId)!;
        const pdfName = pdfFile.relativePath.split("/").pop()!;
        if (!usedFilenames.has(pdfFile.relativePath)) {
          formData.append("files", pdfFile.file, pdfName);
          usedFilenames.add(pdfFile.relativePath);
        }
        const labelIds = state.itemLabelFileIds.get(itemId) ?? [];
        const labelNames: string[] = [];
        for (const lid of labelIds) {
          const lf = state.fileById.get(lid)!;
          const lname = lf.relativePath.split("/").pop()!;
          if (!usedFilenames.has(lf.relativePath)) {
            formData.append("files", lf.file, lname);
            usedFilenames.add(lf.relativePath);
          }
          labelNames.push(lname);
        }
        itemSpecs.push({ item_id: itemId, form_filename: pdfName, label_filenames: labelNames });
      }
      formData.append("mapping", JSON.stringify({ items: itemSpecs }));

      const response = await fetch(apiUrl("/verify/batch"), { method: "POST", body: formData });
      if (!response.ok) {
        const detail = response.status === 400 ? (await response.json()).detail ?? "Bad request" : "Batch verification failed";
        throw new Error(detail);
      }
      const body = (await response.json()) as { job_id: string };
      setJobId(body.job_id);
      websocketRef.current?.close();
      const ws = new WebSocket(batchEventsWebSocketUrl(body.job_id));
      websocketRef.current = ws;
      ws.addEventListener("message", (event) => {
        let parsed: Record<string, unknown> | null = null;
        try {
          parsed = JSON.parse(event.data) as Record<string, unknown>;
        } catch {
          return;
        }
        const processed = parsed.processed;
        const total = parsed.total;
        if (typeof processed === "number" && typeof total === "number") {
          setProgressText(`Batch progress: ${processed}/${total}`);
        }
        if (parsed.event_type === "job_completed") {
          setReportReady(true);
          ws.close();
          websocketRef.current = null;
        }
      });
      ws.addEventListener("error", () => setErrorMessage("Batch progress stream failed"));
    } catch (error) {
      const message =
        error instanceof TypeError && error.message === "Failed to fetch"
          ? `Unable to reach the API. ${unreachableApiHint()}`
          : error instanceof Error
            ? error.message
            : "Batch verification failed";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const downloadReport = async () => {
    if (jobId == null) return;
    setIsDownloading(true);
    setErrorMessage(null);
    try {
      const response = await fetch(apiUrl(`/verify/batch/${jobId}/report?purge=true`));
      if (!response.ok) throw new Error("Batch report request failed");
      const report = (await response.json()) as BatchReportResponse;
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${report.job_id}-report.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      const message =
        error instanceof TypeError && error.message === "Failed to fetch"
          ? `Unable to reach the API. ${unreachableApiHint()}`
          : error instanceof Error
            ? error.message
            : "Batch report request failed";
      setErrorMessage(message);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <section aria-label="Batch upload">
      <h2>Batch Check</h2>

      <div
        className="batch-drop-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        {state.fileById.size === 0 ? (
          <span className="placeholder">Drop a folder or files, or use the buttons below</span>
        ) : (
          <span className="batch-summary">
            {summary.total} files: {summary.pdfCount} PDFs, {summary.imageCount} images
            {state.ignoredFileIds.length > 0 ? ` (${state.ignoredFileIds.length} ignored)` : ""}
          </span>
        )}
      </div>

      <div className="batch-pickers">
        <button type="button" onClick={() => folderInputRef.current?.click()}>Pick folder</button>
        <button type="button" onClick={() => filesInputRef.current?.click()}>Pick files</button>
        <input
          ref={folderInputRef}
          type="file"
          // @ts-expect-error webkitdirectory is non-standard but supported by Chrome/Edge/Firefox
          webkitdirectory=""
          multiple
          hidden
          onChange={onFolderPicked}
        />
        <input
          ref={filesInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          hidden
          onChange={onFilesPicked}
        />
      </div>

      {state.itemPdfFileId.size > 0 ? (
        <div className="batch-items">
          <h3>Paired items</h3>
          {Array.from(state.itemPdfFileId.keys()).map((itemId) => {
            const pdfId = state.itemPdfFileId.get(itemId)!;
            const labelIds = state.itemLabelFileIds.get(itemId) ?? [];
            const overLimit = state.itemOverLimit.get(itemId) ?? false;
            const pdfFile = state.fileById.get(pdfId)!;
            return (
              <div
                className={`batch-item-row${overLimit ? " over-limit" : ""}`}
                key={itemId}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const droppedId = e.dataTransfer.getData("text/orphan-image-id");
                  if (droppedId) attachOrphanImageToItem(droppedId, itemId);
                }}
              >
                <div className="batch-item-pdf">{pdfFile.relativePath}</div>
                <div className="batch-item-labels">
                  {labelIds.map((lid) => {
                    const f = state.fileById.get(lid)!;
                    return (
                      <span key={lid} className="label-chip">
                        {f.relativePath}
                        {overLimit ? (
                          <button type="button" aria-label={`Remove ${f.relativePath}`} onClick={() => removeLabelFromItem(itemId, lid)}>×</button>
                        ) : null}
                      </span>
                    );
                  })}
                  <span className={`label-count-badge${overLimit ? " over-limit" : ""}`}>{labelIds.length}/10</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {(state.orphanPdfFileIds.length + state.orphanImageFileIds.length) > 0 ? (
        <div className="orphan-tray">
          <h3>Needs review ({state.orphanPdfFileIds.length + state.orphanImageFileIds.length})</h3>
          {state.orphanPdfFileIds.length > 0 ? (
            <div className="orphan-section">
              <h4>Orphan PDFs</h4>
              {state.orphanPdfFileIds.map((id) => {
                const f = state.fileById.get(id)!;
                return (
                  <div
                    className="orphan-row"
                    key={id}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      const droppedId = e.dataTransfer.getData("text/orphan-image-id");
                      if (droppedId) promoteOrphanPdfWithImage(id, droppedId);
                    }}
                  >
                    <span>{f.relativePath}</span>
                    <button type="button" onClick={() => discardOrphanPdf(id)}>Discard</button>
                    <select
                      aria-label={`Attach images to ${f.relativePath}`}
                      value=""
                      onChange={(e) => {
                        if (e.target.value) {
                          promoteOrphanPdfWithImage(id, e.target.value);
                        }
                      }}
                    >
                      <option value="">Attach orphan image…</option>
                      {state.orphanImageFileIds.map((imgId) => (
                        <option key={imgId} value={imgId}>
                          {state.fileById.get(imgId)!.relativePath}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          ) : null}
          {state.orphanImageFileIds.length > 0 ? (
            <div className="orphan-section">
              <h4>Orphan images</h4>
              {state.orphanImageFileIds.map((id) => {
                const f = state.fileById.get(id)!;
                return (
                  <div
                    className="orphan-row"
                    key={id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("text/orphan-image-id", id)}
                  >
                    <span>{f.relativePath}</span>
                    <button type="button" onClick={() => discardOrphanImage(id)}>Discard</button>
                    <select
                      aria-label={`Attach ${f.relativePath} to item`}
                      value=""
                      onChange={(e) => {
                        if (e.target.value) attachOrphanImageToItem(id, e.target.value);
                      }}
                    >
                      <option value="">Attach to item…</option>
                      {Array.from(state.itemPdfFileId.keys()).map((itemId) => (
                        <option key={itemId} value={itemId}>
                          {itemId}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      <button
        type="button"
        disabled={blockingReason !== null || isSubmitting}
        title={blockingReason ?? ""}
        onClick={() => void startBatch()}
      >
        {isSubmitting ? "Starting batch check..." : "Start batch check"}
      </button>

      {jobId != null || progressText != null ? (
        <div className="result-panel">
          <h3>Job Status</h3>
          {jobId != null ? <div className="value-box"><span className="value-label">Job ID</span>{jobId}</div> : null}
          {progressText != null ? <div className="progress-text">{progressText}</div> : null}
          {reportReady ? (
            <button type="button" disabled={jobId == null || isDownloading} onClick={() => void downloadReport()}>
              {isDownloading ? "Downloading batch report..." : "Download batch report"}
            </button>
          ) : null}
        </div>
      ) : null}

      {errorMessage != null ? <div className="error-message" role="alert">{errorMessage}</div> : null}
    </section>
  );
}

async function walkEntry(entry: FileSystemEntry, parentPath: string, out: File[]): Promise<void> {
  if (entry.isFile) {
    const fileEntry = entry as FileSystemFileEntry;
    return new Promise((resolve) => {
      fileEntry.file((file) => {
        const path = parentPath ? `${parentPath}/${file.name}` : file.name;
        Object.defineProperty(file, "webkitRelativePath", { value: path });
        out.push(file);
        resolve();
      });
    });
  }
  if (entry.isDirectory) {
    const dirEntry = entry as FileSystemDirectoryEntry;
    const reader = dirEntry.createReader();
    const subPath = parentPath ? `${parentPath}/${entry.name}` : entry.name;
    return new Promise((resolve) => {
      const collected: FileSystemEntry[] = [];
      const readBatch = () => {
        reader.readEntries(async (entries) => {
          if (entries.length === 0) {
            await Promise.all(collected.map((e) => walkEntry(e, subPath, out)));
            resolve();
          } else {
            collected.push(...entries);
            readBatch();
          }
        });
      };
      readBatch();
    });
  }
}

export default BatchUpload;
