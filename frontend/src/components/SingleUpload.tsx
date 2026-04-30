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
      <h2>Single check</h2>
      <label htmlFor="single-form-pdf">TTB Form PDF</label>
      <input
        id="single-form-pdf"
        type="file"
        accept=".pdf,application/pdf"
        onChange={(event) => {
          const nextFile = event.currentTarget.files?.[0] ?? null;
          setFormPdf(nextFile);
        }}
      />

      <label htmlFor="single-label-image">Label Image</label>
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

      {errorMessage != null ? <p role="alert">{errorMessage}</p> : null}

      {result != null ? (
        <div>
          <h3>Single verification result</h3>
          <p>Overall status: {result.status}</p>
        </div>
      ) : null}
    </section>
  );
}

export default SingleUpload;
