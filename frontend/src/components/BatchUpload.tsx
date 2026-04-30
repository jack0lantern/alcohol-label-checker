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
  const [jobId, setJobId] = useState<string | null>(null);
  const [progressText, setProgressText] = useState<string | null>(null);
  const [reportReady, setReportReady] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const latestReportRef = useRef<BatchReportResponse | null>(null);
  const timerRef = useRef<number | null>(null);

  const clearPoller = () => {
    if (timerRef.current == null) {
      return;
    }

    window.clearInterval(timerRef.current);
    timerRef.current = null;
  };

  useEffect(() => {
    return () => {
      clearPoller();
    };
  }, []);

  const loadReport = async (nextJobId: string) => {
    const response = await fetch(`/verify/batch/${nextJobId}/report`);
    if (!response.ok && response.status !== 202) {
      throw new Error("Batch report request failed");
    }

    const body = (await response.json()) as BatchReportResponse;
    latestReportRef.current = body;
    setProgressText(`Batch progress: ${body.summary.processed}/${body.summary.total}`);

    if (body.status === "completed" || body.status === "completed_with_failures") {
      setReportReady(true);
      clearPoller();
    }
  };

  const startBatchCheck = async () => {
    if (mappingFile == null || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setJobId(null);
    setReportReady(false);
    setProgressText(null);
    latestReportRef.current = null;
    clearPoller();

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

      await loadReport(createBody.job_id);
      timerRef.current = window.setInterval(() => {
        void loadReport(createBody.job_id).catch((error) => {
          const message = error instanceof Error ? error.message : "Batch report request failed";
          setErrorMessage(message);
          clearPoller();
        });
      }, 250);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Batch verification failed";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const downloadBatchReport = () => {
    const report = latestReportRef.current;
    if (report == null) {
      return;
    }

    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.job_id}-report.json`;
    link.click();
    URL.revokeObjectURL(url);
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

      <button type="button" disabled={!reportReady} onClick={downloadBatchReport}>
        Download batch report
      </button>
    </section>
  );
}

export default BatchUpload;
