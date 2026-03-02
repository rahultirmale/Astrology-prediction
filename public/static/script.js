// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    token: localStorage.getItem("token"),
    user: null,
    chartData: null,
    activePeriod: "daily",
    predictions: {},   // "daily_career" -> text
};

// ---------------------------------------------------------------------------
// API Helper
// ---------------------------------------------------------------------------

async function api(endpoint, options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

    const res = await fetch(`/api${endpoint}`, { ...options, headers });
    if (res.status === 401) {
        logout();
        throw new Error("Session expired");
    }

    // Safely parse JSON — handle cases where server returns non-JSON (HTML error pages)
    let data;
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
        data = await res.json();
    } else {
        const text = await res.text();
        if (!res.ok) throw new Error(text.slice(0, 150) || `Server error (${res.status})`);
        try {
            data = JSON.parse(text);
        } catch {
            throw new Error(`Unexpected response from server (${res.status})`);
        }
    }

    if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
    return data;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

function logout() {
    localStorage.removeItem("token");
    window.location.href = "/";
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

async function init() {
    if (!state.token) {
        window.location.href = "/";
        return;
    }

    try {
        state.user = await api("/me");
        document.getElementById("user-name").textContent = state.user.full_name;
        document.getElementById("page-loading").classList.add("hidden");

        if (state.user.has_birth_details) {
            showPredictions();
        } else {
            showBirthForm();
        }
    } catch (err) {
        // Token invalid
        logout();
    }
}

// ---------------------------------------------------------------------------
// Birth Details
// ---------------------------------------------------------------------------

function showBirthForm() {
    document.getElementById("birth-section").classList.remove("hidden");
    document.getElementById("chart-summary").classList.add("hidden");
    document.getElementById("predictions-section").classList.add("hidden");

    // Pre-fill if user has existing data
    if (state.user && state.user.has_birth_details) {
        document.getElementById("dob").value = state.user.date_of_birth;
        document.getElementById("tob").value = state.user.time_of_birth;
        document.getElementById("pob").value = state.user.place_of_birth;
    }
}

async function saveBirthDetails(e) {
    e.preventDefault();
    const btn = document.getElementById("save-birth-btn");
    const errorEl = document.getElementById("birth-error");
    errorEl.classList.add("hidden");
    btn.textContent = "Calculating chart...";
    btn.disabled = true;

    try {
        await api("/birth-details", {
            method: "PUT",
            body: JSON.stringify({
                date_of_birth: document.getElementById("dob").value,
                time_of_birth: document.getElementById("tob").value,
                place_of_birth: document.getElementById("pob").value,
            }),
        });

        // Refresh user data
        state.user = await api("/me");
        state.predictions = {};  // Clear cached predictions
        showPredictions();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    } finally {
        btn.textContent = "Calculate My Chart";
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Chart Summary & Predictions
// ---------------------------------------------------------------------------

async function showPredictions() {
    document.getElementById("birth-section").classList.add("hidden");
    document.getElementById("chart-summary").classList.remove("hidden");
    document.getElementById("predictions-section").classList.remove("hidden");

    // Set default month for best-days picker
    const now = new Date();
    const monthStr = now.toISOString().slice(0, 7);
    document.getElementById("best-days-month").value = monthStr;

    // Load chart summary
    loadChartSummary();

    // Load predictions for current period
    loadPredictions(state.activePeriod);
}

async function loadChartSummary() {
    try {
        state.chartData = await api("/chart-summary");
        const chart = state.chartData;

        document.getElementById("summary-asc").textContent =
            `${chart.natal_chart.ascendant.sign} ${chart.natal_chart.ascendant.degree.toFixed(1)}\u00B0`;
        document.getElementById("summary-moon").textContent =
            chart.natal_chart.planets.Moon.sign;
        document.getElementById("summary-nak").textContent =
            chart.natal_chart.moon_nakshatra.name;
        document.getElementById("summary-dasha").textContent =
            `${chart.dasha.mahadasha_lord}-${chart.dasha.antardasha_lord}`;

        if (chart.sade_sati) {
            document.getElementById("sade-sati-banner").classList.remove("hidden");
            document.getElementById("sade-sati-text").textContent = chart.sade_sati;
        } else {
            document.getElementById("sade-sati-banner").classList.add("hidden");
        }
    } catch (err) {
        console.error("Failed to load chart:", err);
    }
}

// ---------------------------------------------------------------------------
// Predictions Loading
// ---------------------------------------------------------------------------

function showLoading(category) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="loading-skeleton"></div>`;
}

function showPrediction(category, text) {
    const el = document.getElementById(`pred-${category}`);
    el.innerHTML = `<div class="prediction-text">${escapeHtml(text)}</div>`;
}

function showPredictionError(category, msg) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="text-red-400 text-xs">${escapeHtml(msg)}</div>`;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    // Preserve line breaks
    return div.innerHTML.replace(/\n/g, "<br>");
}

async function loadPredictions(period) {
    state.activePeriod = period;

    // Show loading for all 3 categories
    ["career", "health", "love"].forEach(showLoading);

    // Fetch all 3 in parallel
    const categories = ["career", "health", "love"];
    const promises = categories.map(async (cat) => {
        const key = `${period}_${cat}`;
        if (state.predictions[key]) {
            showPrediction(cat, state.predictions[key]);
            return;
        }
        try {
            const data = await api(`/predictions?type=${period}&category=${cat}`);
            state.predictions[key] = data.prediction;
            showPrediction(cat, data.prediction);
        } catch (err) {
            showPredictionError(cat, err.message);
        }
    });

    await Promise.all(promises);
}

// ---------------------------------------------------------------------------
// Period Tab Switching
// ---------------------------------------------------------------------------

function switchPeriod(period) {
    // Update tab styles
    document.querySelectorAll(".period-tab").forEach((tab) => {
        tab.className = tab.className
            .replace("bg-amber-500/20", "")
            .replace("text-amber-400", "text-gray-400")
            .replace("border-amber-500/30", "border-white/10")
            .trim();
        tab.classList.add("hover:text-white", "hover:bg-white/5");
    });

    const activeTab = document.getElementById(`period-${period}`);
    activeTab.classList.remove("text-gray-400", "hover:text-white", "hover:bg-white/5", "border-white/10");
    activeTab.classList.add("bg-amber-500/20", "text-amber-400", "border-amber-500/30");

    loadPredictions(period);
}

// ---------------------------------------------------------------------------
// Best Days
// ---------------------------------------------------------------------------

async function loadBestDays() {
    const month = document.getElementById("best-days-month").value;
    const category = document.getElementById("best-days-category").value;
    const btn = document.getElementById("best-days-btn");
    const loading = document.getElementById("best-days-loading");
    const results = document.getElementById("best-days-results");

    if (!month) return;

    btn.disabled = true;
    btn.textContent = "Analyzing...";
    loading.classList.remove("hidden");
    results.classList.add("hidden");

    try {
        const data = await api(`/best-days?month=${month}&category=${category}`);

        // Render best days list
        const list = document.getElementById("best-days-list");
        const categoryColors = {
            career: "blue",
            health: "green",
            love: "pink",
        };
        const color = categoryColors[category] || "amber";

        list.innerHTML = data.best_days
            .map((d, i) => {
                const dateObj = new Date(d.date + "T00:00:00");
                const dayName = dateObj.toLocaleDateString("en-US", { weekday: "short" });
                const dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                const barWidth = Math.max(20, (d.score / 12) * 100);
                return `
                <div class="flex items-center gap-4 bg-white/5 rounded-lg p-3">
                    <div class="text-center min-w-[60px]">
                        <div class="text-xs text-gray-400">${dayName}</div>
                        <div class="font-semibold text-white">${dateStr}</div>
                    </div>
                    <div class="flex-1">
                        <div class="flex items-center gap-2 mb-1">
                            <div class="score-bar" style="width: ${barWidth}%"></div>
                            <span class="text-xs text-${color}-400 font-medium">${d.score}</span>
                        </div>
                        <div class="text-xs text-gray-400">${escapeHtml(d.key_transits)}</div>
                    </div>
                    <div class="text-lg font-bold text-${color}-400/50">#${i + 1}</div>
                </div>`;
            })
            .join("");

        // Render narrative
        document.getElementById("best-days-narrative").innerHTML =
            escapeHtml(data.narrative);

        loading.classList.add("hidden");
        results.classList.remove("hidden");
    } catch (err) {
        loading.classList.add("hidden");
        results.classList.remove("hidden");
        document.getElementById("best-days-list").innerHTML =
            `<div class="text-red-400 text-sm">${escapeHtml(err.message)}</div>`;
        document.getElementById("best-days-narrative").innerHTML = "";
    } finally {
        btn.disabled = false;
        btn.textContent = "Find Best Days";
    }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", init);
