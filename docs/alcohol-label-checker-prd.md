# **Product Requirements Document**

## **1\. Overview**

**Product Summary:** A standalone, AI-powered Python web application deployed on Azure that automatically extracts text from alcohol label images and verifies it against the submitted TTB F 5100.31 application form data.

**Problem Statement:** The TTB Compliance Division processes 150,000 label applications annually using a highly manual "stare-and-compare" visual check, which bottlenecks operations. A previous vendor pilot failed because processing took up to 40 seconds per label. **Target Users:** TTB Compliance Agents, who possess widely varying levels of technical literacy.

## ---

**2\. Goals & Success Metrics**

**Business Goals:**

* Automate the data entry verification of routine application fields to free up agent time.

* Handle large bulk submissions (200–300 applications) during peak seasons without system crashes or massive manual backlogs.

**User Goals:**

* Provide an incredibly simple UI ("something my mother could figure out") requiring zero training.

* Deliver pass/fail match results faster than manual review.

**Measurable Success Criteria:**

* **Latency:** Label processing and verification must complete in **\<= 5 seconds** per item.  
* **Accuracy:** Maintain strict legal compliance for warning statements using an "OCR-aware" exact matching algorithm.

## ---

**3\. User Personas**

* **Persona 1: Dave (Senior Agent, 28 years).** Low tech-literacy (prints emails). Highly skeptical of "modernization" due to past failures. Needs the tool to assist his workflow without overriding his judgment on nuanced label variations.

* **Persona 2: Jenny (Junior Agent, 8 months).** High tech-literacy. Frustrated by manual printed checklists. Keen eye for exact legal compliance, particularly catching improper casing on warning labels. Needs the tool to handle poor-quality, glaring, or angled photo submissions.

## ---

**4\. User Workflow**

* **Current Workflow:** Agents open the COLA application, pull up the label artwork, and visually compare each field line-by-line (5-10 minutes per application).

* **Improved Workflow (Single):** The agent uploads a completed TTB F 5100.31 PDF form and the corresponding label image into the app. The system extracts the ground truth data from the PDF, runs local OCR on the image, and highlights matches/discrepancies in under 5 seconds.  
* **Improved Workflow (Batch):** The agent uploads a folder containing up to 300 PDF forms, 300 label images, and a CSV file mapping the form filenames to the label filenames. The UI immediately confirms upload and displays real-time processing progress as the async queue churns through the batch.

## ---

**5\. Functional Requirements**

* **FR1: Ground Truth Ingestion (Single & Batch).** \* Single: The system must parse uploaded TTB F 5100.31 PDFs to establish base ground truth data, specifically targeting Item 5 for Product Type , Item 6 for Brand Name , and Item 8 for Name and Address.

  * Batch: The system must accept a folder upload containing a CSV file with "form" and "label" columns to map the PDF files to their respective image files for bulk processing.  
* **FR2: Target Data Extraction.** The application must extract the following fields from the label image: Brand name, Class/type designation, Alcohol content, Net contents, Name and address of bottler/producer, Country of origin (imports), and the Government Health Warning Statement.  
* **FR3: Case-Insensitive Matching.** General field comparisons between the PDF application data and the image OCR text must be case-insensitive to account for acceptable styling variations.  
* **FR4: OCR-Aware "Exact" Matching (Government Warning).** The system must enforce an exact word and capitalization match for the mandated legal warning. However, to accommodate unavoidable OCR artifacts (e.g., periods read as commas), the system must utilize a Levenshtein distance threshold of \~99% or highly targeted regex stripping to avoid false rejections.  
* **FR5: Image Preprocessing.** The system must automatically correct label images with bad lighting, odd angles, or glare before performing text extraction.

## ---

**6\. Non-Functional Requirements**

