let uploadedImages = [];
let onlineListing = null;
let inspectionResult = null;

const API_BASE_URL = "http://127.0.0.1:8000";

const pages = [
  "homePage",
  "uploadPage",
  "analysisPage",
  "resultsPage",
  "reportPage"
];

const FIELD_LABELS = {
  product_name: "Product Name",
  manufacturer: "Manufacturer / Responsible Entity",
  net_quantity: "Net Quantity",
  mrp: "Maximum Retail Price (MRP)",
  unit_sale_price: "Unit Sale Price",
  serving_size: "Serving Size",
  packing_date: "Packing Date",
  best_before: "Best Before",
  use_by: "Use By",
  consumer_care: "Consumer Care",
  license_number: "Licence / Registration Number",
  batch_number: "Batch / Lot Number"
};

const $ = id => document.getElementById(id);

let homePage;
let uploadPage;
let analysisPage;
let resultsPage;
let reportPage;

let uploadArea;
let imageInput;
let listingInput;
let imagePreview;
let imageCount;
let analyzeButton;


/* =========================================================
   Utility helpers
   ========================================================= */

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatConfidence(value) {
  const confidence = Number(value);

  if (!Number.isFinite(confidence)) {
    return "—";
  }

  return `${confidence.toFixed(1)}%`;
}

function statusToUi(status) {
  const normalized =
    String(status || "").toUpperCase();

  if (
    normalized === "PASS" ||
    normalized === "MATCH" ||
    normalized === "DETECTED"
  ) {
    return "pass";
  }

  if (
    normalized === "REVIEW_REQUIRED" ||
    normalized === "NOT_DETECTED" ||
    normalized === "NOT_VISIBLE"
  ) {
    return "review";
  }

  if (
    normalized === "POTENTIAL_DISCREPANCY" ||
    normalized === "POTENTIAL_VIOLATION" ||
    normalized === "VIOLATION"
  ) {
    return "violation";
  }

  return "review";
}

function statusLabel(status) {
  const normalized =
    String(status || "").toUpperCase();

  const labels = {
    PASS: "Pass",
    MATCH: "Match",
    DETECTED: "Detected",
    REVIEW_REQUIRED: "Review Required",
    NOT_DETECTED: "Not Detected",
    NOT_VISIBLE: "Not Clearly Visible",
    POTENTIAL_DISCREPANCY: "Potential Discrepancy",
    POTENTIAL_VIOLATION: "Potential Violation",
    VIOLATION: "Potential Violation"
  };

  return (
    labels[normalized] ||
    status ||
    "Review"
  );
}

function formatFieldName(field) {
  return (
    FIELD_LABELS[field] ||
    String(field || "")
      .replace(/_/g, " ")
      .replace(/\b\w/g, char =>
        char.toUpperCase()
      )
  );
}


/* =========================================================
   Navigation
   ========================================================= */

function hidePages() {
  pages.forEach(id => {
    const page = $(id);

    if (page) {
      page.classList.add("hidden");
    }
  });
}

function showPage(id) {
  const page = $(id);

  if (!page) {
    console.warn(
      `LabelLens: page '${id}' not found.`
    );
    return;
  }

  hidePages();
  page.classList.remove("hidden");

  window.scrollTo({
    top: 0,
    behavior: "smooth"
  });
}

function startInspection() {
  showPage("uploadPage");
}

function goHome() {
  showPage("homePage");
}

function scrollToHowItWorks() {
  const section = $("howItWorks");

  if (section) {
    section.scrollIntoView({
      behavior: "smooth"
    });
  }
}

function showResults() {
  if (!inspectionResult) {
    return;
  }

  showPage("resultsPage");
  renderResults();
}

function showReport() {
  if (!inspectionResult) {
    return;
  }

  showPage("reportPage");
  renderReport();
}


/* =========================================================
   Package image upload
   ========================================================= */

function addImages(files) {
  if (!files) {
    return;
  }

  [...files].forEach(file => {
    if (!(file instanceof File)) {
      return;
    }

    if (
      !file.type ||
      !file.type.startsWith("image/")
    ) {
      return;
    }

    uploadedImages.push({
      file,
      url: URL.createObjectURL(file)
    });
  });

  if (imageInput) {
    imageInput.value = "";
  }

  renderImages();
}

