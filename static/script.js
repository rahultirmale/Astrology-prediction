// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    token: localStorage.getItem("token"),
    birthDetails: JSON.parse(localStorage.getItem("birthDetails") || "null"),
    chartData: null,
    activePeriod: "daily",
    predictions: {},   // "daily_career" -> text
};

// ---------------------------------------------------------------------------
// API Helper
// ---------------------------------------------------------------------------

async function api(endpoint, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

    const res = await fetch(`/api${endpoint}`, { ...options, headers });

    // Safely parse JSON — handle cases where server returns non-JSON
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
// Helper: get current birth details from form or state
// ---------------------------------------------------------------------------

function getBirthPayload() {
    return {
        date_of_birth: state.birthDetails.dob,
        time_of_birth: state.birthDetails.tob,
        place_of_birth: state.birthDetails.pob,
    };
}

// ---------------------------------------------------------------------------
// HTML Escape
// ---------------------------------------------------------------------------

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, "<br>");
}

// ---------------------------------------------------------------------------
// Auth UI: Toggle Login Panel
// ---------------------------------------------------------------------------

function toggleLogin() {
    const panel = document.getElementById("login-panel");
    panel.classList.toggle("hidden");
}

function switchAuthTab(tab) {
    const loginTab = document.getElementById("auth-tab-login");
    const registerTab = document.getElementById("auth-tab-register");
    const loginForm = document.getElementById("form-login");
    const registerForm = document.getElementById("form-register");
    const errorEl = document.getElementById("auth-error");
    errorEl.classList.add("hidden");

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

// ---------------------------------------------------------------------------
// Auth: Login
// ---------------------------------------------------------------------------

async function handleLogin(e) {
    e.preventDefault();
    const errorEl = document.getElementById("auth-error");
    errorEl.classList.add("hidden");

    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;

    try {
        const data = await api("/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
        });

        state.token = data.access_token;
        localStorage.setItem("token", data.access_token);

        // If the user has saved birth details, auto-fill the form
        if (data.user) {
            if (data.user.date_of_birth && data.user.time_of_birth && data.user.place_of_birth) {
                document.getElementById("dob").value = data.user.date_of_birth;
                document.getElementById("tob").value = data.user.time_of_birth;
                document.getElementById("pob").value = data.user.place_of_birth;
            }
            showLoggedIn(data.user.full_name);
        }

        // Close login panel
        document.getElementById("login-panel").classList.add("hidden");

    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    }
}

// ---------------------------------------------------------------------------
// Auth: Register
// ---------------------------------------------------------------------------

async function handleRegister(e) {
    e.preventDefault();
    const errorEl = document.getElementById("auth-error");
    errorEl.classList.add("hidden");

    const full_name = document.getElementById("reg-name").value;
    const email = document.getElementById("reg-email").value;
    const password = document.getElementById("reg-password").value;

    try {
        const data = await api("/register", {
            method: "POST",
            body: JSON.stringify({ email, password, full_name }),
        });

        state.token = data.access_token;
        localStorage.setItem("token", data.access_token);
        showLoggedIn(full_name);

        // Close login panel
        document.getElementById("login-panel").classList.add("hidden");

    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    }
}

// ---------------------------------------------------------------------------
// Auth: Show logged-in state / Logout
// ---------------------------------------------------------------------------

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

    // Save birth details to state and localStorage
    state.birthDetails = { dob, tob, pob };
    localStorage.setItem("birthDetails", JSON.stringify(state.birthDetails));

    // Clear any old predictions
    state.predictions = {};
    state.chartData = null;

    btn.innerHTML = "&#9733; Calculating your chart...";
    btn.disabled = true;

    try {
        // Fetch chart data
        const chart = await api("/chart", {
            method: "POST",
            body: JSON.stringify(getBirthPayload()),
        });
        state.chartData = chart;

        // Display chart summary
        displayChartSummary(chart);

        // Show predictions section and set default month
        document.getElementById("predictions-section").classList.remove("hidden");
        const now = new Date();
        document.getElementById("best-days-month").value = now.toISOString().slice(0, 7);

        // Load predictions for default period
        state.activePeriod = "daily";
        loadPredictions("daily");

        // Scroll to chart summary
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

async function loadPredictions(period) {
    if (!state.birthDetails) return;
    state.activePeriod = period;

    // Show loading for all 3 categories
    ["career", "health", "love"].forEach(showLoading);

    // Fetch all 3 in parallel via POST
    const categories = ["career", "health", "love"];
    const promises = categories.map(async (cat) => {
        const key = `${period}_${cat}`;
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
        const payload = {
            ...getBirthPayload(),
            category,
            month,
        };
        const data = await api("/best-days", {
            method: "POST",
            body: JSON.stringify(payload),
        });

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
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    // If user was logged in, try to restore session
    if (state.token) {
        api("/me").then(user => {
            showLoggedIn(user.full_name);
            // Auto-fill birth details from server if user has them
            if (user.date_of_birth && user.time_of_birth && user.place_of_birth) {
                document.getElementById("dob").value = user.date_of_birth;
                document.getElementById("tob").value = user.time_of_birth;
                document.getElementById("pob").value = user.place_of_birth;
            }
        }).catch(() => {
            // Token expired or invalid — just clear it silently
            state.token = null;
            localStorage.removeItem("token");
        });
    }

    // If there are saved birth details from last session, pre-fill form
    if (state.birthDetails) {
        document.getElementById("dob").value = state.birthDetails.dob || "";
        document.getElementById("tob").value = state.birthDetails.tob || "";
        document.getElementById("pob").value = state.birthDetails.pob || "";
    }
});