* **Performance (Latency & Throughput):** The system must maintain a strict processing SLA of \<= 5 seconds per label. Bulk uploads (up to 300 labels) must be processed asynchronously without timing out the client application.  
* **Security (Zero-Retention Policy):** **NO PII** may be stored. Because Item 8 (Name and Address) may contain sensitive proprietor data, the application must operate completely in memory (RAM). Uploaded PDFs, CSVs, images, and extracted text must be instantly destroyed once the HTTP response is sent. No databases or local disk caches are permitted.

* **Infrastructure:** Must be built with a **Python backend** and deployed on **Azure**. Standard CPU VMs (e.g., Standard\_D4s\_v3) should be targeted to accommodate prototype constraints.  
* **Network Integration:** Must operate as a **standalone app** with no integration to the legacy .NET COLA system. Outbound network requests must be minimized to avoid government firewall blocks.

## ---

**7\. System Design Considerations**

* **PDF Parsing Engine:** Utilize lightweight Python libraries (e.g., pdfplumber or PyMuPDF) to quickly extract ground truth coordinates from the standardized TTB F 5100.31 form.  
* **Two-Tiered Local OCR Stack:** Rely on open-source, local engines. Start with CPU-friendly Tesseract/PyTesseract for maximum speed. If confidence scores fall below a threshold due to complex fonts, gracefully fallback to a deeper learning model (like EasyOCR), budget permitting.  
* **Preprocessing Pipeline:** Implement OpenCV, Pillow, and NumPy for grayscale conversion, deskewing, noise removal, and adaptive thresholding to sculpt images prior to OCR.  
* **Asynchronous Queue Architecture:** Implement an async worker queue (e.g., Celery \+ Redis, or Azure Queue Storage) in the Python backend to handle CSV bulk uploads securely and reliably.

## ---

**8\. UX/UI Requirements**

* **Simplicity:** The interface must be visually clean, accessible, and require no manual hunting for options.

* **Batch Upload UX:** Utilize a directory upload input (e.g., \<input type="file" webkitdirectory /\>) allowing users to drag and drop an entire folder holding the CSV, PDFs, and Images simultaneously.  
* **Feedback & Real-time Progress:** Use WebSockets or long-polling to provide live UI updates during batch runs (e.g., "Processed 45/300...").  
* **Error Handling:** Gracefully flag unreadable images or forms for human review. Visually confirm verified matches and explicitly highlight discrepancies.

## ---

**9\. Edge Cases & Risks**

* **Risk:** High false-rejection rate on the Government Warning due to tiny fonts and camera glare.

  * *Mitigation:* The two-tiered OCR stack and OCR-aware Levenshtein distance string matching.  
* **Risk:** Client browser timeouts during 300-item bulk uploads.  
  * *Mitigation:* Asynchronous job queuing and WebSocket progress updates.  
* **Risk:** External ML APIs blocked by TTB firewalls.

  * *Mitigation:* Strict enforcement of 100% local/edge processing for all OCR and parsing tasks.

## ---

**10\. MVP Scope**

* Standalone Python web application deployed to a standard Azure instance.  
* Simple frontend supporting single file uploads and folder directory uploads.  
* Ground truth extraction from TTB F 5100.31 using pdfplumber.  
* OpenCV image preprocessing.  
* Local Tesseract OCR text extraction (zero external APIs).  
* Verification logic for all 7 core fields, featuring regex/Levenshtein matching for the mandatory Government Warning.  
* In-memory zero-retention data security layer.

## ---

**11\. Future Enhancements**

* Direct API integration with the legacy .NET COLA system to fetch ground truth data directly from the TTB database, eliminating the need for PDF and CSV uploads.

* Heavy GPU-accelerated computer vision models (e.g., Donut) capable of reading heavily distorted bottles without manual agent rejection.

## ---

**12\. Open Questions / Assumptions**

* **Azure Quotas:** Will the provided Azure prototype environment allow the deployment of a basic Redis instance to support the Celery asynchronous worker queue, or should we default to Python's built-in asyncio for a simpler, albeit less robust, in-memory queue? **Use asyncio**