function renderImages() {
  if (!imagePreview) {
    return;
  }

  imagePreview.innerHTML = "";

  const names = [
    "Front",
    "Back",
    "Side",
    "Additional"
  ];

  uploadedImages.forEach((image, index) => {
    const card =
      document.createElement("div");

    card.className = "image-card";

    const preview =
      document.createElement("img");

    /*
     * Assign the blob URL directly.
     * This is more reliable than injecting it
     * through innerHTML.
     */
    preview.src = image.url;
    preview.alt =
      names[index] ||
      `Package panel ${index + 1}`;

    const info =
      document.createElement("div");

    info.className = "image-info";

    const label =
      document.createElement("span");

    label.textContent =
      names[index] ||
      `Panel ${index + 1}`;

    const removeButton =
      document.createElement("button");

    removeButton.type = "button";
    removeButton.className = "remove-btn";
    removeButton.textContent = "Remove";

    removeButton.addEventListener(
      "click",
      () => removeImage(index)
    );

    info.appendChild(label);
    info.appendChild(removeButton);

    card.appendChild(preview);
    card.appendChild(info);

    imagePreview.appendChild(card);
  });

  if (imageCount) {
    imageCount.textContent =
      `${uploadedImages.length} image${
        uploadedImages.length === 1
          ? ""
          : "s"
      }`;
  }

  if (analyzeButton) {
    analyzeButton.disabled =
      uploadedImages.length === 0;
  }
}

function removeImage(index) {
  const image =
    uploadedImages[index];

  if (image?.url) {
    URL.revokeObjectURL(image.url);
  }

  uploadedImages.splice(index, 1);

  renderImages();
}


/* =========================================================
   Optional online listing
   ========================================================= */

function handleListingChange(file) {
  if (
    !file ||
    !file.type ||
    !file.type.startsWith("image/")
  ) {
    return;
  }

  if (onlineListing?.url) {
    URL.revokeObjectURL(
      onlineListing.url
    );
  }

  onlineListing = {
    file,
    url: URL.createObjectURL(file)
  };

  renderListing();
}

function renderListing() {
  const preview =
    $("listingPreview");

  const listingImage =
    $("listingImage");

  const listingFileName =
    $("listingFileName");

  if (!preview) {
    return;
  }

  if (!onlineListing) {
    preview.classList.add("hidden");

    if (listingImage) {
      listingImage.removeAttribute("src");
    }

    if (listingFileName) {
      listingFileName.textContent = "";
    }

    return;
  }

  if (listingImage) {
    listingImage.src =
      onlineListing.url;
  }

  if (listingFileName) {
    listingFileName.textContent =
      onlineListing.file.name;
  }

  preview.classList.remove("hidden");
}

function removeListing() {
  if (onlineListing?.url) {
    URL.revokeObjectURL(
      onlineListing.url
    );
  }

  onlineListing = null;

  if (listingInput) {
    listingInput.value = "";
  }

  renderListing();
}

/* =========================================================
   Analysis
   ========================================================= */

