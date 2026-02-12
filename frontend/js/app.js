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

// Recommendations DOM Elements
const viewRecommendationsBtn2 = document.getElementById("viewRecommendationsBtn2");
const viewAllRecommendationsBtn = document.getElementById("viewAllRecommendationsBtn");
const recommendationsLoadingSection = document.getElementById("recommendationsLoadingSection");
const recommendationsSection = document.getElementById("recommendationsSection");
const newAnalysisBtn3 = document.getElementById("newAnalysisBtn3");

let selectedFile = null;
let lastAnalysisData = null; // Stores data needed for rewrite request
let selectedRoleTemplate = null; // Selected role template for enhancement

// ===== Initialization =====
document.addEventListener("DOMContentLoaded", () => {
    setupDropZone();
    setupTextarea();
    setupFormSubmit();
    setupButtons();
    setupRoleSelection();
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

    // Display section scores if available
    if (data.data.section_scores) {
        displaySectionScores(data.data.section_scores);
    }

    // Show the enhance prompt after a short delay (only if resume_text is available)
    if (lastAnalysisData.resume_text) {
        setTimeout(() => {
            enhancePromptSection.hidden = false;
        }, 600);

        // Auto-fetch job recommendations in the background
        fetchRecommendationsInline();
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
        const requestBody = { ...lastAnalysisData };
        if (selectedRoleTemplate) {
            requestBody.role_preference = selectedRoleTemplate;
        }

        const response = await fetch(`${API_BASE}/rewrite`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
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
    recommendationsLoadingSection.hidden = section !== "recommendations-loading";
    recommendationsSection.hidden = section !== "recommendations";

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

    // Recommendations buttons
    viewRecommendationsBtn2.addEventListener("click", async () => {
        await fetchRecommendations();
    });

    viewAllRecommendationsBtn.addEventListener("click", () => {
        showSection("recommendations");
    });

    newAnalysisBtn3.addEventListener("click", () => {
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
    selectedRoleTemplate = null;

    // Reset role selection
    document.querySelectorAll(".role-card").forEach(c => c.classList.remove("selected"));
    if (enhanceBtn) {
        enhanceBtn.disabled = true;
        enhanceBtn.querySelector(".btn-text")?.remove();
        enhanceBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
            </svg>
            Select a Template to Enhance`;
    }

    // Reset section scores
    const sectionScoresContainer = document.getElementById("sectionScoresContainer");
    if (sectionScoresContainer) sectionScoresContainer.hidden = true;

    // Reset inline recommendations
    const inlineSection = document.getElementById("inlineRecommendations");
    if (inlineSection) inlineSection.hidden = true;

    showSection("form");
}

// ===== Recommendations Flow =====

// Full-page navigation (from button clicks)
async function fetchRecommendations() {
    if (!lastAnalysisData || !lastAnalysisData.resume_text) {
        showError("No resume data available. Please analyze a resume first.");
        return;
    }

    showSection("recommendations-loading");

    try {
        const data = await _callRecommendationsAPI();
        displayRecommendations(data);
        showSection("recommendations");
    } catch (err) {
        if (err.name === "TypeError" && err.message === "Failed to fetch") {
            showError("Cannot connect to the server.");
        } else {
            showError(err.message);
        }
    }
}

// Inline fetch (auto-triggered after analysis, renders below results)
async function fetchRecommendationsInline() {
    const inlineSection = document.getElementById("inlineRecommendations");
    const inlineLoading = document.getElementById("inlineRecommendationsLoading");
    const inlineContent = document.getElementById("inlineRecommendationsContent");
    const inlineEmpty = document.getElementById("inlineRecommendationsEmpty");

    if (!inlineSection) return;

    inlineSection.hidden = false;
    inlineLoading.hidden = false;
    inlineContent.hidden = true;
    inlineEmpty.hidden = true;

    try {
        const data = await _callRecommendationsAPI();

        inlineLoading.hidden = true;

        if (!data.recommendations || data.recommendations.length === 0) {
            inlineEmpty.hidden = false;
            return;
        }

        // Populate inline profile summary
        const profileBadge = document.getElementById("inlineProfileBadge");
        profileBadge.textContent =
            `${data.profile.experience_level.charAt(0).toUpperCase() + data.profile.experience_level.slice(1)} ` +
            `\u00B7 ${data.profile.skill_count} skills ` +
            `\u00B7 ${data.profile.domains.slice(0, 3).join(", ")}`;

        // Populate inline job cards
        const grid = document.getElementById("inlineJobCardsGrid");
        grid.innerHTML = "";
        data.recommendations.forEach((job, index) => {
            const card = createJobCard(job, index);
            grid.appendChild(card);
        });

        inlineContent.hidden = false;

        // Also populate the full-page view in case user clicks "View All"
        displayRecommendations(data);
    } catch {
        inlineLoading.hidden = true;
        inlineEmpty.hidden = false;
    }
}

async function _callRecommendationsAPI() {
    const response = await fetch(`${API_BASE}/recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            resume_text: lastAnalysisData.resume_text,
            matched_keywords: lastAnalysisData.matched_keywords || [],
            job_keywords: lastAnalysisData.job_keywords || [],
        }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
        const msg = data.detail || data.error || "Failed to generate recommendations.";
        throw new Error(msg);
    }

    return data;
}

function displayRecommendations(data) {
    const { profile, recommendations, total_matched } = data;

    // Profile summary
    document.getElementById("profileLevel").textContent =
        profile.experience_level.charAt(0).toUpperCase() + profile.experience_level.slice(1);
    document.getElementById("profileSkillCount").textContent = profile.skill_count;
    document.getElementById("profileDomains").textContent =
        profile.domains.length > 0 ? profile.domains.join(", ") : "General";

    // Profile skills tags
    const profileSkills = document.getElementById("profileSkills");
    profileSkills.innerHTML = "";
    if (profile.detected_skills && profile.detected_skills.length > 0) {
        profile.detected_skills.slice(0, 15).forEach((skill) => {
            const tag = document.createElement("span");
            tag.className = "keyword-tag";
            tag.textContent = skill;
            profileSkills.appendChild(tag);
        });
    }

    // Recommendations count
    document.getElementById("recommendationsCount").textContent =
        `Found ${total_matched} matching role${total_matched !== 1 ? "s" : ""} based on your profile`;

    // Job cards
    const grid = document.getElementById("jobCardsGrid");
    grid.innerHTML = "";

    if (recommendations.length === 0) {
        grid.innerHTML = `
            <div class="recommendations-empty">
                <p>No matching roles found for your profile. Try broadening your resume skills.</p>
            </div>
        `;
        return;
    }

    recommendations.forEach((job, index) => {
        const card = createJobCard(job, index);
        grid.appendChild(card);
    });
}

function createJobCard(job, index) {
    const card = document.createElement("div");
    card.className = "job-card";
    card.style.animationDelay = `${index * 0.05}s`;

    const tier = getMatchTier(job.match_score);

    card.innerHTML = `
        <div class="job-card-header">
            <div class="job-title-section">
                <h3 class="job-title">${escapeHtml(job.title)}</h3>
                <p class="job-company">${escapeHtml(job.company)} &middot; ${escapeHtml(job.company_type)}</p>
            </div>
            <div class="job-match-badge ${tier.className}">
                <span class="match-value">${Math.round(job.match_score)}%</span>
                <span class="match-label">match</span>
            </div>
        </div>
        <p class="job-description">${escapeHtml(job.description)}</p>
        <div class="job-meta">
            <span class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                </svg>
                ${escapeHtml(job.location)}
            </span>
            <span class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <line x1="12" y1="1" x2="12" y2="23"></line>
                    <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                </svg>
                ${escapeHtml(job.salary_range)}
            </span>
            <span class="job-meta-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="9" cy="7" r="4"></circle>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                ${escapeHtml(job.company_size)} employees
            </span>
        </div>
        <div class="job-skills-section">
            <div class="job-skills-group">
                <span class="skills-group-label matched-label">Your matching skills:</span>
                <div class="job-skills-tags">
                    ${job.matched_skills.map(s => `<span class="skill-tag matched">${escapeHtml(s)}</span>`).join("")}
                    ${job.matched_skills.length === 0 ? '<span class="skills-none">None detected</span>' : ""}
                </div>
            </div>
            ${job.missing_skills.length > 0 ? `
            <div class="job-skills-group">
                <span class="skills-group-label missing-label">Skills to develop:</span>
                <div class="job-skills-tags">
                    ${job.missing_skills.map(s => `<span class="skill-tag missing">${escapeHtml(s)}</span>`).join("")}
                </div>
            </div>
            ` : ""}
        </div>
        <p class="job-fit-reason">${escapeHtml(job.why_good_fit)}</p>
    `;

    return card;
}

function getMatchTier(score) {
    if (score >= 75) return { className: "excellent" };
    if (score >= 50) return { className: "good" };
    if (score >= 30) return { className: "moderate" };
    return { className: "low" };
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ===== Section Scores Display =====
function displaySectionScores(sectionScores) {
    const container = document.getElementById("sectionScoresContainer");
    const list = document.getElementById("sectionScoresList");
    if (!container || !list) return;

    list.innerHTML = "";

    const sections = [
        { key: "skills", label: "Skills", icon: "\u2699\uFE0F" },
        { key: "experience", label: "Experience", icon: "\uD83D\uDCBC" },
        { key: "projects", label: "Projects", icon: "\uD83D\uDEE0\uFE0F" },
        { key: "education", label: "Education", icon: "\uD83C\uDF93" },
    ];

    sections.forEach(({ key, label, icon }) => {
        const data = sectionScores[key];
        const isNA = !data || data.score === null || data.score === undefined;
        const score = isNA ? null : data.score;
        const tier = isNA ? "na" : getSectionTier(score);

        const item = document.createElement("div");
        item.className = `section-score-item ${tier}`;

        item.innerHTML = `
            <div class="section-score-header" onclick="toggleSectionDetail('${key}')">
                <div class="section-score-label">
                    <span class="section-icon">${icon}</span>
                    <span class="section-name">${label}</span>
                </div>
                <div class="section-score-value-row">
                    <span class="section-score-number">${isNA ? "N/A" : Math.round(score) + "%"}</span>
                    <div class="section-progress-bar">
                        <div class="section-progress-fill ${tier}" style="width: ${isNA ? 0 : score}%"></div>
                    </div>
                    <button class="section-expand-btn" aria-label="Toggle details">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                            <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="section-detail" id="sectionDetail-${key}" hidden>
                <p class="section-explanation">${escapeHtml(data ? data.explanation : "Section not found")}</p>
                ${data && data.matched_elements && data.matched_elements.length > 0 ? `
                <div class="section-elements matched">
                    <strong>Strong points:</strong>
                    <ul>${data.matched_elements.map(el => `<li>${escapeHtml(el)}</li>`).join("")}</ul>
                </div>` : ""}
                ${data && data.missing_elements && data.missing_elements.length > 0 ? `
                <div class="section-elements missing">
                    <strong>Missing from JD:</strong>
                    <ul>${data.missing_elements.map(el => `<li>${escapeHtml(el)}</li>`).join("")}</ul>
                </div>` : ""}
                ${data && data.weak_areas && data.weak_areas.length > 0 ? `
                <div class="section-elements weak">
                    <strong>Areas to improve:</strong>
                    <ul>${data.weak_areas.map(el => `<li>${escapeHtml(el)}</li>`).join("")}</ul>
                </div>` : ""}
            </div>
        `;

        list.appendChild(item);
    });

    container.hidden = false;
}

function getSectionTier(score) {
    if (score >= 80) return "excellent";
    if (score >= 60) return "good";
    if (score >= 40) return "moderate";
    return "low";
}

function toggleSectionDetail(key) {
    const detail = document.getElementById(`sectionDetail-${key}`);
    if (detail) {
        detail.hidden = !detail.hidden;
        const item = detail.closest(".section-score-item");
        if (item) item.classList.toggle("expanded", !detail.hidden);
    }
}

// ===== Role Selection =====
function setupRoleSelection() {
    const roleCards = document.querySelectorAll(".role-card");

    roleCards.forEach((card) => {
        card.addEventListener("click", () => {
            // Toggle selection
            const role = card.dataset.role;

            if (selectedRoleTemplate === role) {
                // Deselect
                card.classList.remove("selected");
                selectedRoleTemplate = null;
                enhanceBtn.disabled = true;
                enhanceBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                    </svg>
                    Select a Template to Enhance`;
            } else {
                // Select this card
                roleCards.forEach(c => c.classList.remove("selected"));
                card.classList.add("selected");
                selectedRoleTemplate = role;
                enhanceBtn.disabled = false;

                const templateName = card.querySelector("h4").textContent;
                enhanceBtn.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                    </svg>
                    Enhance with ${escapeHtml(templateName)} Template`;
            }
        });
    });
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
