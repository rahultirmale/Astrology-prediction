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
    isPaid: localStorage.getItem("isPaid") === "true",
    email: localStorage.getItem("paymentEmail") || "",
    subscriptionExpiry: localStorage.getItem("subscriptionExpiry") || null,
};

function updatePaymentState(paymentData) {
    if (paymentData && paymentData.paid) {
        state.isPaid = true;
        state.subscriptionExpiry = paymentData.expires_at;
        localStorage.setItem("isPaid", "true");
        if (paymentData.expires_at) {
            localStorage.setItem("subscriptionExpiry", paymentData.expires_at);
        }
    } else {
        state.isPaid = false;
        state.subscriptionExpiry = null;
        localStorage.removeItem("isPaid");
        localStorage.removeItem("subscriptionExpiry");
    }
}

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

    if (!res.ok) {
        const err = new Error(data.detail || `Request failed (${res.status})`);
        err.status = res.status;
        throw err;
    }
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
            if (data.user.email) {
                state.email = data.user.email;
                localStorage.setItem("paymentEmail", data.user.email);
            }
            if (data.user.date_of_birth && data.user.time_of_birth && data.user.place_of_birth) {
                document.getElementById("dob").value = data.user.date_of_birth;
                document.getElementById("tob").value = data.user.time_of_birth;
                document.getElementById("pob").value = data.user.place_of_birth;
            }
            showLoggedIn(data.user.full_name);
        }
        if (data.payment) {
            updatePaymentState(data.payment);
        }
        document.getElementById("login-panel").classList.add("hidden");
        updatePaywallUI();
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
    const regEmail = document.getElementById("reg-email").value;

    try {
        const data = await api("/register", {
            method: "POST",
            body: JSON.stringify({
                email: regEmail,
                password: document.getElementById("reg-password").value,
                full_name,
            }),
        });
        state.token = data.access_token;
        localStorage.setItem("token", data.access_token);
        state.email = regEmail;
        localStorage.setItem("paymentEmail", regEmail);
        if (data.payment) {
            updatePaymentState(data.payment);
        }
        showLoggedIn(full_name);
        document.getElementById("login-panel").classList.add("hidden");
        updatePaywallUI();
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
    state.isPaid = false;
    state.email = "";
    state.subscriptionExpiry = null;
    localStorage.removeItem("token");
    localStorage.removeItem("isPaid");
    localStorage.removeItem("paymentEmail");
    localStorage.removeItem("subscriptionExpiry");
    document.getElementById("auth-area").classList.remove("hidden");
    document.getElementById("user-area").classList.add("hidden");
    document.getElementById("user-area").classList.remove("flex");
    updatePaywallUI();
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

        // Display free content
        displayChartSummary(chart);
        displayPlanetPositions(chart);
        displayTransits(chart);
        displayHouseLords(chart);
        displayYogas(chart);
        displayDashaTimeline(chart.dasha_timeline);

        // Show compatibility section (form ready)
        document.getElementById("compatibility-section").classList.remove("hidden");

        // Show predictions wrapper and update paywall state
        document.getElementById("predictions-wrapper").classList.remove("hidden");
        const now = new Date();
        document.getElementById("best-days-month").value = now.toISOString().slice(0, 7);
        document.getElementById("prediction-date").value = now.toISOString().slice(0, 10);
        document.getElementById("prediction-date-label").classList.add("hidden");

        // Check payment state and update UI
        await checkAndUpdatePaywall();

        // Always load predictions (preview for free, full for paid)
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
// Display Planet Positions
// ---------------------------------------------------------------------------

function displayPlanetPositions(chart) {
    const planets = chart.natal_chart.planets;
    const tbody = document.getElementById("planets-table-body");

    const planetSymbols = {
        Sun: "\u2609", Moon: "\u263D", Mars: "\u2642", Mercury: "\u263F",
        Jupiter: "\u2643", Venus: "\u2640", Saturn: "\u2644", Rahu: "\u260A", Ketu: "\u260B",
    };

    let html = "";
    for (const [name, p] of Object.entries(planets)) {
        const symbol = planetSymbols[name] || "";
        const dignityClass = p.dignity === "exalted" ? "badge-exalted"
            : p.dignity === "own_sign" ? "badge-own"
            : p.dignity === "debilitated" ? "badge-debilitated"
            : "badge-neutral";
        const dignityLabel = p.dignity === "own_sign" ? "Own" : p.dignity.charAt(0).toUpperCase() + p.dignity.slice(1);
        const retroBadge = p.retrograde
            ? '<span class="badge badge-retro">R</span>'
            : '<span class="badge badge-direct">D</span>';

        html += `<tr>
            <td class="font-medium text-white">${symbol} ${name}</td>
            <td class="text-gray-300">${p.sign}</td>
            <td class="text-right text-gray-300">${p.degree.toFixed(2)}\u00B0</td>
            <td class="text-center text-gray-300">${p.house}</td>
            <td class="text-center">${retroBadge}</td>
            <td class="text-center"><span class="badge ${dignityClass}">${dignityLabel}</span></td>
        </tr>`;
    }

    tbody.innerHTML = html;
    document.getElementById("planets-section").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Display Transits
// ---------------------------------------------------------------------------

function displayTransits(chart) {
    const transits = chart.transits;
    if (!transits || !transits.length) return;

    const tbody = document.getElementById("transits-table-body");

    let html = "";
    for (const t of transits) {
        const effectClass = t.is_favorable ? "badge-favorable" : "badge-unfavorable";
        const effectLabel = t.is_favorable ? "Favorable" : "Unfavorable";
        const retroBadge = t.retrograde
            ? '<span class="badge badge-retro">R</span>'
            : '<span class="badge badge-direct">D</span>';

        html += `<tr>
            <td class="font-medium text-white">${t.planet}</td>
            <td class="text-gray-300">${t.transit_sign}</td>
            <td class="text-center text-gray-300">${t.house_from_moon}</td>
            <td class="text-center"><span class="badge ${effectClass}">${effectLabel}</span></td>
            <td class="text-center">${retroBadge}</td>
        </tr>`;
    }

    tbody.innerHTML = html;
    document.getElementById("transits-section").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Display House Lords
// ---------------------------------------------------------------------------

function displayHouseLords(chart) {
    const houseSigns = chart.natal_chart.house_signs;
    const houseLords = chart.natal_chart.house_lords;
    if (!houseSigns || !houseLords) return;

    const grid = document.getElementById("houses-grid");
    const houseNames = [
        "1st - Self", "2nd - Wealth", "3rd - Siblings", "4th - Home",
        "5th - Children", "6th - Enemies", "7th - Marriage", "8th - Longevity",
        "9th - Fortune", "10th - Career", "11th - Gains", "12th - Loss",
    ];

    let html = "";
    for (let i = 0; i < 12; i++) {
        const sign = houseSigns[i];
        const lord = houseLords[String(i + 1)] || houseLords[i + 1] || "—";
        const label = houseNames[i] || `House ${i + 1}`;
        html += `<div class="house-card">
            <div class="text-xs text-gray-500 mb-1">${label}</div>
            <div class="text-sm font-semibold text-white">${sign}</div>
            <div class="text-xs text-amber-400 mt-1">${lord}</div>
        </div>`;
    }

    grid.innerHTML = html;
    document.getElementById("houses-section").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Display Yogas
// ---------------------------------------------------------------------------

function displayYogas(chart) {
    const yogas = chart.yogas;
    const container = document.getElementById("yogas-container");
    const noYogas = document.getElementById("no-yogas");

    if (!yogas || yogas.length === 0) {
        container.innerHTML = "";
        noYogas.classList.remove("hidden");
    } else {
        noYogas.classList.add("hidden");

        const typeColors = {
            "Pancha Mahapurusha": "purple",
            "Gajakesari": "yellow",
            "Budhaditya": "green",
            "Chandra-Mangal": "red",
            "Amala": "blue",
        };

        let html = '<div class="grid grid-cols-1 md:grid-cols-2 gap-4">';
        for (const y of yogas) {
            const color = typeColors[y.type] || "amber";
            html += `<div class="yoga-card">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-${color}-400 text-lg font-bold">\u2726</span>
                    <span class="font-semibold text-white">${escapeHtml(y.name)}</span>
                </div>
                <p class="text-gray-400 text-xs leading-relaxed">${escapeHtml(y.description)}</p>
                <div class="mt-2 text-xs text-gray-500">
                    Formed by: <span class="text-gray-300">${escapeHtml(y.formed_by)}</span>
                </div>
            </div>`;
        }
        html += "</div>";
        container.innerHTML = html;
    }

    document.getElementById("yogas-section").classList.remove("hidden");
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
// Collapsible Section Toggle
// ---------------------------------------------------------------------------

function toggleSection(id) {
    const body = document.getElementById(`${id}-body`);
    const arrow = body.parentElement.querySelector('.section-arrow');
    body.classList.toggle('hidden');
    if (arrow) arrow.classList.toggle('rotate-180');
}

// ---------------------------------------------------------------------------
// Love Compatibility
// ---------------------------------------------------------------------------

function switchCompatTab(tab) {
    const gunmilanTab = document.getElementById("compat-tab-gunmilan");
    const partnerTab = document.getElementById("compat-tab-partner");
    const gunmilanPanel = document.getElementById("compat-gunmilan-panel");
    const partnerPanel = document.getElementById("compat-partner-panel");

    if (tab === "gunmilan") {
        gunmilanTab.classList.remove("text-gray-400", "border-white/10");
        gunmilanTab.classList.add("bg-pink-500/20", "text-pink-400", "border-pink-500/30");
        partnerTab.classList.remove("bg-pink-500/20", "text-pink-400", "border-pink-500/30");
        partnerTab.classList.add("text-gray-400", "border-white/10");
        gunmilanPanel.classList.remove("hidden");
        partnerPanel.classList.add("hidden");
    } else {
        partnerTab.classList.remove("text-gray-400", "border-white/10");
        partnerTab.classList.add("bg-pink-500/20", "text-pink-400", "border-pink-500/30");
        gunmilanTab.classList.remove("bg-pink-500/20", "text-pink-400", "border-pink-500/30");
        gunmilanTab.classList.add("text-gray-400", "border-white/10");
        partnerPanel.classList.remove("hidden");
        gunmilanPanel.classList.add("hidden");
    }
}

async function calculateCompatibility() {
    if (!state.birthDetails) return;

    const partnerDob = document.getElementById("partner-dob").value;
    const partnerTob = document.getElementById("partner-tob").value;
    const partnerPob = document.getElementById("partner-pob").value;
    const btn = document.getElementById("compat-btn");
    const errorEl = document.getElementById("compat-error");
    errorEl.classList.add("hidden");

    if (!partnerDob || !partnerTob || !partnerPob) {
        errorEl.textContent = "Please fill in all partner birth details.";
        errorEl.classList.remove("hidden");
        return;
    }

    btn.disabled = true;
    btn.textContent = "Calculating...";
    document.getElementById("compat-results").classList.add("hidden");
    document.getElementById("compat-loading").classList.remove("hidden");

    try {
        const data = await api("/compatibility", {
            method: "POST",
            body: JSON.stringify({
                ...getBirthPayload(),
                partner_date_of_birth: partnerDob,
                partner_time_of_birth: partnerTob,
                partner_place_of_birth: partnerPob,
                email: state.email,
            }),
        });

        displayGunMilanResults(data);

    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
    } finally {
        btn.disabled = false;
        btn.innerHTML = "&#128149; Check Compatibility";
        document.getElementById("compat-loading").classList.add("hidden");
    }
}

function displayGunMilanResults(data) {
    const gm = data.gun_milan;

    // Score circle
    document.getElementById("compat-score-value").textContent = gm.total_score;
    document.getElementById("compat-verdict").textContent = gm.verdict;

    // Person info
    document.getElementById("compat-boy-info").textContent =
        `${gm.boy_rashi} (${gm.boy_nakshatra})`;
    document.getElementById("compat-girl-info").textContent =
        `${gm.girl_rashi} (${gm.girl_nakshatra})`;

    // Color the score based on value
    const circle = document.getElementById("compat-score-circle");
    if (gm.total_score >= 28) {
        circle.style.borderColor = "rgba(16, 185, 129, 0.5)";
    } else if (gm.total_score >= 21) {
        circle.style.borderColor = "rgba(245, 158, 11, 0.5)";
    } else if (gm.total_score >= 18) {
        circle.style.borderColor = "rgba(251, 146, 60, 0.5)";
    } else {
        circle.style.borderColor = "rgba(239, 68, 68, 0.5)";
    }

    // Nadi Dosha warning
    if (gm.nadi_dosha) {
        document.getElementById("compat-nadi-warning").classList.remove("hidden");
    } else {
        document.getElementById("compat-nadi-warning").classList.add("hidden");
    }

    // Kuta score cards
    const grid = document.getElementById("compat-kutas-grid");
    grid.innerHTML = gm.kutas.map(k => {
        const pct = (k.score / k.max) * 100;
        const barColor = pct >= 75 ? "#34d399" : pct >= 50 ? "#fbbf24" : pct > 0 ? "#fb923c" : "#f87171";
        return `<div class="kuta-card">
            <div class="text-xs text-gray-400 mb-1">${k.name}</div>
            <div class="flex items-baseline gap-1">
                <span class="text-lg font-bold text-white">${k.score}</span>
                <span class="text-xs text-gray-500">/ ${k.max}</span>
            </div>
            <div class="kuta-bar mt-1">
                <div class="kuta-bar-fill" style="width: ${pct}%; background: ${barColor}"></div>
            </div>
            <div class="text-[10px] text-gray-500 mt-1">${k.description}</div>
        </div>`;
    }).join("");

    // AI Interpretation
    const aiSection = document.getElementById("compat-ai-section");
    const aiText = document.getElementById("compat-ai-text");
    if (data.ai_interpretation) {
        aiText.innerHTML = escapeHtml(data.ai_interpretation);
        aiSection.classList.remove("hidden");
    } else if (data.preview) {
        aiText.innerHTML = `<div class="prediction-preview">
            <div class="text-gray-500 text-xs mb-2">AI interpretation available with full access</div>
            <span class="text-amber-400 text-xs font-semibold cursor-pointer hover:text-amber-300 transition-colors" onclick="initPayment()">&#128274; Unlock AI interpretation &rarr;</span>
        </div>`;
        aiSection.classList.remove("hidden");
    }

    document.getElementById("compat-results").classList.remove("hidden");
}

async function loadPartnerPrediction() {
    if (!state.birthDetails) return;

    if (!state.isPaid) {
        document.getElementById("partner-pred-lock").classList.remove("hidden");
        return;
    }

    const gender = document.getElementById("partner-pred-gender").value;
    const btn = document.getElementById("partner-pred-btn");
    const errorEl = document.getElementById("partner-pred-error");
    errorEl.classList.add("hidden");

    btn.disabled = true;
    btn.textContent = "Analyzing...";
    document.getElementById("partner-pred-results").classList.add("hidden");
    document.getElementById("partner-pred-loading").classList.remove("hidden");

    try {
        const data = await api("/partner-prediction", {
            method: "POST",
            body: JSON.stringify({
                ...getBirthPayload(),
                gender: gender,
                email: state.email,
            }),
        });

        document.getElementById("partner-dk-planet").textContent =
            `${data.darakaraka.planet} in ${data.darakaraka.sign}`;
        document.getElementById("partner-7th-lord").textContent =
            data.seventh_house_lord || "--";
        document.getElementById("partner-pred-text").innerHTML =
            escapeHtml(data.prediction);

        document.getElementById("partner-pred-loading").classList.add("hidden");
        document.getElementById("partner-pred-results").classList.remove("hidden");

    } catch (err) {
        if (err.status === 402) {
            state.isPaid = false;
            localStorage.removeItem("isPaid");
            updatePaywallUI();
        }
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
        document.getElementById("partner-pred-loading").classList.add("hidden");
    } finally {
        btn.disabled = false;
        btn.innerHTML = "&#128302; Predict My Partner";
    }
}

// ---------------------------------------------------------------------------
// Payment / Paywall
// ---------------------------------------------------------------------------

async function checkAndUpdatePaywall() {
    // Verify payment status with server (requires login)
    if (state.token) {
        try {
            const data = await api("/check-payment");
            updatePaymentState(data);
        } catch {
            // If check fails, trust localStorage
        }
    }
    updatePaywallUI();
}

function updatePaywallUI() {
    const unlockBanner = document.getElementById("unlock-banner");
    const bestDaysLock = document.getElementById("best-days-lock-overlay");
    const partnerPredLock = document.getElementById("partner-pred-lock");
    const subsInfo = document.getElementById("subscription-info");

    if (state.isPaid) {
        unlockBanner.classList.add("hidden");
        bestDaysLock.classList.add("hidden");
        if (partnerPredLock) partnerPredLock.classList.add("hidden");

        // Show subscription info
        if (subsInfo && state.subscriptionExpiry) {
            const expDate = new Date(state.subscriptionExpiry);
            const formatted = expDate.toLocaleDateString("en-US", {
                month: "long", day: "numeric", year: "numeric"
            });
            subsInfo.innerHTML = `<div class="text-center py-3 px-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                <span class="text-green-400 text-sm font-medium">&#10003; Premium Active</span>
                <span class="text-gray-400 text-xs ml-2">until ${formatted}</span>
            </div>`;
            subsInfo.classList.remove("hidden");
        } else if (subsInfo) {
            subsInfo.innerHTML = `<div class="text-center py-3 px-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                <span class="text-green-400 text-sm font-medium">&#10003; Premium Active</span>
            </div>`;
            subsInfo.classList.remove("hidden");
        }
    } else {
        unlockBanner.classList.remove("hidden");
        bestDaysLock.classList.remove("hidden");
        if (partnerPredLock) partnerPredLock.classList.remove("hidden");
        if (subsInfo) subsInfo.classList.add("hidden");

        // Show logged-in user's email in payment banner
        if (state.token && state.email) {
            const emailDisplay = document.getElementById("payment-email-display");
            const emailSpan = document.getElementById("payment-user-email");
            if (emailDisplay && emailSpan) {
                emailSpan.textContent = state.email;
                emailDisplay.classList.remove("hidden");
            }
        }
    }
}

async function initPayment() {
    // Require login before payment
    if (!state.token) {
        document.getElementById("login-panel").classList.remove("hidden");
        const authErr = document.getElementById("auth-error");
        authErr.textContent = "Please login or create an account first to proceed with payment.";
        authErr.classList.remove("hidden");
        document.getElementById("login-panel").scrollIntoView({ behavior: "smooth" });
        return;
    }

    const email = state.email;
    const errorEl = document.getElementById("payment-error");
    const btn = document.getElementById("pay-btn");
    errorEl.classList.add("hidden");

    if (!email || !email.includes("@")) {
        errorEl.textContent = "Could not determine your email. Please log out and log in again.";
        errorEl.classList.remove("hidden");
        return;
    }

    btn.disabled = true;
    btn.textContent = "Creating order...";

    try {
        const data = await api("/create-order", {
            method: "POST",
            body: JSON.stringify({}),
        });

        // If already paid, unlock immediately
        if (data.already_paid) {
            state.isPaid = true;
            state.subscriptionExpiry = data.expires_at;
            localStorage.setItem("isPaid", "true");
            if (data.expires_at) localStorage.setItem("subscriptionExpiry", data.expires_at);
            state.predictions = {};
            updatePaywallUI();
            loadPredictions(state.activePeriod);
            return;
        }

        // Open Razorpay checkout
        const options = {
            key: data.key_id,
            amount: data.amount,
            currency: data.currency,
            name: "Jyotish AI",
            description: "1-Year AI Vedic Astrology Subscription",
            order_id: data.order_id,
            prefill: { email: email },
            theme: { color: "#f59e0b" },
            handler: function (response) {
                verifyPayment(email, response);
            },
            modal: {
                ondismiss: function () {
                    btn.disabled = false;
                    btn.innerHTML = "Unlock Full Reading &mdash; &#8377;19/year";
                },
            },
        };

        const rzp = new Razorpay(options);
        rzp.open();
    } catch (err) {
        if (err.status === 401) {
            document.getElementById("login-panel").classList.remove("hidden");
            const authErr = document.getElementById("auth-error");
            authErr.textContent = "Your session expired. Please login again.";
            authErr.classList.remove("hidden");
        } else {
            errorEl.textContent = err.message;
            errorEl.classList.remove("hidden");
        }
        btn.disabled = false;
        btn.innerHTML = "Unlock Full Reading &mdash; &#8377;19/year";
    }
}

async function verifyPayment(email, response) {
    const errorEl = document.getElementById("payment-error");
    const btn = document.getElementById("pay-btn");
    btn.textContent = "Verifying payment...";

    try {
        const data = await api("/verify-payment", {
            method: "POST",
            body: JSON.stringify({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
            }),
        });

        // Success — unlock
        state.isPaid = true;
        state.email = email;
        state.subscriptionExpiry = data.expires_at;
        localStorage.setItem("isPaid", "true");
        localStorage.setItem("paymentEmail", email);
        if (data.expires_at) localStorage.setItem("subscriptionExpiry", data.expires_at);
        state.predictions = {};
        updatePaywallUI();

        // Reload predictions with full content
        loadPredictions(state.activePeriod);
    } catch (err) {
        errorEl.textContent = "Payment verification failed: " + err.message;
        errorEl.classList.remove("hidden");
        btn.disabled = false;
        btn.innerHTML = "Unlock Full Reading &mdash; &#8377;19/year";
    }
}

// ---------------------------------------------------------------------------
// Predictions Loading
// ---------------------------------------------------------------------------

function showLoading(category) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="loading-skeleton"></div>`;
}

function showPrediction(category, text, isPreview = false) {
    const container = document.getElementById(`pred-${category}`);
    if (isPreview) {
        container.innerHTML =
            `<div class="prediction-text prediction-preview">
                <div class="preview-text-fade">${escapeHtml(text)}</div>
                <div class="preview-cta" onclick="initPayment()">
                    <span class="text-amber-400 text-xs font-semibold cursor-pointer hover:text-amber-300 transition-colors">&#128274; Unlock full reading &rarr;</span>
                </div>
            </div>`;
    } else {
        container.innerHTML =
            `<div class="prediction-text">${escapeHtml(text)}</div>`;
    }
}

function showPredictionError(category, msg) {
    document.getElementById(`pred-${category}`).innerHTML =
        `<div class="text-red-400 text-xs">${escapeHtml(msg)}</div>`;
}

async function loadPredictions(period, targetDate) {
    if (!state.birthDetails) return;
    state.activePeriod = period;
    const dateKey = targetDate || "";
    const paidKey = state.isPaid ? "full" : "preview";

    ["career", "health", "love"].forEach(showLoading);

    const categories = ["career", "health", "love"];
    const promises = categories.map(async (cat) => {
        const key = `${period}_${cat}_${dateKey}_${paidKey}`;
        if (state.predictions[key]) {
            showPrediction(cat, state.predictions[key].text, state.predictions[key].preview);
            return;
        }
        try {
            const payload = {
                ...getBirthPayload(),
                prediction_type: period,
                category: cat,
                email: state.email,
            };
            if (targetDate) payload.target_date = targetDate;

            const data = await api("/predict", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            state.predictions[key] = { text: data.prediction, preview: data.preview };
            showPrediction(cat, data.prediction, data.preview);
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
    if (!state.birthDetails || !state.isPaid) return;

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
            body: JSON.stringify({ ...getBirthPayload(), category, month, email: state.email }),
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
        if (err.status === 402) {
            state.isPaid = false;
            localStorage.removeItem("isPaid");
            updatePaywallUI();
        }
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
            if (user.email) {
                state.email = user.email;
                localStorage.setItem("paymentEmail", user.email);
            }
            if (user.payment) {
                updatePaymentState(user.payment);
                updatePaywallUI();
            }
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