async function analyzeProduct() {
  if (!uploadedImages.length) {
    return;
  }

  if (!analyzeButton) {
    console.error(
      "LabelLens: analyze button not found."
    );
    return;
  }

  analyzeButton.disabled = true;

  showPage("analysisPage");

  const analysisLog =
    $("analysisLog");

  if (analysisLog) {
    analysisLog.innerHTML = "";
  }

  resetAnalysis();

  try {
    await runStep(
      1,
      "Reading package images and detecting text regions..."
    );

    const formData =
      new FormData();

    uploadedImages.forEach(
      (item, index) => {
        formData.append(
          "files",
          item.file,
          item.file.name ||
            `panel_${index + 1}.png`
        );
      }
    );

    addLog(
      `Sending ${uploadedImages.length} package image${
        uploadedImages.length === 1
          ? ""
          : "s"
      } to LabelLens backend...`
    );

    const response =
      await fetch(
        `${API_BASE_URL}/upload`,
        {
          method: "POST",
          body: formData
        }
      );

    if (!response.ok) {
      let detail =
        `HTTP ${response.status}`;

      try {
        const errorData =
          await response.json();

        if (
          errorData &&
          errorData.detail
        ) {
          detail =
            errorData.detail;
        }
      } catch {
        // Server may return a non-JSON error.
      }

      throw new Error(detail);
    }

    const backendData =
      await response.json();

    if (
      !backendData ||
      !Array.isArray(
        backendData.results
      )
    ) {
      throw new Error(
        "The backend returned an unexpected response."
      );
    }

    await completeStep(
      1,
      "Package images received successfully."
    );

    await runStep(
      2,
      "Extracting declarations such as MRP, quantity, dates and manufacturer..."
    );

    await completeStep(
      2,
      "Declarations extracted from the uploaded package panels."
    );

    await runStep(
      3,
      "Comparing detected declarations across package panels..."
    );

    await completeStep(
      3,
      "Cross-panel comparison completed."
    );

    await runStep(
      4,
      "Building evidence-backed findings and preparing the inspection report..."
    );

    inspectionResult =
      transformBackendResponse(
        backendData
      );

    await completeStep(
      4,
      "Inspection results are ready."
    );

    if (onlineListing) {
      addLog(
        "Online listing image saved. Listing comparison will be integrated separately."
      );
    }

    setTimeout(
      () => showResults(),
      350
    );

  } catch (error) {
    console.error(
      "LabelLens analysis error:",
      error
    );

    resetAnalysis();

    if (analysisLog) {
      analysisLog.innerHTML = "";
    }

    addLog(
      "Analysis failed."
    );

    addLog(
      `Error: ${
        error?.message ||
        "Unable to connect to the backend."
      }`
    );

    addLog(
      "Make sure the FastAPI server is running at http://127.0.0.1:8000"
    );

    const retryButton =
      document.createElement(
        "button"
      );

    retryButton.type =
      "button";

    retryButton.className =
      "primary-btn";

    retryButton.textContent =
      "Back to Upload";

    retryButton.style.marginTop =
      "20px";

    retryButton.addEventListener(
      "click",
      () => {
        retryButton.remove();

        if (analyzeButton) {
          analyzeButton.disabled =
            uploadedImages.length === 0;
        }

        showPage(
          "uploadPage"
        );
      }
    );

    if (analysisLog) {
      analysisLog.appendChild(
        retryButton
      );
    }

  } finally {
    if (
      !inspectionResult &&
      analyzeButton
    ) {
      analyzeButton.disabled =
        uploadedImages.length === 0;
    }
  }
}

function resetAnalysis() {
  for (let i = 1; i <= 4; i++) {
    const step =
      $(`step${i}`);

    if (!step) {
      continue;
    }

    step.classList.remove(
      "active",
      "completed"
    );
  }
}

function runStep(
  number,
  message
) {
  return new Promise(
    resolve => {
      const step =
        $(`step${number}`);

      if (step) {
        step.classList.add(
          "active"
        );
      }

      addLog(message);

      setTimeout(
        resolve,
        450
      );
    }
  );
}

function completeStep(
  number,
  message
) {
  return new Promise(
    resolve => {
      const step =
        $(`step${number}`);

      if (step) {
        step.classList.remove(
          "active"
        );

        step.classList.add(
          "completed"
        );
      }

      addLog(
        `✓ ${message}`
      );

      setTimeout(
        resolve,
        250
      );
    }
  );
}

function addLog(message) {
  const analysisLog =
    $("analysisLog");

  if (!analysisLog) {
    return;
  }

  const line =
    document.createElement(
      "p"
    );

  line.textContent =
    `> ${message}`;

  analysisLog.appendChild(
    line
  );

  analysisLog.scrollTop =
    analysisLog.scrollHeight;
}


/* =========================================================
   Backend response transformation
   ========================================================= */

function transformBackendResponse(
  data
) {
  const results =
    Array.isArray(data?.results)
      ? data.results
      : [];

  const comparisons =
    Array.isArray(data?.comparisons)
      ? data.comparisons
      : [];

  const successfulResults =
    results.filter(
      result => !result?.error
    );

  const productName =
    findBestProductName(
      successfulResults
    );

  const declarations =
    buildDeclarationRows(
      successfulResults
    );

  const findings =
    buildFindings(
      successfulResults,
      comparisons
    );

  const statusInfo =
    calculateOverallStatus(
      successfulResults,
      comparisons
    );

  return {
    productName,
    status:
      statusInfo.status,
    message:
      statusInfo.message,
    declarations,
    comparisons,
    findings,
    backendResults:
      results
  };
}


/* =========================================================
   Product identity
   ========================================================= */

