// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    token: localStorage.getItem("token"),
    birthDetails: JSON.parse(localStorage.getItem("birthDetails") || "null"),
    chartData: null,
    activePeriod: "daily",
    customDate: null,      // "YYYY-MM-DD" or null (means today)
    predictions: {},       // "daily_career" or "daily_career_2026-04-15" -> text
};

// ---------------------------------------------------------------------------
// API Helper
// ---------------------------------------------------------------------------

async function api(endpoint, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

    const res = await fetch(`/api${endpoint}`, { ...options, headers });

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
// Helpers
// ---------------------------------------------------------------------------

function getBirthPayload() {
    return {
        date_of_birth: state.birthDetails.dob,
        time_of_birth: state.birthDetails.tob,
        place_of_birth: state.birthDetails.pob,
    };
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, "<br>");
}

function formatDate(isoStr) {
    const d = new Date(isoStr + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ---------------------------------------------------------------------------
// Auth UI
// ---------------------------------------------------------------------------

function toggleLogin() {
    document.getElementById("login-panel").classList.toggle("hidden");
}

function switchAuthTab(tab) {
    const loginTab = document.getElementById("auth-tab-login");
    const registerTab = document.getElementById("auth-tab-register");
    const loginForm = document.getElementById("form-login");
    const registerForm = document.getElementById("form-register");
    document.getElementById("auth-error").classList.add("hidden");

    if (tab === "login") {
        loginTab.classList.add("text-amber-400", "border-amber-400");
        loginTab.classList.remove("text-gray-400", "border-transparent");
        registerTab.classList.add("text-gray-400", "border-transparent");
        registerTab.classList.remove("text-amber-400", "border-amber-400");
        loginForm.classList.remove("hidden");
        registerForm.classList.add("hidden");
    } else {
        registerTab.classList.add("text-amber-400", "border-amber-400");
        registerTab.classList.remove("text-gray-400", "border-transparent");
        loginTab.classList.add("text-gray-400", "border-transparent");
        loginTab.classList.remove("text-amber-400", "border-amber-400");
        registerForm.classList.remove("hidden");
        loginForm.classList.add("hidden");
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const errorEl = document.getElementById("auth-error");
    errorEl.classList.add("hidden");

    try {
        const data = await api("/login", {
            method: "POST",
            body: JSON.stringify({
                email: document.getElementById("login-email").value,
                password: document.getElementById("login-password").value,
            }),
        });
        state.token = data.access_token;
        localStorage.setItem("token", data.access_token);
        if (data.user) {
            if (data.user.date_of_birth && data.user.time_of_birth && data.user.place_of_birth) {
                document.getElementById("dob").value = data.user.date_of_birth;
                document.getElementById("tob").value = data.user.time_of_birth;
                document.getElementById("pob").value = data.user.place_of_birth;
            }
            showLoggedIn(data.user.full_name);
        }
        document.getElementById("login-panel").classList.add("hidden");
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const errorEl = document.getElementById("auth-error");
    errorEl.classList.add("hidden");
    const full_name = document.getElementById("reg-name").value;

    try {
        const data = await api("/register", {
            method: "POST",
            body: JSON.stringify({
                email: document.getElementById("reg-email").value,
                password: document.getElementById("reg-password").value,
                full_name,
            }),
        });
        state.token = data.access_token;
        localStorage.setItem("token", data.access_token);
        showLoggedIn(full_name);
        document.getElementById("login-panel").classList.add("hidden");
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    }
}

function showLoggedIn(name) {
    document.getElementById("auth-area").classList.add("hidden");
    document.getElementById("user-area").classList.remove("hidden");
    document.getElementById("user-area").classList.add("flex");
    document.getElementById("user-name").textContent = name;
}

function logout() {
    state.token = null;
    localStorage.removeItem("token");
    document.getElementById("auth-area").classList.remove("hidden");
    document.getElementById("user-area").classList.add("hidden");
    document.getElementById("user-area").classList.remove("flex");
}

// ---------------------------------------------------------------------------
// Main: Get Reading (form submit)
// ---------------------------------------------------------------------------

async function getReading(e) {
    e.preventDefault();

    const dob = document.getElementById("dob").value;
    const tob = document.getElementById("tob").value;
    const pob = document.getElementById("pob").value;
    const btn = document.getElementById("get-reading-btn");
    const errorEl = document.getElementById("birth-error");
    errorEl.classList.add("hidden");

    if (!dob || !tob || !pob) {
        errorEl.textContent = "Please fill in all fields.";
        errorEl.classList.remove("hidden");
        return;
    }

    state.birthDetails = { dob, tob, pob };
    localStorage.setItem("birthDetails", JSON.stringify(state.birthDetails));
    state.predictions = {};
    state.chartData = null;
    state.customDate = null;

    btn.innerHTML = "&#9733; Calculating your chart...";
    btn.disabled = true;

    try {
        const chart = await api("/chart", {
            method: "POST",
            body: JSON.stringify(getBirthPayload()),
        });
        state.chartData = chart;

        displayChartSummary(chart);
        displayDashaTimeline(chart.dasha_timeline);

        // Show predictions section and set defaults
        document.getElementById("predictions-section").classList.remove("hidden");
        const now = new Date();
        document.getElementById("best-days-month").value = now.toISOString().slice(0, 7);
        document.getElementById("prediction-date").value = now.toISOString().slice(0, 10);

        // Hide custom date label (showing today by default)
        document.getElementById("prediction-date-label").classList.add("hidden");

        state.activePeriod = "daily";
        loadPredictions("daily");

        document.getElementById("chart-summary").scrollIntoView({ behavior: "smooth" });

    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    } finally {
        btn.innerHTML = "&#9733; Get My Reading";
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Display Chart Summary
// ---------------------------------------------------------------------------

function displayChartSummary(chart) {
    document.getElementById("chart-summary").classList.remove("hidden");

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
}

// ---------------------------------------------------------------------------
// Dasha Timeline
// ---------------------------------------------------------------------------

function displayDashaTimeline(timeline) {
    if (!timeline || !timeline.length) return;

    document.getElementById("dasha-section").classList.remove("hidden");
    const container = document.getElementById("dasha-timeline");

    const planetColors = {
        Sun: "amber", Moon: "blue", Mars: "red", Mercury: "green",
        Jupiter: "yellow", Venus: "pink", Saturn: "purple", Rahu: "gray", Ketu: "gray",
    };

    let html = "";
    for (const md of timeline) {
        const color = planetColors[md.lord] || "gray";
        const isCurrent = md.is_current;
        const border = isCurrent ? "border-amber-500/50 bg-amber-500/5" : "border-white/10";

        html += `<div class="border ${border} rounded-xl p-4 ${isCurrent ? '' : 'opacity-70'}">`;
        html += `<div class="flex items-center justify-between cursor-pointer" onclick="toggleDashaDetail(this)">`;
        html += `<div class="flex items-center gap-3">`;
        html += `<div class="w-8 h-8 rounded-full bg-${color}-500/20 flex items-center justify-center text-xs font-bold text-${color}-400">${md.lord.slice(0, 2)}</div>`;
        html += `<div>`;
        html += `<span class="font-semibold text-sm ${isCurrent ? 'text-amber-400' : 'text-white'}">${md.lord} Mahadasha</span>`;
        if (isCurrent) html += ` <span class="text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full ml-2">Current</span>`;
        html += `<div class="text-xs text-gray-400">${formatDate(md.start)} - ${formatDate(md.end)} (${md.duration_years} yrs)</div>`;
        html += `</div></div>`;
        html += `<span class="text-gray-500 text-xs dasha-arrow">&#9660;</span>`;
        html += `</div>`;

        // Antardasha details (collapsed by default, expanded for current)
        html += `<div class="dasha-detail ${isCurrent ? '' : 'hidden'} mt-3 pl-11 space-y-1">`;
        for (const ad of md.antardashas) {
            const adActive = ad.is_current;
            html += `<div class="flex items-center gap-2 text-xs ${adActive ? 'text-amber-400 font-medium' : 'text-gray-400'}">`;
            html += `<span class="w-1.5 h-1.5 rounded-full ${adActive ? 'bg-amber-400' : 'bg-gray-600'}"></span>`;
            html += `<span>${ad.lord}</span>`;
            html += `<span class="text-gray-500">${formatDate(ad.start)} - ${formatDate(ad.end)}</span>`;
            if (adActive) html += ` <span class="bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded text-[10px]">Active</span>`;
            html += `</div>`;
        }
        html += `</div></div>`;
    }

    container.innerHTML = html;
}

function toggleDashaDetail(el) {
    const detail = el.parentElement.querySelector(".dasha-detail");
    if (detail) detail.classList.toggle("hidden");
}

// ---------------------------------------------------------------------------
// Predictions Loading
// ---------------------------------------------------------------------------

function showLoading(category) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="loading-skeleton"></div>`;
}

function showPrediction(category, text) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="prediction-text">${escapeHtml(text)}</div>`;
}

function showPredictionError(category, msg) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="text-red-400 text-xs">${escapeHtml(msg)}</div>`;
}

async function loadPredictions(period, targetDate) {
    if (!state.birthDetails) return;
    state.activePeriod = period;
    const dateKey = targetDate || "";

    ["career", "health", "love"].forEach(showLoading);

    const categories = ["career", "health", "love"];
    const promises = categories.map(async (cat) => {
        const key = `${period}_${cat}_${dateKey}`;
        if (state.predictions[key]) {
            showPrediction(cat, state.predictions[key]);
            return;
        }
        try {
            const payload = {
                ...getBirthPayload(),
                prediction_type: period,
                category: cat,
            };
            if (targetDate) payload.target_date = targetDate;

            const data = await api("/predict", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            state.predictions[key] = data.prediction;
            showPrediction(cat, data.prediction);
        } catch (err) {
            showPredictionError(cat, err.message);
        }
    });

    await Promise.all(promises);
}

// ---------------------------------------------------------------------------
// Custom Date Predictions
// ---------------------------------------------------------------------------

function loadCustomDatePredictions() {
    const dateInput = document.getElementById("prediction-date").value;
    if (!dateInput) return;

    state.customDate = dateInput;

    // Show the date label
    const label = document.getElementById("prediction-date-label");
    label.classList.remove("hidden");
    document.getElementById("prediction-date-display").textContent = formatDate(dateInput);

    loadPredictions(state.activePeriod, dateInput);
}

// ---------------------------------------------------------------------------
// Period Tab Switching
// ---------------------------------------------------------------------------

function switchPeriod(period) {
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

    loadPredictions(period, state.customDate);
}

// ---------------------------------------------------------------------------
// Best Days
// ---------------------------------------------------------------------------

async function loadBestDays() {
    if (!state.birthDetails) return;

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
        const data = await api("/best-days", {
            method: "POST",
            body: JSON.stringify({ ...getBirthPayload(), category, month }),
        });

        const list = document.getElementById("best-days-list");
        const categoryColors = { career: "blue", health: "green", love: "pink" };
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

        document.getElementById("best-days-narrative").innerHTML = escapeHtml(data.narrative);
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
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    if (state.token) {
        api("/me").then(user => {
            showLoggedIn(user.full_name);
            if (user.date_of_birth && user.time_of_birth && user.place_of_birth) {
                document.getElementById("dob").value = user.date_of_birth;
                document.getElementById("tob").value = user.time_of_birth;
                document.getElementById("pob").value = user.place_of_birth;
            }
        }).catch(() => {
            state.token = null;
            localStorage.removeItem("token");
        });
    }

    if (state.birthDetails) {
        document.getElementById("dob").value = state.birthDetails.dob || "";
        document.getElementById("tob").value = state.birthDetails.tob || "";
        document.getElementById("pob").value = state.birthDetails.pob || "";
    }
});
