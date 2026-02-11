// In production, frontend is served by the same backend — use relative URLs.
// For local dev with separate servers, set window.__API_BASE__ = "http://localhost:8000"
const API_BASE = window.__API_BASE__ || "";
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

// DOM Elements
const form = document.getElementById("analyzeForm");
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("resumeFile");
const fileInfo = document.getElementById("fileInfo");
const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");
const fileRemove = document.getElementById("fileRemove");
const jobDescription = document.getElementById("jobDescription");
const charCount = document.getElementById("charCount");
const analyzeBtn = document.getElementById("analyzeBtn");
const loadingSection = document.getElementById("loadingSection");
const errorSection = document.getElementById("errorSection");
const errorMessage = document.getElementById("errorMessage");
const retryBtn = document.getElementById("retryBtn");
const resultsSection = document.getElementById("resultsSection");
const newAnalysisBtn = document.getElementById("newAnalysisBtn");

// Enhancement DOM Elements
const enhancePromptSection = document.getElementById("enhancePromptSection");
const enhanceBtn = document.getElementById("enhanceBtn");
const noThanksBtn = document.getElementById("noThanksBtn");
const enhanceLoadingSection = document.getElementById("enhanceLoadingSection");
const comparisonSection = document.getElementById("comparisonSection");
const downloadBtn = document.getElementById("downloadBtn");
const newAnalysisBtn2 = document.getElementById("newAnalysisBtn2");

let selectedFile = null;
let lastAnalysisData = null; // Stores data needed for rewrite request

// ===== Initialization =====
document.addEventListener("DOMContentLoaded", () => {
    setupDropZone();
    setupTextarea();
    setupFormSubmit();
    setupButtons();
});

// ===== Drop Zone =====
function setupDropZone() {
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files[0]) handleFileSelect(fileInput.files[0]);
    });

    fileRemove.addEventListener("click", () => {
        clearFile();
    });
}

function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showInlineError("Please select a PDF file.");
        return;
    }

    if (file.size > MAX_FILE_SIZE) {
        showInlineError("File size exceeds 5MB limit.");
        return;
    }

    if (file.size === 0) {
        showInlineError("File is empty.");
        return;
    }

    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    dropZone.hidden = true;
    fileInfo.hidden = false;
    validateForm();
}

function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    dropZone.hidden = false;
    fileInfo.hidden = true;
    validateForm();
}

function showInlineError(msg) {
    const existing = dropZone.querySelector(".drop-error");
    if (existing) existing.remove();

    const el = document.createElement("p");
    el.className = "drop-error";
    el.style.cssText = "color:#dc2626;font-size:0.8rem;margin-top:8px;font-weight:500;";
    el.textContent = msg;
    dropZone.appendChild(el);

    setTimeout(() => el.remove(), 3000);
}

// ===== Textarea =====
function setupTextarea() {
    jobDescription.addEventListener("input", () => {
        const len = jobDescription.value.length;
        charCount.textContent = `${len} character${len !== 1 ? "s" : ""}`;
        charCount.classList.toggle("valid", len >= 10);
        validateForm();
    });
}

// ===== Form Validation =====
function validateForm() {
    const hasFile = selectedFile !== null;
    const hasText = jobDescription.value.trim().length >= 10;
    analyzeBtn.disabled = !(hasFile && hasText);
}

// ===== Form Submission =====
function setupFormSubmit() {
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (analyzeBtn.disabled) return;
        await analyzeResume();
    });
}

async function analyzeResume() {
    showSection("loading");

    const formData = new FormData();
    formData.append("resume", selectedFile);
    formData.append("job_description", jobDescription.value.trim());

    try {
        const response = await fetch(`${API_BASE}/analyze`, {
            method: "POST",
            body: formData,
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            const msg = data.error || data.detail || "An unexpected error occurred.";
            throw new Error(msg);
        }

        displayResults(data);
        showSection("results");
    } catch (err) {
        if (err.name === "TypeError" && err.message === "Failed to fetch") {
            showError("Cannot connect to the server. Make sure the backend is running on " + API_BASE);
        } else {
            showError(err.message);
        }
    }
}

// ===== Display Results =====
function displayResults(data) {
    const { score, match_percentage, explanation, matched_keywords, resume_word_count, job_description_word_count } = data.data;
    const meta = data.metadata;

    // Score tier
    const tier = getScoreTier(score);
    const scoreCard = document.getElementById("scoreCard");
    scoreCard.className = `score-card ${tier.className}`;

    // Animate score ring
    const ring = document.getElementById("scoreRing");
    const circumference = 2 * Math.PI * 52; // r=52
    const offset = circumference - (score / 100) * circumference;
    ring.style.strokeDasharray = circumference;
    ring.style.strokeDashoffset = circumference;
    // Trigger animation after a frame
    requestAnimationFrame(() => {
        ring.style.strokeDashoffset = offset;
    });

    // Animate score number
    animateNumber("scoreNumber", 0, Math.round(score), 1000);

    // Score label and assessment
    document.getElementById("scoreLabel").textContent = tier.label;
    document.getElementById("scoreAssessment").textContent = tier.assessment;

    // Explanation (convert markdown bold/newlines to HTML)
    document.getElementById("explanationContent").innerHTML = renderMarkdown(explanation);

    // Keywords
    const keywordsList = document.getElementById("keywordsList");
    keywordsList.innerHTML = "";
    if (matched_keywords && matched_keywords.length > 0) {
        matched_keywords.forEach((kw) => {
            const tag = document.createElement("span");
            tag.className = "keyword-tag";
            tag.textContent = kw;
            keywordsList.appendChild(tag);
        });
    } else {
        keywordsList.innerHTML = '<span class="keywords-empty">No matching keywords found</span>';
    }

    // Metadata
    document.getElementById("metaFilename").textContent = meta.filename || "-";
    document.getElementById("metaFileSize").textContent = meta.file_size_kb ? `${meta.file_size_kb} KB` : "-";
    document.getElementById("metaResumeWords").textContent = resume_word_count?.toLocaleString() || "-";
    document.getElementById("metaJobWords").textContent = job_description_word_count?.toLocaleString() || "-";
    document.getElementById("metaTimestamp").textContent = meta.upload_timestamp
        ? new Date(meta.upload_timestamp).toLocaleString()
        : new Date().toLocaleString();

    // Store data for potential rewrite request
    lastAnalysisData = {
        resume_text: data.data.resume_text || "",
        job_description: jobDescription.value.trim(),
        matched_keywords: data.data.matched_keywords || [],
        job_keywords: data.data.job_keywords || [],
        original_score: data.data.score,
    };

    // Show the enhance prompt after a short delay (only if resume_text is available)
    if (lastAnalysisData.resume_text) {
        setTimeout(() => {
            enhancePromptSection.hidden = false;
        }, 600);
    }
}

function getScoreTier(score) {
    if (score >= 80) return { className: "excellent", label: "Excellent Match", assessment: "This resume is a strong match for the position. The candidate demonstrates highly relevant skills and experience." };
    if (score >= 60) return { className: "good", label: "Good Match", assessment: "The resume shows solid alignment with the job requirements. Worth reviewing in detail for a potential interview." };
    if (score >= 40) return { className: "moderate", label: "Moderate Match", assessment: "Some relevant experience is present, but the candidate may be missing key qualifications for this role." };
    return { className: "low", label: "Low Match", assessment: "Limited alignment with the job requirements. The candidate's background may not be suitable for this position." };
}

function animateNumber(elementId, start, end, duration) {
    const el = document.getElementById(elementId);
    const startTime = performance.now();
    const diff = end - start;

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + diff * eased);
        if (progress < 1) requestAnimationFrame(update);
    }

    requestAnimationFrame(update);
}