function findBestProductName(
  results
) {
  const candidates = [];

  results.forEach(
    result => {
      const field =
        result
          ?.declarations
          ?.product_name;

      if (
        !field ||
        field.status !==
          "detected" ||
        !field.value
      ) {
        return;
      }

      const value =
        String(field.value)
          .trim();

      const confidence =
        Number(
          field.confidence || 0
        );

      if (
        !value ||
        confidence < 60
      ) {
        return;
      }

      /*
       * Reject obvious OCR garbage.
       * These are intentionally conservative checks,
       * not product-specific rules.
       */
      if (
        value.length < 3 ||
        value.length > 80 ||
        /^[^a-zA-Z]*$/.test(value) ||
        /\b(if|the|and|for|with|ever)\b/i.test(
          value
        )
      ) {
        return;
      }

      candidates.push({
        value,
        confidence
      });
    }
  );

  if (!candidates.length) {
    return "Inspection Result";
  }

  candidates.sort(
    (a, b) =>
      b.confidence -
      a.confidence
  );

  return candidates[0].value;
}


/* =========================================================
   Package-wide declaration aggregation
   ========================================================= */

function buildDeclarationRows(
  results
) {
  const rows = [];

  results.forEach(
    (result, index) => {
      const declarations =
        result?.declarations ||
        {};

      Object.entries(
        FIELD_LABELS
      ).forEach(
        ([fieldName, label]) => {
          const field =
            declarations[fieldName];

          if (
            !field ||
            typeof field !==
              "object"
          ) {
            return;
          }

          const hasValue =
            field.value !== null &&
            field.value !== undefined &&
            field.value !== "";

          const status =
            field.status ||
            "not_detected";

          /*
           * Do not display fields that are
           * completely absent from this panel.
           */
          if (
            !hasValue &&
            status ===
              "not_detected"
          ) {
            return;
          }

          rows.push({
            panel:
              result.filename ||
              `Panel ${index + 1}`,

            name: label,

            value:
              hasValue
                ? field.value
                : "Not clearly captured",

            confidence:
              Number(
                field.confidence
              ) || 0,

            rawStatus:
              status,

            status:
              statusToUi(status),

            evidence:
              field.evidence ||
              null
          });
        }
      );
    }
  );

  return rows;
}


/*
 * Determine whether a declaration exists
 * reliably anywhere on the supplied package.
 */
function packageFieldIsDetected(
  results,
  fieldName
) {
  return results.some(
    result => {
      const field =
        result
          ?.declarations
          ?.[fieldName];

      return (
        field &&
        field.status ===
          "detected" &&
        field.value !== null &&
        field.value !==
          undefined &&
        field.value !== ""
      );
    }
  );
}


/* =========================================================
   Findings aggregation
   ========================================================= */

