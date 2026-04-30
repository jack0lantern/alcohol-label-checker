import { useEffect, useRef, useState } from "react";

type BatchStartResponse = {
  job_id: string;
};

type BatchReportResponse = {
  job_id: string;
  status: "queued" | "running" | "completed" | "completed_with_failures";
  summary: {
    processed: number;
    total: number;
    pass: number;
    fail: number;
    review_required: number;
  };
  items: Array<Record<string, unknown>>;
};

function BatchUpload() {
  const [mappingFile, setMappingFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [reportReady, setReportReady] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);

  const clearSocket = () => {
    if (websocketRef.current == null) {
      return;
    }

    websocketRef.current.close();
    websocketRef.current = null;
  };

  useEffect(() => {
    return () => {
      clearSocket();
    };
  }, []);

  const startBatchCheck = async () => {
    if (mappingFile == null || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setJobId(null);
    setReportReady(false);
    setProgressText(null);
    clearSocket();

    try {
      const batchJson = JSON.parse(await mappingFile.text()) as { items: unknown[] };
      const createResponse = await fetch("/verify/batch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(batchJson),
      });

      if (!createResponse.ok) {
        throw new Error("Batch verification failed");
      }

      const createBody = (await createResponse.json()) as BatchStartResponse;
      setJobId(createBody.job_id);
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${wsProtocol}://${window.location.host}/verify/batch/${createBody.job_id}/events`);
      websocketRef.current = ws;

      ws.addEventListener("message", (event) => {
        let body: Record<string, unknown> | null = null;
        try {
          body = JSON.parse(event.data) as Record<string, unknown>;
        } catch {
          return;
        }

        const processed = body.processed;
        const total = body.total;
        if (typeof processed === "number" && typeof total === "number") {
          setProgressText(`Batch progress: ${processed}/${total}`);
        }

        const eventType = body.event_type;
        if (eventType === "job_completed") {
          setReportReady(true);
          clearSocket();
        }
      });

      ws.addEventListener("error", () => {
        setErrorMessage("Batch progress stream failed");
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Batch verification failed";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const downloadBatchReport = async () => {
    if (jobId == null) {
      return;
    }

    setIsDownloading(true);
    setErrorMessage(null);

    try {
      const response = await fetch(`/verify/batch/${jobId}/report`);
      if (!response.ok) {
        throw new Error("Batch report request failed");
      }

      const report = (await response.json()) as BatchReportResponse;
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${report.job_id}-report.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Batch report request failed";
      setErrorMessage(message);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <section aria-label="Batch upload">
      <h2>Batch check</h2>
      <label htmlFor="batch-mapping-json">Batch Mapping JSON</label>
      <input
        id="batch-mapping-json"
        type="file"
        accept=".json,application/json"
        onChange={(event) => {
          const nextFile = event.currentTarget.files?.[0] ?? null;
          setMappingFile(nextFile);
        }}
      />

      <button type="button" disabled={mappingFile == null || isSubmitting} onClick={startBatchCheck}>
        {isSubmitting ? "Starting batch check..." : "Start batch check"}
      </button>

      {jobId != null ? <p>Batch job: {jobId}</p> : null}
      {progressText != null ? <p>{progressText}</p> : null}
      {errorMessage != null ? <p role="alert">{errorMessage}</p> : null}

      <button type="button" disabled={!reportReady || jobId == null || isDownloading} onClick={() => void downloadBatchReport()}>
        {isDownloading ? "Downloading batch report..." : "Download batch report"}
      </button>
    </section>
  );
}

export default BatchUpload;