// ===== Enhancement Flow =====
async function enhanceResume() {
    // Hide results and prompt, show enhance loading
    enhancePromptSection.hidden = true;
    resultsSection.hidden = true;
    showSection("enhance-loading");

    try {
        const response = await fetch(`${API_BASE}/rewrite`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(lastAnalysisData),
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            const msg = data.detail || data.error || "Enhancement failed.";
            throw new Error(msg);
        }

        displayComparison(data);
        showSection("comparison");
    } catch (err) {
        if (err.name === "TypeError" && err.message === "Failed to fetch") {
            showError("Cannot connect to the server.");
        } else {
            showError(err.message);
        }
    }
}

function displayComparison(data) {
    // Score comparison
    document.getElementById("originalScoreDisplay").textContent = `${data.original_score.toFixed(1)}%`;
    document.getElementById("enhancedScoreDisplay").textContent = `${data.updated_score.toFixed(1)}%`;

    // Score improvement
    const improvementEl = document.getElementById("scoreImprovement");
    const sign = data.score_improvement >= 0 ? "+" : "";
    document.getElementById("improvementValue").textContent = `${sign}${data.score_improvement.toFixed(1)}`;

    improvementEl.classList.remove("positive", "negative");
    if (data.score_improvement > 0) {
        improvementEl.classList.add("positive");
    } else if (data.score_improvement < 0) {
        improvementEl.classList.add("negative");
    }

    // Improvements list
    const list = document.getElementById("improvementsList");
    list.innerHTML = "";
    if (data.improvements_summary && data.improvements_summary.length > 0) {
        data.improvements_summary.forEach((item) => {
            const li = document.createElement("li");
            li.textContent = item;
            list.appendChild(li);
        });
    } else {
        const li = document.createElement("li");
        li.textContent = "No significant changes were needed.";
        list.appendChild(li);
    }

    // Updated explanation
    document.getElementById("enhancedExplanationContent").innerHTML =
        renderMarkdown(data.updated_analysis.explanation);

    // Download link
    downloadBtn.href = `${API_BASE}/download/${data.download_id}`;
}

// ===== Section Management =====
function showSection(section) {
    const uploadSection = document.querySelector(".upload-section");
    uploadSection.hidden = section !== "form";
    loadingSection.hidden = section !== "loading";
    errorSection.hidden = section !== "error";
    resultsSection.hidden = section !== "results";
    enhancePromptSection.hidden = true; // Always hide unless explicitly shown
    enhanceLoadingSection.hidden = section !== "enhance-loading";
    comparisonSection.hidden = section !== "comparison";

    if (section !== "form") {
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function showError(msg) {
    errorMessage.textContent = msg;
    showSection("error");
}

// ===== Buttons =====
function setupButtons() {
    retryBtn.addEventListener("click", () => {
        showSection("form");
    });

    newAnalysisBtn.addEventListener("click", () => {
        resetToForm();
    });

    // Enhancement buttons
    enhanceBtn.addEventListener("click", async () => {
        await enhanceResume();
    });

    noThanksBtn.addEventListener("click", () => {
        enhancePromptSection.hidden = true;
    });

    newAnalysisBtn2.addEventListener("click", () => {
        resetToForm();
    });
}

function resetToForm() {
    clearFile();
    jobDescription.value = "";
    charCount.textContent = "0 characters";
    charCount.classList.remove("valid");
    analyzeBtn.disabled = true;
    lastAnalysisData = null;
    showSection("form");
}

// ===== Utilities =====
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function renderMarkdown(text) {
    // Sanitize HTML entities first to prevent XSS
    const escaped = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    // Convert **bold** to <strong>, newlines to <br>
    return escaped
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>");
}