function buildFindings(
  results,
  comparisons
) {
  const findings = [];

  /*
   * Handle actual image-processing errors.
   */
  results.forEach(
    result => {
      if (!result?.error) {
        return;
      }

      findings.push({
        title:
          `Image processing issue: ${
            result.filename ||
            "uploaded image"
          }`,

        description:
          "This package image could not be processed successfully and should be reviewed manually.",

        status:
          "review",

        evidence:
          result.error
      });
    }
  );


  /*
   * Collect package-wide compliance review items.
   *
   * A missing declaration on one panel is NOT
   * reported when that declaration was detected
   * somewhere else on the package.
   */
  const reviewFields =
    new Map();

  results.forEach(
    result => {
      if (result?.error) {
        return;
      }

      const checks =
        result
          ?.compliance
          ?.checks || [];

      checks.forEach(
        check => {
          if (
            check?.status !==
            "REVIEW_REQUIRED"
          ) {
            return;
          }

          const fieldName =
            check.field ||
            check.label ||
            "unknown";

          if (
            packageFieldIsDetected(
              results,
              check.field
            )
          ) {
            return;
          }

          if (
            !reviewFields.has(
              fieldName
            )
          ) {
            reviewFields.set(
              fieldName,
              {
                label:
                  check.label ||
                  FIELD_LABELS[
                    check.field
                  ] ||
                  check.field ||
                  "Declaration",

                reason:
                  check.reason ||
                  "Manual verification is required.",

                evidence: [],

                confidence:
                  check.confidence
              }
            );
          }

          const item =
            reviewFields.get(
              fieldName
            );

          if (
            check.evidence
          ) {
            const evidence =
              typeof check.evidence ===
              "string"
                ? check.evidence
                : JSON.stringify(
                    check.evidence
                  );

            item.evidence.push(
              `${result.filename || "Panel"}: ${evidence}`
            );
          }
        }
      );
    }
  );

  reviewFields.forEach(
    (item, fieldName) => {
      findings.push({
        title:
          `${item.label}`,

        description:
          item.reason,

        status:
          "review",

        evidence:
          item.evidence.length
            ? item.evidence.join(
                " · "
              )
            : "The value was not clearly captured from the supplied package images.",

        field:
          fieldName
      });
    }
  );


  /*
   * Cross-panel discrepancies remain separate
   * because these are one of the core features
   * of LabelLens.
   */
  comparisons.forEach(
    comparison => {
      if (!comparison) {
        return;
      }

      if (
        comparison.status ===
        "MATCH"
      ) {
        return;
      }

      const sourceText =
        Array.isArray(
          comparison.sources
        )
          ? comparison.sources
              .map(
                source =>
                  `${source.filename || "Panel"}: ${source.value}`
              )
              .join(" · ")
          : "";

      if (
        comparison.status ===
        "POTENTIAL_DISCREPANCY"
      ) {
        findings.push({
          title:
            `${formatFieldName(
              comparison.field
            )} differs across panels`,

          description:
            comparison.message ||
            "Different values were detected across the supplied panels.",

          status:
            "violation",

          evidence:
            sourceText ||
            "Multiple package-panel values were detected.",

          field:
            comparison.field
        });

        return;
      }

      if (
        comparison.status ===
        "REVIEW_REQUIRED"
      ) {
        findings.push({
          title:
            `${formatFieldName(
              comparison.field
            )} requires verification`,

          description:
            comparison.message ||
            "Manual verification is required.",

          status:
            "review",

          evidence:
            sourceText ||
            "Conflicting or uncertain values were detected.",

          field:
            comparison.field
        });
      }
    }
  );


  /*
   * Keep the findings section useful when
   * there really are no review items.
   */
  if (!findings.length) {
    findings.push({
      title:
        "No additional findings",

      description:
        "The automated inspection did not generate any additional review findings from the available package evidence.",

      status:
        "pass",

      evidence:
        "Automated inspection checks"
    });
  }

  return findings;
}

/* =========================================================
   Compliance / finding helpers
   ========================================================= */

function buildCheckEvidence(
  filename,
  check
) {
  const prefix =
    filename || "Package image";

  if (!check?.evidence) {
    return `${prefix}: ${
      check?.value ||
      "Value not clearly captured"
    }`;
  }

  if (
    typeof check.evidence ===
    "string"
  ) {
    return `${prefix}: ${check.evidence}`;
  }

  if (
    typeof check.evidence ===
    "object"
  ) {
    return `${prefix}: ${
      check.evidence.text ||
      check.value ||
      "Evidence captured"
    }`;
  }

  return `${prefix}: Evidence captured`;
}


/* =========================================================
   Overall inspection status
   ========================================================= */

function calculateOverallStatus(
  results,
  comparisons
) {
  const hasDiscrepancy =
    comparisons.some(
      item =>
        item?.status ===
        "POTENTIAL_DISCREPANCY"
    );

  if (hasDiscrepancy) {
    return {
      status: "violation",

      message:
        "Potential discrepancies were detected across the uploaded package panels. Manual verification is required."
    };
  }

  const hasComparisonReview =
    comparisons.some(
      item =>
        item?.status ===
        "REVIEW_REQUIRED"
    );

  const hasComplianceReview =
    results.some(
      result =>
        (
          result?.compliance
            ?.checks || []
        ).some(
          check =>
            check?.status ===
            "REVIEW_REQUIRED"
        )
    );

  if (
    hasComparisonReview ||
    hasComplianceReview
  ) {
    return {
      status: "review",

      message:
        "The package was processed successfully, but one or more declarations require manual verification."
    };
  }

  return {
    status: "pass",

    message:
      "The uploaded package panels were processed successfully and no potential discrepancy was detected."
  };
}


/* =========================================================
   Results
   ========================================================= */

function renderResults() {
  if (!inspectionResult) {
    return;
  }

  const productName =
    $("productName");

  const inspectionDate =
    $("inspectionDate");

  if (productName) {
    productName.textContent =
      inspectionResult.productName ||
      "Inspection Result";
  }

  if (inspectionDate) {
    inspectionDate.textContent =
      `Inspected on ${new Date().toLocaleString()}`;
  }

  renderOverallStatus();
  renderSummary();
  renderDeclarations();
  renderComparisons();
  renderFindings();
}


