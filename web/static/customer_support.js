(function () {
  const els = {
    transcript: document.getElementById("transcript"),
    input: document.getElementById("composerInput"),
    sendBtn: document.getElementById("sendBtn"),
    modeTextBtn: document.getElementById("modeTextBtn"),
    modeVoiceBtn: document.getElementById("modeVoiceBtn"),
    voiceBar: document.getElementById("voiceBar"),
    voiceInputBtn: document.getElementById("voiceInputBtn"),
    voiceHint: document.getElementById("voiceHint"),
    voiceBackendHint: document.getElementById("voiceBackendHint"),
    statusLine: document.getElementById("statusLine"),
    quickActions: document.getElementById("quickActions"),
    capabilityList: document.getElementById("capabilityList"),
    commitmentList: document.getElementById("commitmentList"),
    officialChannels: document.getElementById("officialChannels"),
    brandName: document.getElementById("brandName"),
    brandSub: document.getElementById("brandSub"),
    topLinkPrimary: document.getElementById("topLinkPrimary"),
    topLinkSecondary: document.getElementById("topLinkSecondary"),
    heroTitle: document.getElementById("heroTitle"),
    heroSubtitle: document.getElementById("heroSubtitle"),
    resourcePanelTitle: document.getElementById("resourcePanelTitle"),
    continuePhoneBtn: document.getElementById("continuePhoneBtn"),
    continueSmsBtn: document.getElementById("continueSmsBtn"),
    sendSummaryBtn: document.getElementById("sendSummaryBtn"),
    resetSessionBtn: document.getElementById("resetSessionBtn"),
    uploadBtn: document.getElementById("uploadBtn"),
    uploadInput: document.getElementById("uploadInput"),
    technicalToggle: document.getElementById("technicalToggle"),
    technicalBody: document.getElementById("technicalBody"),
    technicalPre: document.getElementById("technicalPre"),
    planToggle: document.getElementById("planToggle"),
    planEmpty: document.getElementById("planEmpty"),
    planBodyWrap: document.getElementById("planBodyWrap"),
    planBody: document.getElementById("planBody"),
    planIntent: document.getElementById("planIntent"),
    planStage: document.getElementById("planStage"),
    planCanDo: document.getElementById("planCanDo"),
    planNeed: document.getElementById("planNeed"),
    planContext: document.getElementById("planContext"),
    resourcesToggle: document.getElementById("resourcesToggle"),
    resourcesBody: document.getElementById("resourcesBody"),
    alertsToggle: document.getElementById("alertsToggle"),
    alertsBody: document.getElementById("alertsBody"),
    alertsList: document.getElementById("alertsList"),
    resolutionToggle: document.getElementById("resolutionToggle"),
    resolutionBody: document.getElementById("resolutionBody"),
    resolutionList: document.getElementById("resolutionList"),
    capabilitiesToggle: document.getElementById("capabilitiesToggle"),
    capabilitiesBody: document.getElementById("capabilitiesBody"),
    trackerToggle: document.getElementById("trackerToggle"),
    trackerBody: document.getElementById("trackerBody"),
    trackerList: document.getElementById("trackerList"),
    trackerRefreshBtn: document.getElementById("trackerRefreshBtn"),
  };

  const state = {
    mode: "text",
    tenant: detectTenantFromPath(),
    sessionId: null,
    customerId: "cust-web-demo",
    sending: false,
    listening: false,
    mediaRecorder: null,
    mediaStream: null,
    mediaChunks: [],
    mediaMime: "",
    recognition: null,
    synthEnabled: "speechSynthesis" in window,
    currentAudio: null,
    ttsAbort: null,
    typingIndicator: null,
    lastCapabilities: null,
    lastHealth: null,
    lastResponse: null,
    lastAlerts: [],
    trackerData: null,
    voiceRetries: 0,
    pendingTranscript: null,
    voiceBackend: { stt: "unknown", tts: "browser" },
    brand: { name: "Support", callCenterPhone: null },
  };

  const nextActionPrompts = {
    provide_booking_reference: "My booking reference is AB12CD.",
    verify_booking_reference: "Please check booking reference AB12CD.",
    provide_flight_number_or_booking_reference: "My flight number is F81234.",
    rebooking_options: "Please show rebooking options.",
    compensation_check: "Please check APPR compensation eligibility.",
    confirm_rebooking_option: "I choose option 1.",
    submit_refund: "Submit refund now.",
    choose_travel_credit: "I want travel credit instead.",
    continue_current_request: "Continue with this request.",
    switch_to_new_request: "I want to start a different request.",
    urgent_human_help_if_needed: "I need urgent human support now.",
    human_agent_if_urgent: "I need a human agent.",
    check_rebooking_options: "Check rebooking options now.",
    contact_bank_if_fraud: "I contacted my bank. What should I do next?",
    share_booking_or_transaction_details: "The booking reference is AB12CD.",
  };

  function detectTenantFromPath() {
    const parts = (window.location.pathname || "/").split("/").filter(Boolean);
    if (parts.length >= 2 && parts[0] === "support") return parts[1].toLowerCase();
    return "flair";
  }

  function newSessionId() {
    return "sess-" + Math.random().toString(36).slice(2, 10);
  }

  state.sessionId = newSessionId();

  function setStatus(text) {
    els.statusLine.textContent = text || "Connected.";
  }

  function setMode(mode) {
    state.mode = mode === "voice" ? "voice" : "text";
    const isVoice = state.mode === "voice";
    els.modeTextBtn.classList.toggle("active", !isVoice);
    els.modeVoiceBtn.classList.toggle("active", isVoice);
    els.modeTextBtn.setAttribute("aria-selected", String(!isVoice));
    els.modeVoiceBtn.setAttribute("aria-selected", String(isVoice));
    els.voiceBar.classList.toggle("hidden", !isVoice);
    setStatus(isVoice ? "Voice mode." : "Text mode.");
    if (!isVoice) {
      stopVoiceInput();
      state.pendingTranscript = null;
      state.voiceRetries = 0;
    }
  }

  function scrollTranscript() {
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }

  function addSystemNote(text) {
    const note = document.createElement("div");
    note.className = "system-note";
    note.textContent = text;
    els.transcript.appendChild(note);
    scrollTranscript();
  }

  function addTypingIndicator() {
    removeTypingIndicator();
    const el = document.createElement("div");
    el.className = "typing-note";
    el.textContent = "Agent is responding...";
    state.typingIndicator = el;
    els.transcript.appendChild(el);
    scrollTranscript();
  }

  function removeTypingIndicator() {
    if (state.typingIndicator && state.typingIndicator.parentNode) {
      state.typingIndicator.parentNode.removeChild(state.typingIndicator);
    }
    state.typingIndicator = null;
  }

  function appendMessage(role, text, payload) {
    const msg = document.createElement("div");
    msg.className = "msg " + role;
    msg.textContent = text;

    if (role === "agent" && payload) {
      const meta = document.createElement("div");
      meta.className = "meta-block";

      if (Array.isArray(payload.next_actions) && payload.next_actions.length) {
        const row = document.createElement("div");
        row.className = "chip-row";
        payload.next_actions.slice(0, 6).forEach((actRaw) => {
          const act = String(actRaw || "");
          const mapped = nextActionPrompts[act];
          if (mapped) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "chip action-btn";
            btn.textContent = act.replaceAll("_", " ");
            btn.addEventListener("click", () => sendCustomerMessage(mapped));
            row.appendChild(btn);
          } else {
            const chip = document.createElement("span");
            chip.className = "chip";
            chip.textContent = act.replaceAll("_", " ");
            row.appendChild(chip);
          }
        });
        meta.appendChild(row);
      }

      const links = [];
      const seen = new Set();
      if (Array.isArray(payload.self_service_options)) {
        payload.self_service_options.slice(0, 2).forEach((opt) => {
          if (opt && opt.url && !seen.has(opt.url)) {
            seen.add(opt.url);
            links.push({ label: opt.label || "Official self-service", url: opt.url });
          }
        });
      }
      if (Array.isArray(payload.official_next_steps)) {
        payload.official_next_steps.slice(0, 1).forEach((item) => {
          if (item && item.source_url && !seen.has(item.source_url)) {
            seen.add(item.source_url);
            links.push({ label: item.topic ? `Official ${item.topic}` : "Official support info", url: item.source_url });
          }
        });
      }
      if (Array.isArray(payload.citations) && !links.length) {
        payload.citations.slice(0, 1).forEach((cite) => {
          if (cite && cite.source_url && !seen.has(cite.source_url)) {
            seen.add(cite.source_url);
            links.push({ label: cite.topic ? `Source: ${cite.topic}` : "Source", url: cite.source_url });
          }
        });
      }

      if (links.length) {
        const stack = document.createElement("div");
        stack.className = "link-stack";
        links.forEach((link) => {
          const a = document.createElement("a");
          a.href = link.url;
          a.target = "_blank";
          a.rel = "noreferrer";
          a.textContent = link.label;
          stack.appendChild(a);
        });
        meta.appendChild(stack);
      }

      if (meta.childElementCount) msg.appendChild(meta);
    }

    els.transcript.appendChild(msg);
    scrollTranscript();
  }

  function applyBranding(capData) {
    const branding = capData?.branding || {};
    const supportContact = capData?.support_contact || {};
    const productName = branding.product_name || capData?.product_name || "Support";
    const brandName = branding.brand_name || productName;
    state.brand = {
      name: brandName,
      callCenterPhone: supportContact.call_center_phone || null,
      accessibilityPhone: supportContact.accessibility_phone || null,
    };
    nextActionPrompts.contact_bank_if_fraud = `I contacted my bank. What should I do next with ${brandName}?`;
    if (els.brandName) els.brandName.textContent = productName;
    if (els.brandSub) els.brandSub.textContent = "Customer support, chat and voice";
    if (els.heroTitle && branding.hero_title) els.heroTitle.textContent = branding.hero_title;
    if (els.heroSubtitle && branding.hero_subtitle) els.heroSubtitle.textContent = branding.hero_subtitle;
    if (els.resourcePanelTitle) {
      els.resourcePanelTitle.textContent = branding.resource_panel_title || `Official ${brandName} support links`;
    }
    const links = Array.isArray(branding.top_links) ? branding.top_links : [];
    if (els.topLinkPrimary) {
      const first = links[0];
      if (first?.url) {
        els.topLinkPrimary.href = first.url;
        els.topLinkPrimary.textContent = first.label || "Official Contact Info";
        els.topLinkPrimary.classList.remove("hidden");
      } else {
        els.topLinkPrimary.classList.add("hidden");
      }
    }
    if (els.topLinkSecondary) {
      const second = links[1];
      if (second?.url) {
        els.topLinkSecondary.href = second.url;
        els.topLinkSecondary.textContent = second.label || "Help Centre";
        els.topLinkSecondary.classList.remove("hidden");
      } else {
        els.topLinkSecondary.classList.add("hidden");
      }
    }
    const vars = branding.css_vars || {};
    const root = document.documentElement;
    if (vars.accent) root.style.setProperty("--accent", String(vars.accent));
    if (vars.accent_2) root.style.setProperty("--accent-2", String(vars.accent_2));
    if (vars.surface_tint) root.style.setProperty("--surface-tint", String(vars.surface_tint));
    if (vars.brand_dark) root.style.setProperty("--brand-dark", String(vars.brand_dark));
    const brandMark = document.querySelector(".brand-mark");
    if (brandMark && branding.brand_mark) brandMark.textContent = String(branding.brand_mark).slice(0, 2);
  }

  function renderResolutionArtifacts(artifacts) {
    if (!els.resolutionList) return;
    els.resolutionList.innerHTML = "";
    const a = artifacts && typeof artifacts === "object" ? artifacts : null;
    if (!a || !Object.keys(a).length) {
      els.resolutionList.innerHTML = '<div class="muted">Live status, rebooking options, refund estimates, and other actionable details appear here when available.</div>';
      return;
    }

    const addCard = (title, bodyNode, tone) => {
      const card = document.createElement("div");
      card.className = `artifact-card${tone ? " " + tone : ""}`;
      const h = document.createElement("div");
      h.className = "artifact-title";
      h.textContent = title;
      card.appendChild(h);
      card.appendChild(bodyNode);
      els.resolutionList.appendChild(card);
    };

    if (a.flight_status) {
      const body = document.createElement("div");
      body.className = "artifact-body";
      const fs = a.flight_status;
      body.innerHTML = `
        <div><strong>Flight:</strong> ${fs.flight_number || "Unknown"}</div>
        <div><strong>Status:</strong> ${String(fs.status || "Unknown").toLowerCase()}</div>
        <div><strong>Delay:</strong> ${fs.delay_minutes || 0} minutes</div>
        <div><strong>Gate:</strong> ${fs.departure_gate || "TBD"}</div>
      `;
      addCard("Flight status", body, fs.delay_minutes >= 180 ? "warn" : "");
    }

    if (Array.isArray(a.rebooking_options) && a.rebooking_options.length) {
      const wrap = document.createElement("div");
      wrap.className = "artifact-list";
      a.rebooking_options.forEach((opt) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "artifact-action";
        row.innerHTML = `<strong>Option ${opt.option}</strong><span>${opt.flight_number || ""} | ${opt.date || ""} | Fare difference $${opt.fare_diff ?? 0} CAD</span>`;
        row.addEventListener("click", () => sendCustomerMessage(`option ${opt.option}`));
        wrap.appendChild(row);
      });
      addCard("Rebooking options", wrap, "actionable");
    }

    if (a.compensation_estimate) {
      const comp = a.compensation_estimate;
      const body = document.createElement("div");
      body.className = "artifact-body";
      body.innerHTML = `
        <div><strong>Estimated compensation:</strong> $${comp.amount ?? 0} ${comp.currency || "CAD"}</div>
        <div><strong>Rule:</strong> ${comp.regulation_section || "APPR"}</div>
      `;
      addCard("Compensation estimate", body, "info");
    }

    if (a.refund_estimate) {
      const ref = a.refund_estimate;
      const body = document.createElement("div");
      body.className = "artifact-body";
      body.innerHTML = `
        <div><strong>Estimated refund:</strong> $${ref.amount_cad ?? 0} CAD</div>
        <div><strong>Timeline:</strong> ${ref.timeline_days ? `Up to ${ref.timeline_days} days` : "Varies by payment method"}</div>
      `;
      addCard("Refund options", body, "info");
    }

    if (a.refund_request?.refund_id) {
      const body = document.createElement("div");
      body.className = "artifact-body";
      body.innerHTML = `<div><strong>Request status:</strong> ${a.refund_request.status || "submitted"}</div>`;
      addCard("Refund submitted", body, "success");
    }

    if (a.travel_credit?.voucher_code) {
      const body = document.createElement("div");
      body.className = "artifact-body";
      body.innerHTML = `<div><strong>Travel credit:</strong> $${a.travel_credit.voucher_value_cad ?? 0} CAD</div>`;
      addCard("Travel credit issued", body, "success");
    }

    if (a.grounding) {
      const body = document.createElement("div");
      body.className = "artifact-body";
      body.innerHTML = `
        <div><strong>Official source grounding:</strong> ${a.grounding.source_backed ? "Yes" : "No / limited"}</div>
        <div><strong>Knowledge snapshot date:</strong> ${a.grounding.snapshot_date || "Unknown"}</div>
      `;
      addCard("Answer grounding", body, "subtle");
    }
  }

  function renderAlerts(alerts) {
    if (!els.alertsList) return;
    els.alertsList.innerHTML = "";
    if (!Array.isArray(alerts) || !alerts.length) {
      els.alertsList.innerHTML = '<div class="muted">No active trip alerts in this conversation yet. Ask about a flight or booking to enable proactive recovery suggestions.</div>';
      return;
    }
    alerts.forEach((alert) => {
      const card = document.createElement("div");
      card.className = `alert-card ${alert.severity || "info"}`;
      const title = document.createElement("div");
      title.className = "alert-title";
      title.textContent = alert.title || "Trip update";
      const summary = document.createElement("div");
      summary.className = "alert-summary";
      summary.textContent = alert.summary || "";
      card.appendChild(title);
      card.appendChild(summary);
      const actions = Array.isArray(alert.recommended_actions) ? alert.recommended_actions : [];
      if (actions.length) {
        const row = document.createElement("div");
        row.className = "chip-row";
        actions.slice(0, 4).forEach((a) => {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "chip action-btn";
          b.textContent = a.label || "Open";
          b.addEventListener("click", () => sendCustomerMessage(a.prompt || ""));
          row.appendChild(b);
        });
        card.appendChild(row);
      }
      els.alertsList.appendChild(card);
    });
  }

  function renderCustomerPlan(plan) {
    if (!plan || typeof plan !== "object") {
      els.planEmpty.classList.remove("hidden");
      els.planBody.classList.add("hidden");
      return;
    }
    els.planEmpty.classList.add("hidden");
    els.planBody.classList.remove("hidden");
    els.planIntent.textContent = String(plan.intent || "").replaceAll("_", " ") || "Unknown";
    els.planStage.textContent = String(plan.stage || "").replaceAll("_", " ") || "Unknown";

    els.planCanDo.innerHTML = "";
    (plan.what_i_can_do_now || []).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      els.planCanDo.appendChild(li);
    });

    els.planNeed.innerHTML = "";
    (plan.what_i_need_from_you || []).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      els.planNeed.appendChild(li);
    });

    els.planContext.innerHTML = "";
    const ctxItems = Array.isArray(plan.prepared_context) ? plan.prepared_context : [];
    if (!ctxItems.length) {
      const chip = document.createElement("span");
      chip.className = "chip info";
      chip.textContent = "No trip details captured yet";
      els.planContext.appendChild(chip);
    } else {
      ctxItems.forEach((item) => {
        const chip = document.createElement("span");
        chip.className = "chip info";
        chip.textContent = `${item.label || item.field}: ${item.value}`;
        els.planContext.appendChild(chip);
      });
    }
  }

  function stopPlayback() {
    if (state.currentAudio) {
      try {
        state.currentAudio.pause();
        state.currentAudio.src = "";
      } catch (_) {}
      state.currentAudio = null;
    }
    if (state.ttsAbort) {
      try { state.ttsAbort.abort(); } catch (_) {}
      state.ttsAbort = null;
    }
    if (state.synthEnabled) {
      try { window.speechSynthesis.cancel(); } catch (_) {}
    }
  }

  async function speak(text) {
    const clean = String(text || "").trim();
    if (!clean) return;
    stopPlayback();
    try {
      const controller = new AbortController();
      state.ttsAbort = controller;
      const resp = await fetch("/api/v1/customer/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: clean, voice_mode: "support", tenant: state.tenant }),
        signal: controller.signal,
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        state.currentAudio = audio;
        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (state.currentAudio === audio) state.currentAudio = null;
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
        };
        await audio.play();
        state.voiceBackend.tts = resp.headers.get("X-TTS-Provider") || "server";
        renderTechnical();
        return;
      }
    } catch (_) {
      // fall back
    } finally {
      state.ttsAbort = null;
    }
    if (state.synthEnabled) {
      try {
        const utter = new SpeechSynthesisUtterance(clean);
        utter.rate = 0.96;
        utter.pitch = 1.0;
        window.speechSynthesis.speak(utter);
        state.voiceBackend.tts = "browser";
      } catch (_) {}
    }
    renderTechnical();
  }

  async function callCustomerMessageAPI(content, channelOverride) {
    const channel = channelOverride || (state.mode === "voice" ? "voice" : "web");
    const body = {
      session_id: state.sessionId,
      customer_id: state.customerId,
      channel,
      content,
      tenant: state.tenant,
      metadata: { ui_mode: state.mode },
    };
    const endpoint = state.mode === "voice" ? "/api/v1/customer/voice/simulate" : "/api/v1/customer/message";
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
    return await resp.json();
  }

  async function sendCustomerMessage(text, channelOverride) {
    const content = (text ?? els.input.value ?? "").trim();
    if (!content || state.sending) return;
    appendMessage("user", content);
    if (text == null) els.input.value = "";
    removeTypingIndicator();
    addTypingIndicator();
    state.sending = true;
    els.sendBtn.disabled = true;
    setStatus("Sending...");

    try {
      const data = await callCustomerMessageAPI(content, channelOverride);
      state.lastResponse = data;
      removeTypingIndicator();
      appendMessage("agent", data.message || data.response_text || "I can help with that.", data);
      renderCustomerPlan(data.customer_plan || null);
      renderResolutionArtifacts(data.resolution_artifacts || {});
      if (data.follow_up_summary?.summary && data.support_reference) {
        addSystemNote("Summary and next steps are saved for this request.");
      }
      refreshTracker();
      refreshAlerts();
      setStatus("Connected.");
      if (state.mode === "voice") {
        const spoken = data.spoken_message || data.message || data.response_text || "";
        state.voiceRetries = 0;
        await speak(spoken);
      }
    } catch (err) {
      removeTypingIndicator();
      appendMessage("agent", `Sorry, I ran into a problem while sending your request. ${String(err)}`);
      setStatus("Unable to send right now.");
    } finally {
      state.sending = false;
      els.sendBtn.disabled = false;
      renderTechnical();
    }
  }

  async function continueChannel(toChannel) {
    try {
      const resp = await fetch("/api/v1/customer/continue-channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          customer_id: state.customerId,
          from_channel: state.mode === "voice" ? "voice" : "web_chat",
          to_channel: toChannel,
          tenant: state.tenant,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      addSystemNote(data.customer_message || `Prepared continuation to ${toChannel}.`);
      if (toChannel === "phone" && data.phone_number) {
        addSystemNote(`Call ${state.brand?.name || "support"}: ${data.phone_number}`);
      }
      if (toChannel === "sms" && data.sms_preview) {
        addSystemNote("SMS summary is ready. You can use Summary if you want a fresh recap after another update.");
      }
      setStatus(`Prepared continuation to ${toChannel}.`);
      refreshTracker();
    } catch (err) {
      if (toChannel === "phone") {
        const phone = state.brand?.callCenterPhone || "the official support number";
        addSystemNote(`Could not prepare phone continuation automatically. ${state.brand?.name || "Support"}'s published call center number is ${phone}. Wait times may vary.`);
        setStatus("Phone number shown.");
        return;
      }
      if (toChannel === "sms") {
        addSystemNote("Could not prepare SMS continuation automatically. You can still use Summary to prepare a support recap, or continue by phone.");
        setStatus("SMS continuation unavailable.");
        return;
      }
      addSystemNote(`Could not prepare ${toChannel} continuation. ${String(err)}`);
    }
  }

  async function resetSession() {
    stopPlayback();
    stopVoiceInput();
    try {
      await fetch("/api/v1/customer/session/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          customer_id: state.customerId,
          channel: state.mode === "voice" ? "voice" : "web",
          tenant: state.tenant,
        }),
      });
    } catch (_) {
      // Local reset still proceeds if backend reset fails.
    }
    state.sessionId = newSessionId();
    state.lastResponse = null;
    els.transcript.innerHTML = "";
    appendMessage(
      "agent",
      `New conversation started. I can help with flight status and disruptions, rebooking, cancellations, refunds, baggage issues, accessibility support, and human support handoff for ${state.brand?.name || "your trip"}.`
    );
    renderCustomerPlan(null);
    renderResolutionArtifacts({});
    renderAlerts([]);
    els.input.value = "";
    setStatus("Connected.");
    addSystemNote("Started a new request.");
    refreshTracker();
    refreshAlerts();
    renderTechnical();
  }

  async function sendFollowUpSummary() {
    try {
      const resp = await fetch("/api/v1/customer/follow-up-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          customer_id: state.customerId,
          channel: state.mode === "voice" ? "voice" : "web",
          delivery_channel: "sms",
          tenant: state.tenant,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || data.error || "summary_failed");
      if (!data.ok) {
        addSystemNote(data.message || "Ask a question first, then I can prepare a summary.");
        setStatus("Summary unavailable yet.");
        return;
      }
      addSystemNote("Summary prepared. You can continue by SMS or keep going here.");
      refreshTracker();
    } catch (err) {
      addSystemNote(`Could not prepare summary right now. ${String(err)}`);
    }
  }

  async function refreshTracker() {
    if (!els.trackerList) return;
    try {
      const resp = await fetch(`/api/v1/customer/references?tenant=${encodeURIComponent(state.tenant)}&customer_id=${encodeURIComponent(state.customerId)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.trackerData = data;
      renderTracker(data.references || []);
    } catch (err) {
      if (!state.trackerData) {
        els.trackerList.innerHTML = '<div class="muted">Could not load support references.</div>';
      }
    }
  }

  function renderTracker(references) {
    if (!els.trackerList) return;
    els.trackerList.innerHTML = "";
    if (!Array.isArray(references) || !references.length) {
      els.trackerList.innerHTML = '<div class="muted">Your active support references will appear here.</div>';
      return;
    }
    references.slice(0, 8).forEach((ref) => {
      const card = document.createElement("div");
      card.className = "tracker-item";
      const top = document.createElement("div");
      top.className = "tracker-top";
      const customerLabel = String(ref.customer_label || "Support request");
      top.innerHTML = `<strong>${customerLabel}</strong><span class="tracker-status">${String(ref.status_label || ref.status || "").replaceAll("_", " ")}</span>`;
      const sum = document.createElement("div");
      sum.className = "tracker-summary";
      sum.textContent = ref.summary || "Support update available.";
      const meta = document.createElement("div");
      meta.className = "tracker-meta";
      meta.textContent = `Updated ${new Date(ref.updated_at).toLocaleString()}`;
      card.appendChild(top);
      card.appendChild(sum);
      card.appendChild(meta);
      if (Array.isArray(ref.next_steps) && ref.next_steps.length) {
        const row = document.createElement("div");
        row.className = "chip-row";
        ref.next_steps.slice(0, 3).forEach((step) => {
          const chip = document.createElement("span");
          chip.className = "chip";
          chip.textContent = String(step).replaceAll("_", " ");
          row.appendChild(chip);
        });
        card.appendChild(row);
      }
      if (ref.next_update_hint) {
        const hint = document.createElement("div");
        hint.className = "tracker-hint";
        hint.textContent = ref.next_update_hint;
        card.appendChild(hint);
      }
      els.trackerList.appendChild(card);
    });
  }

  async function refreshAlerts() {
    if (!els.alertsList) return;
    try {
      const url = `/api/v1/customer/alerts?tenant=${encodeURIComponent(state.tenant)}&session_id=${encodeURIComponent(state.sessionId)}&customer_id=${encodeURIComponent(state.customerId)}`;
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.lastAlerts = Array.isArray(data.alerts) ? data.alerts : [];
      renderAlerts(state.lastAlerts);
    } catch (_) {
      if (!state.lastAlerts?.length) {
        renderAlerts([]);
      }
    }
  }

  function triggerUploadPicker() {
    if (els.uploadInput) els.uploadInput.click();
  }

  async function handleUploadFile(file) {
    if (!file) return;
    setStatus("Analyzing upload...");
    try {
      const base64 = await blobToBase64(file);
      const resp = await fetch("/api/v1/customer/upload/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_name: file.name,
          mime_type: file.type || "application/octet-stream",
          content_base64: base64,
          tenant: state.tenant,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.detail || data.error || "upload_analyze_failed");
      const extracted = data.entities || {};
      const extractedKeys = Object.keys(extracted);
      addSystemNote(
        extractedKeys.length
          ? `Upload analyzed (${data.extraction_method}). Found: ${extractedKeys.map((k) => `${k}=${extracted[k]}`).join(", ")}`
          : `Upload analyzed (${data.extraction_method}). I did not extract key details automatically.`
      );
      if (data.suggested_message) {
        els.input.value = data.suggested_message;
        els.input.focus();
        setStatus("Upload analyzed. Review or send the suggested message.");
      } else {
        setStatus("Upload analyzed.");
      }
      if (Array.isArray(data.warnings) && data.warnings.length) {
        els.voiceBackendHint.textContent = `Upload notes: ${data.warnings.slice(0, 2).join(", ")}`;
      }
    } catch (err) {
      addSystemNote(`Upload analysis failed. ${String(err)}`);
      setStatus("Upload analysis failed.");
    } finally {
      if (els.uploadInput) els.uploadInput.value = "";
    }
  }

  async function loadCapabilities() {
    try {
      const [capResp, healthResp] = await Promise.all([
        fetch(`/api/v1/customer/capabilities?tenant=${encodeURIComponent(state.tenant)}`),
        fetch("/health"),
      ]);
      const capData = capResp.ok ? await capResp.json() : null;
      const healthData = healthResp.ok ? await healthResp.json() : null;
      state.lastCapabilities = capData;
      state.lastHealth = healthData;
      if (capData) {
        applyBranding(capData);
        els.capabilityList.innerHTML = "";
        (capData.what_it_can_help_with || []).forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          els.capabilityList.appendChild(li);
        });
        els.commitmentList.innerHTML = "";
        (capData.support_commitments || []).forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          els.commitmentList.appendChild(li);
        });
        if (capData.product_name) {
          els.brandName.textContent = capData.product_name;
          document.title = capData.product_name;
        }
        if (Array.isArray(capData.suggested_starters) && capData.suggested_starters.length && els.quickActions) {
          const quickButtons = Array.from(els.quickActions.querySelectorAll("button[data-msg]"));
          capData.suggested_starters.slice(0, quickButtons.length).forEach((starter, idx) => {
            const btn = quickButtons[idx];
            if (!btn) return;
            btn.dataset.msg = starter;
            btn.textContent = starter.length > 28 ? starter.slice(0, 28).trimEnd() + "..." : starter;
            btn.title = starter;
          });
        }
        els.officialChannels.innerHTML = "";
        const entries = capData.official_channel_snapshot?.entries || [];
        entries.slice(0, 8).forEach((entry) => {
          const div = document.createElement("div");
          div.className = "link-item";
          const a = document.createElement("a");
          a.href = entry.source_url;
          a.target = "_blank";
          a.rel = "noreferrer";
          a.textContent = entry.topic ? `Official ${entry.topic} guidance` : "Official support guidance";
          const small = document.createElement("small");
          small.textContent = entry.text || "";
          div.appendChild(a);
          div.appendChild(small);
          els.officialChannels.appendChild(div);
        });
      }
      if (healthData) {
        state.voiceBackend.stt = healthData.stt_available ? "server" : "browser";
        state.voiceBackend.tts = healthData.tts_available ? "server" : "browser";
        els.voiceBackendHint.textContent = healthData.stt_available
          ? `Server transcription available (${healthData.llm_provider || "llm"}).`
          : "Browser transcription fallback.";
      }
      renderTechnical();
    } catch (_) {
      els.voiceBackendHint.textContent = "Local support service is available, but capability details could not be loaded.";
      renderTechnical();
    }
  }

  function toggleCollapse(button, body) {
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    body.classList.toggle("hidden", expanded);
  }

  async function blobToBase64(blob) {
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const comma = result.indexOf(",");
        resolve(comma >= 0 ? result.slice(comma + 1) : result);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function preferredRecorderMime() {
    const prefs = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    for (const mime of prefs) {
      try {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(mime)) return mime;
      } catch (_) {}
    }
    return "";
  }

  async function ensureMediaStream() {
    if (state.mediaStream) return state.mediaStream;
    state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    return state.mediaStream;
  }

  async function startVoiceRecording() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      return startSpeechRecognitionFallback();
    }
    stopPlayback();
    try {
      const stream = await ensureMediaStream();
      state.mediaChunks = [];
      state.mediaMime = preferredRecorderMime();
      state.mediaRecorder = state.mediaMime ? new MediaRecorder(stream, { mimeType: state.mediaMime }) : new MediaRecorder(stream);
      state.mediaMime = state.mediaRecorder.mimeType || state.mediaMime || "audio/webm";

      state.mediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) state.mediaChunks.push(ev.data);
      };
      state.mediaRecorder.onerror = () => {
        addSystemNote("Microphone recording failed. You can type your question instead.");
        setStatus("Voice input unavailable.");
        resetVoiceButton();
      };
      state.mediaRecorder.onstop = async () => {
        const blob = new Blob(state.mediaChunks, { type: state.mediaMime || "audio/webm" });
        state.mediaChunks = [];
        resetVoiceButton();
        await transcribeAndSend(blob, state.mediaMime || "audio/webm");
      };

      state.listening = true;
      els.voiceInputBtn.classList.add("listening");
      els.voiceInputBtn.textContent = "Stop Voice Input";
      els.voiceHint.textContent = "Listening...";
      setStatus("Listening...");
      state.mediaRecorder.start();
    } catch (err) {
      addSystemNote("Microphone access is blocked or unavailable. Allow microphone access in your browser and try again.");
      els.voiceHint.textContent = "Microphone permission is blocked or unavailable.";
      setStatus("Voice input unavailable.");
      resetVoiceButton();
    }
  }

  function stopVoiceInput() {
    if (state.mediaRecorder && state.listening && state.mediaRecorder.state !== "inactive") {
      try { state.mediaRecorder.stop(); } catch (_) {}
      state.listening = false;
    }
    if (state.recognition && state.listening) {
      try { state.recognition.stop(); } catch (_) {}
      state.listening = false;
    }
    resetVoiceButton();
  }

  function resetVoiceButton() {
    state.listening = false;
    els.voiceInputBtn.classList.remove("listening");
    els.voiceInputBtn.textContent = "Start Voice Input";
    if (els.voiceHint.textContent === "Listening...") {
      els.voiceHint.textContent = "Speak, then press again to stop.";
    }
    if (els.statusLine.textContent === "Listening...") {
      setStatus("Voice mode.");
    }
  }

  function setVoiceStatusHint(primary, secondary) {
    if (els.voiceHint && primary != null) els.voiceHint.textContent = String(primary);
    if (els.voiceBackendHint && secondary != null) els.voiceBackendHint.textContent = String(secondary);
  }

  async function transcribeAndSend(blob, mimeType) {
    if (!blob || blob.size < 300) {
      addSystemNote("I couldn't hear enough audio. Please try again and speak a little longer.");
      els.voiceHint.textContent = "Try again and speak a little longer.";
      return;
    }
    setStatus("Transcribing...");
    els.voiceHint.textContent = "Transcribing...";
    try {
      const audioBase64 = await blobToBase64(blob);
      const resp = await fetch("/api/v1/customer/voice/transcribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_base64: audioBase64,
          mime_type: mimeType || "audio/webm",
          language: "en",
          session_id: state.sessionId,
          customer_id: state.customerId,
          tenant: state.tenant,
        }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        throw new Error(data.message || data.detail || data.error || "transcription_failed");
      }
      state.voiceBackend.stt = data.provider || "server";
      state.pendingTranscript = data.text || "";
      const confPct = Math.round((Number(data.confidence) || 0) * 100);
      const backendLine = `Server transcription active (${data.provider}${data.model ? ` / ${data.model}` : ""})${Number.isFinite(confPct) ? ` - ${confPct}% confidence` : ""}.`;
      setVoiceStatusHint(`Heard: "${data.text}"`, backendLine);
      renderTechnical();
      if (data.needs_confirmation) {
        state.voiceRetries += 1;
        if (data.reason === "likely_agent_echo") {
          setVoiceStatusHint("I may have heard the agent audio. Try again after playback ends.", backendLine);
          addSystemNote(data.message || "I may have picked up the agent audio. Please try again after the reply finishes.");
          setStatus("Voice input needs another try.");
          if (state.voiceRetries >= 2) {
            addSystemNote("If voice keeps failing, type your question or upload a document/photo and I can extract the details.");
          }
          return;
        }
        els.input.value = data.text || "";
        els.input.focus();
        addSystemNote(data.message || "Please check the transcript before sending.");
        setStatus("Please review the transcript before sending.");
        return;
      }
      state.voiceRetries = 0;
      await sendCustomerMessage(data.text, "voice");
    } catch (err) {
      addSystemNote(`Voice transcription failed. ${String(err)}`);
      els.voiceHint.textContent = "Voice transcription failed. You can type your question instead.";
      setStatus("Voice transcription failed.");
    }
  }

  function initSpeechRecognitionFallback() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = "en-CA";
    rec.interimResults = false;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    rec.onstart = () => {
      state.listening = true;
      els.voiceInputBtn.classList.add("listening");
      els.voiceInputBtn.textContent = "Stop Voice Input";
      els.voiceHint.textContent = "Listening...";
      setStatus("Listening...");
    };
    rec.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim() || "";
      if (!transcript) return;
      els.voiceHint.textContent = `Heard: "${transcript}"`;
      sendCustomerMessage(transcript, "voice");
    };
    rec.onerror = (event) => {
      const code = event.error || "unknown";
      addSystemNote(`Voice input error (${code}). You can type your question instead.`);
      els.voiceHint.textContent = "Voice input failed. You can type instead.";
    };
    rec.onend = () => {
      resetVoiceButton();
    };
    state.recognition = rec;
  }

  function startSpeechRecognitionFallback() {
    if (!state.recognition) initSpeechRecognitionFallback();
    if (!state.recognition) {
      addSystemNote("This browser does not support microphone input here. You can still type your question.");
      els.voiceHint.textContent = "Microphone input is not supported in this browser.";
      return;
    }
    stopPlayback();
    try {
      state.recognition.start();
    } catch (_) {
      addSystemNote("Voice input could not start. Please try again or type your question.");
    }
  }

  function toggleVoiceInput() {
    if (state.listening) {
      stopVoiceInput();
      return;
    }
    startVoiceRecording();
  }

  function renderTechnical() {
    const payload = {
      sessionId: state.sessionId,
      customerId: state.customerId,
      tenant: state.tenant,
      mode: state.mode,
      voiceBackend: state.voiceBackend,
      mediaRecorderSupported: Boolean(window.MediaRecorder),
      speechRecognitionSupported: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
      speechSynthesisSupported: Boolean(state.synthEnabled),
      health: state.lastHealth,
      lastCapabilities: state.lastCapabilities,
      lastResponse: state.lastResponse,
      lastAlerts: state.lastAlerts,
    };
    els.technicalPre.textContent = JSON.stringify(payload, null, 2);
  }

  function bindEvents() {
    els.modeTextBtn.addEventListener("click", () => setMode("text"));
    els.modeVoiceBtn.addEventListener("click", () => setMode("voice"));

    els.sendBtn.addEventListener("click", () => sendCustomerMessage());
    els.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendCustomerMessage();
      }
    });

    els.quickActions.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-msg]");
      if (!btn) return;
      sendCustomerMessage(btn.dataset.msg || "");
    });

    els.voiceInputBtn.addEventListener("click", toggleVoiceInput);
    els.continuePhoneBtn.addEventListener("click", () => continueChannel("phone"));
    els.continueSmsBtn.addEventListener("click", () => continueChannel("sms"));
    if (els.sendSummaryBtn) els.sendSummaryBtn.addEventListener("click", sendFollowUpSummary);
    if (els.resetSessionBtn) {
      els.resetSessionBtn.addEventListener("click", resetSession);
    }
    if (els.uploadBtn) els.uploadBtn.addEventListener("click", triggerUploadPicker);
    if (els.uploadInput) {
      els.uploadInput.addEventListener("change", (e) => {
        const file = e.target?.files?.[0];
        if (file) handleUploadFile(file);
      });
    }

    els.planToggle.addEventListener("click", () => toggleCollapse(els.planToggle, els.planBodyWrap));
    els.resourcesToggle.addEventListener("click", () => toggleCollapse(els.resourcesToggle, els.resourcesBody));
    if (els.alertsToggle && els.alertsBody) {
      els.alertsToggle.addEventListener("click", () => toggleCollapse(els.alertsToggle, els.alertsBody));
    }
    if (els.resolutionToggle && els.resolutionBody) {
      els.resolutionToggle.addEventListener("click", () => toggleCollapse(els.resolutionToggle, els.resolutionBody));
    }
    els.capabilitiesToggle.addEventListener("click", () => toggleCollapse(els.capabilitiesToggle, els.capabilitiesBody));
    if (els.trackerToggle && els.trackerBody) {
      els.trackerToggle.addEventListener("click", () => toggleCollapse(els.trackerToggle, els.trackerBody));
    }
    if (els.trackerRefreshBtn) els.trackerRefreshBtn.addEventListener("click", refreshTracker);
    els.technicalToggle.addEventListener("click", () => toggleCollapse(els.technicalToggle, els.technicalBody));
  }

  function init() {
    bindEvents();
    initSpeechRecognitionFallback();
    setMode("text");
    appendMessage(
      "agent",
      "Hello. I can help with flight status and disruptions, rebooking, cancellations, refunds, baggage issues, accessibility support, and connecting you to a human agent if needed."
    );
    renderCustomerPlan(null);
    renderResolutionArtifacts({});
    renderAlerts([]);
    loadCapabilities();
    refreshTracker();
    refreshAlerts();
    renderTechnical();
  }

  init();
})();
