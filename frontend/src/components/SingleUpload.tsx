import { useMemo, useState } from "react";

type SingleVerifyStatus = "pass" | "fail" | "review_required";

type SingleVerifyResponse = {
  status: SingleVerifyStatus;
  field_results: Record<
    string,
    {
      status: SingleVerifyStatus;
      expected_value: string | null;
      extracted_value: string | null;
    }
  >;
  image_results: Array<{
    status: SingleVerifyStatus;
    field_results: Record<
      string,
      {
        status: SingleVerifyStatus;
        expected_value: string | null;
        extracted_value: string | null;
      }
    >;
  }>;
};

const EMPTY_FIELD_PLACEHOLDER = "—";

function formatVerificationField(value: string | null | undefined): string {
  if (value == null) {
    return EMPTY_FIELD_PLACEHOLDER;
  }
  const trimmed = value.trim();
  return trimmed === "" ? EMPTY_FIELD_PLACEHOLDER : trimmed;
}

function SingleUpload() {
  const [formPdf, setFormPdf] = useState<File | null>(null);
  const [labelImages, setLabelImages] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SingleVerifyResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    return formPdf != null && labelImages.length > 0 && labelImages.length <= 10 && !isSubmitting;
  }, [formPdf, isSubmitting, labelImages]);

  const runSingleCheck = async () => {
    if (!canSubmit) {
      return;
    }

    const payload = new FormData();
    payload.append("form_pdf", formPdf);
    for (const labelImage of labelImages) {
      payload.append("label_images", labelImage);
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setResult(null);

    try {
      const response = await fetch("/verify/single", {
        method: "POST",
        body: payload,
      });

      if (!response.ok) {
        throw new Error("Single verification failed");
      }

      const body = (await response.json()) as SingleVerifyResponse;
      setResult(body);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Single verification failed";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section aria-label="Single upload">
      <div className="decorative-cross"></div>
      <h2>Single Check</h2>
      
      <div className="file-drop-area" onClick={() => document.getElementById("single-form-pdf")?.click()}>
        <span className="file-name">{formPdf ? formPdf.name : <span className="placeholder">Select TTB Form PDF</span>}</span>
      </div>
      <input
        id="single-form-pdf"
        type="file"
        accept=".pdf,application/pdf"
        onChange={(event) => {
          const nextFile = event.currentTarget.files?.[0] ?? null;
          setFormPdf(nextFile);
        }}
      />

      <div className="file-drop-area" onClick={() => document.getElementById("single-label-images")?.click()}>
        <span className="file-name">
          {labelImages.length > 0
            ? `${labelImages.length} selected: ${labelImages.map((file) => file.name).join(", ")}`
            : <span className="placeholder">Select 1-10 Label Images</span>}
        </span>
      </div>
      <input
        id="single-label-images"
        type="file"
        accept="image/*"
        multiple
        onChange={(event) => {
          const nextFiles = Array.from(event.currentTarget.files ?? []);
          setLabelImages(nextFiles);
        }}
      />

      <button type="button" disabled={!canSubmit} onClick={runSingleCheck}>
        {isSubmitting ? "Running single check..." : "Run single check"}
      </button>

      {errorMessage != null ? <div className="error-message" role="alert">{errorMessage}</div> : null}

      {result != null ? (
        <div className="result-panel">
          <h3>Verification Result</h3>
          <span className={`status-badge ${result.status}`}>{result.status.replace('_', ' ')}</span>
          <div className="value-box" style={{ marginTop: "var(--spacing-sm)" }}>
            <span className="value-label">Images Processed</span>
            {result.image_results.length}
          </div>
          
          <div className="field-results">
            {Object.entries(result.field_results).map(([field, data]) => (
              <div key={field} className="field-result-item">
                <span className="field-name">{field.replace(/_/g, ' ')}</span>
                <span className={`status-badge ${data.status}`}>{data.status.replace('_', ' ')}</span>
                
                <div className="field-values">
                  <div className="value-box" data-testid={`single-expected-${field}`}>
                    <span className="value-label">Expected (Form)</span>
                    {formatVerificationField(data.expected_value)}
                  </div>
                  <div className="value-box" data-testid={`single-extracted-${field}`}>
                    <span className="value-label">Extracted (Label)</span>
                    {formatVerificationField(data.extracted_value)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default SingleUpload;