/* =========================================================
   Overall result card
   ========================================================= */

function renderOverallStatus() {
  const container =
    $("overallStatus");

  const title =
    $("overallTitle");

  const message =
    $("overallMessage");

  const badge =
    $("overallBadge");

  if (!container) {
    return;
  }

  const status =
    inspectionResult.status ||
    "review";

  container.className =
    `overall-status ${status}`;

  if (status === "pass") {
    if (title) {
      title.textContent =
        "No Potential Discrepancy Detected";
    }

    if (badge) {
      badge.textContent =
        "PASS";

      badge.className =
        "status-badge pass";
    }
  } else if (
    status === "violation"
  ) {
    if (title) {
      title.textContent =
        "Potential Discrepancy Detected";
    }

    if (badge) {
      badge.textContent =
        "POTENTIAL DISCREPANCY";

      badge.className =
        "status-badge violation";
    }
  } else {
    if (title) {
      title.textContent =
        "Manual Review Required";
    }

    if (badge) {
      badge.textContent =
        "REVIEW REQUIRED";

      badge.className =
        "status-badge review";
    }
  }

  if (message) {
    message.textContent =
      inspectionResult.message ||
      "Inspection completed.";
  }
}


/* =========================================================
   Summary cards
   ========================================================= */

function renderSummary() {
  const container =
    $("summary");

  if (!container) {
    return;
  }

  const declarationCount =
    inspectionResult
      .declarations
      .length;

  const matchCount =
    inspectionResult
      .comparisons
      .filter(
        comparison =>
          comparison.status ===
          "MATCH"
      )
      .length;

  const reviewDeclarationCount =
    inspectionResult
      .declarations
      .filter(
        declaration =>
          declaration.status ===
          "review"
      )
      .length;

  const comparisonReviewCount =
    inspectionResult
      .comparisons
      .filter(
        comparison =>
          comparison.status ===
          "REVIEW_REQUIRED"
      )
      .length;

  const reviewCount =
    reviewDeclarationCount +
    comparisonReviewCount;

  const discrepancyCount =
    inspectionResult
      .comparisons
      .filter(
        comparison =>
          comparison.status ===
          "POTENTIAL_DISCREPANCY"
      )
      .length;

  container.innerHTML = `
    <div class="summary-card">
      <span>
        DECLARATION RECORDS
      </span>

      <strong>
        ${declarationCount}
      </strong>
    </div>

    <div class="summary-card">
      <span>
        PANEL MATCHES
      </span>

      <strong>
        ${matchCount}
      </strong>
    </div>

    <div class="summary-card">
      <span>
        REVIEW ITEMS
      </span>

      <strong>
        ${reviewCount}
      </strong>
    </div>

    <div class="summary-card">
      <span>
        DISCREPANCIES
      </span>

      <strong>
        ${discrepancyCount}
      </strong>
    </div>
  `;
}


/* =========================================================
   Status badge
   ========================================================= */

function renderStatusBadge(
  status
) {
  const uiStatus =
    statusToUi(status);

  return `
    <span class="badge ${uiStatus}">
      ${escapeHtml(
        statusLabel(status)
      )}
    </span>
  `;
}


/* =========================================================
   Declaration table
   ========================================================= */

function renderDeclarations(
  targetId = "declarations"
) {
  const container =
    $(targetId);

  if (!container) {
    return;
  }

  const rows =
    inspectionResult.declarations;

  if (!rows.length) {
    container.innerHTML = `
      <div class="finding">
        <strong>
          No declarations were clearly extracted.
        </strong>

        <p>
          Review the uploaded package images manually.
        </p>
      </div>
    `;

    return;
  }

  container.innerHTML = `
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Panel</th>
            <th>Declaration</th>
            <th>Value</th>
            <th>Confidence</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          ${rows.map(row => `
            <tr>
              <td>
                ${escapeHtml(
                  row.panel
                )}
              </td>

              <td>
                ${escapeHtml(
                  row.name
                )}
              </td>

              <td>
                ${escapeHtml(
                  String(row.value)
                )}
              </td>

              <td>
                ${escapeHtml(
                  formatConfidence(
                    row.confidence
                  )
                )}
              </td>

              <td>
                ${renderStatusBadge(
                  row.rawStatus
                )}
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}


