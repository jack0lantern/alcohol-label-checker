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
};

function SingleUpload() {
  const [formPdf, setFormPdf] = useState<File | null>(null);
  const [labelImage, setLabelImage] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SingleVerifyResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    return formPdf != null && labelImage != null && !isSubmitting;
  }, [formPdf, isSubmitting, labelImage]);

  const runSingleCheck = async () => {
    if (!canSubmit) {
      return;
    }

    const payload = new FormData();
    payload.append("form_pdf", formPdf);
    payload.append("label_image", labelImage);

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

      <div className="file-drop-area" onClick={() => document.getElementById("single-label-image")?.click()}>
        <span className="file-name">{labelImage ? labelImage.name : <span className="placeholder">Select Label Image</span>}</span>
      </div>
      <input
        id="single-label-image"
        type="file"
        accept="image/*"
        onChange={(event) => {
          const nextFile = event.currentTarget.files?.[0] ?? null;
          setLabelImage(nextFile);
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
          
          <div className="field-results">
            {Object.entries(result.field_results).map(([field, data]) => (
              <div key={field} className="field-result-item">
                <span className="field-name">{field.replace(/_/g, ' ')}</span>
                <span className={`status-badge ${data.status}`}>{data.status.replace('_', ' ')}</span>
                
                <div className="field-values">
                  <div className="value-box">
                    <span className="value-label">Expected (Form)</span>
                    {data.expected_value || '—'}
                  </div>
                  <div className="value-box">
                    <span className="value-label">Extracted (Label)</span>
                    {data.extracted_value || '—'}
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