/* =========================================================
   Cross-panel comparison table
   ========================================================= */

function renderComparisons(
  targetId = "comparisons"
) {
  const container =
    $(targetId);

  if (!container) {
    return;
  }

  const comparisons =
    inspectionResult.comparisons;

  if (!comparisons.length) {
    container.innerHTML = `
      <div class="finding">
        <strong>
          No cross-panel comparison was available.
        </strong>

        <p>
          A field must be detected on at least
          two supplied panels to be compared.
        </p>
      </div>
    `;

    return;
  }

  container.innerHTML = `
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Panel Values</th>
            <th>Status</th>
          </tr>
        </thead>

        <tbody>
          ${comparisons.map(
            comparison => `
              <tr>
                <td>
                  <strong>
                    ${escapeHtml(
                      formatFieldName(
                        comparison.field
                      )
                    )}
                  </strong>
                </td>

                <td>
                  ${
                    Array.isArray(
                      comparison.sources
                    )
                      ? comparison.sources
                          .map(
                            source => `
                              <div class="comparison-value">
                                <strong>
                                  ${escapeHtml(
                                    source.filename ||
                                    "Panel"
                                  )}
                                </strong>

                                :
                                ${escapeHtml(
                                  String(
                                    source.value
                                  )
                                )}

                                ${
                                  source.confidence !==
                                  undefined
                                    ? `
                                      <span>
                                        (
                                        ${escapeHtml(
                                          formatConfidence(
                                            source.confidence
                                          )
                                        )}
                                        )
                                      </span>
                                    `
                                    : ""
                                }
                              </div>
                            `
                          )
                          .join("")
                      : "—"
                  }
                </td>

                <td>
                  ${renderStatusBadge(
                    comparison.status
                  )}
                </td>
              </tr>
            `
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

/* =========================================================
   Findings
   ========================================================= */

function renderFindings(
  targetId = "findings"
) {
  const container =
    $(targetId);

  if (!container) {
    return;
  }

  const findings =
    inspectionResult.findings;

  if (!findings.length) {
    container.innerHTML = `
      <div class="finding pass">
        <div class="finding-top">
          <strong>
            No additional findings
          </strong>

          ${renderStatusBadge("PASS")}
        </div>

        <p>
          No additional review items were produced
          by the automated inspection checks.
        </p>
      </div>
    `;

    return;
  }

  container.innerHTML =
    findings.map(finding => `
      <div class="finding ${escapeHtml(
        finding.status || "review"
      )}">
        <div class="finding-top">
          <strong>
            ${escapeHtml(
              finding.title ||
              "Inspection finding"
            )}
          </strong>

          ${renderStatusBadge(
            finding.status
          )}
        </div>

        <p>
          ${escapeHtml(
            finding.description ||
            "Manual verification is required."
          )}
        </p>

        ${
          finding.evidence
            ? `
              <div class="evidence">
                <strong>Evidence:</strong>
                ${escapeHtml(
                  String(
                    finding.evidence
                  )
                )}
              </div>
            `
            : ""
        }
      </div>
    `).join("");
}


/* =========================================================
   Report
   ========================================================= */

function renderReport() {
  if (!inspectionResult) {
    return;
  }

  const reportProductName =
    $("reportProductName");

  const reportDate =
    $("reportDate");

  const reportStatus =
    $("reportStatus");

  const reportMessage =
    $("reportMessage");

  if (reportProductName) {
    reportProductName.textContent =
      inspectionResult.productName ||
      "Inspection Result";
  }

  if (reportDate) {
    reportDate.textContent =
      new Date().toLocaleString();
  }

  if (reportStatus) {
    if (
      inspectionResult.status ===
      "pass"
    ) {
      reportStatus.textContent =
        "PASS";
    } else if (
      inspectionResult.status ===
      "violation"
    ) {
      reportStatus.textContent =
        "POTENTIAL DISCREPANCY";
    } else {
      reportStatus.textContent =
        "REVIEW REQUIRED";
    }
  }

  if (reportMessage) {
    reportMessage.textContent =
      inspectionResult.message ||
      "Inspection completed.";
  }

  renderDeclarations(
    "reportDeclarations"
  );

  renderComparisons(
    "reportComparisons"
  );

  renderFindings(
    "reportFindings"
  );
}


/* =========================================================
   Event listeners
   ========================================================= */

function setupEventListeners() {

  /*
   * Package image upload area.
   */
  if (
    uploadArea &&
    imageInput
  ) {
    uploadArea.addEventListener(
      "click",
      () => {
        imageInput.click();
      }
    );

    uploadArea.addEventListener(
      "dragover",
      event => {
        event.preventDefault();
        uploadArea.classList.add(
          "dragging"
        );
      }
    );

    uploadArea.addEventListener(
      "dragleave",
      () => {
        uploadArea.classList.remove(
          "dragging"
        );
      }
    );

    uploadArea.addEventListener(
      "drop",
      event => {
        event.preventDefault();

        uploadArea.classList.remove(
          "dragging"
        );

        addImages(
          event.dataTransfer.files
        );
      }
    );
  }


  /*
   * File picker.
   */
  if (imageInput) {
    imageInput.addEventListener(
      "change",
      event => {
        addImages(
          event.target.files
        );
      }
    );
  }


  /*
   * Optional online listing.
   */
  if (listingInput) {
    listingInput.addEventListener(
      "change",
      event => {
        const file =
          event.target.files?.[0];

        handleListingChange(file);
      }
    );
  }


  /*
   * Analyze button.
   */
  if (analyzeButton) {
    analyzeButton.addEventListener(
      "click",
      analyzeProduct
    );
  }


  /*
   * Existing navigation buttons
   * that use data-page.
   */
  document
    .querySelectorAll(
      "[data-page]"
    )
    .forEach(button => {
      button.addEventListener(
        "click",
        () => {
          const page =
            button.dataset.page;

          if (
            pages.includes(page)
          ) {
            showPage(page);
          }
        }
      );
    });


  /*
   * Back to upload.
   */
  const backToUpload =
    $("backToUpload");

  if (backToUpload) {
    backToUpload.addEventListener(
      "click",
      () => {
        showPage(
          "uploadPage"
        );
      }
    );
  }


  /*
   * Back to results.
   */
  const backToResults =
    $("backToResults");

  if (backToResults) {
    backToResults.addEventListener(
      "click",
      () => {
        if (!inspectionResult) {
          return;
        }

        showPage(
          "resultsPage"
        );

        renderResults();
      }
    );
  }


  /*
   * Report button.
   */
  const reportButton =
    $("reportButton");

  if (reportButton) {
    reportButton.addEventListener(
      "click",
      showReport
    );
  }


  /*
   * Print / Save PDF.
   */
  const printButton =
    $("printButton");

  if (printButton) {
    printButton.addEventListener(
      "click",
      () => {
        window.print();
      }
    );
  }


  /*
   * Optional explicit listing
   * removal button.
   */
  const removeListingButton =
    $("removeListingButton");

  if (removeListingButton) {
    removeListingButton.addEventListener(
      "click",
      removeListing
    );
  }
}


/* =========================================================
   Existing inline HTML compatibility
   ========================================================= */

window.startInspection =
  startInspection;

window.goHome =
  goHome;

window.scrollToHowItWorks =
  scrollToHowItWorks;

window.showResults =
  showResults;

window.showReport =
  showReport;

window.removeImage =
  removeImage;

window.removeListing =
  removeListing;

window.analyzeProduct =
  analyzeProduct;


/* =========================================================
   Initialize after HTML loads
   ========================================================= */

document.addEventListener(
  "DOMContentLoaded",
  () => {

    /*
     * Resolve all DOM references only after
     * the HTML has been parsed.
     */
    homePage =
      $("homePage");

    uploadPage =
      $("uploadPage");

    analysisPage =
      $("analysisPage");

    resultsPage =
      $("resultsPage");

    reportPage =
      $("reportPage");

    uploadArea =
      $("uploadArea");

    imageInput =
      $("imageInput");

    listingInput =
      $("listingInput");

    imagePreview =
      $("imagePreview");

    imageCount =
      $("imageCount");

    analyzeButton =
      $("analyzeButton");


    /*
     * Start at the home page.
     */
    showPage(
      "homePage"
    );


    /*
     * Analyze starts disabled
     * until at least one image exists.
     */
    if (analyzeButton) {
      analyzeButton.disabled =
        uploadedImages.length === 0;
    }


    /*
     * Activate all interactions.
     */
    setupEventListeners();


    /*
     * Render initial empty states.
     */
    renderImages();
    renderListing();
  }
);