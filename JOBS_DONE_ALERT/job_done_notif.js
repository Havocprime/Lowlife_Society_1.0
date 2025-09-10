// ==UserScript==
// @name         ChatGPT — Job’s Done Notifier (v2)
// @namespace    vincent.chatgpt.jobsdone
// @version      2.0
// @description  Play tones and/or ping a webhook when ChatGPT finishes, needs "Continue generating", or errors.
// @match        https://chat.openai.com/*
// @match        https://chatgpt.com/*
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // =======================
  // CONFIG
  // =======================
  const QUIET_MS = 2500;              // No DOM changes for this long => assume finished
  const CHECK_EVERY_MS = 800;         // Poll loop
  const DEBOUNCE_MS = 3000;           // Minimum gap between signals
  const ENABLE_SOUND = true;          // Local tone(s)
  const ENABLE_WEBHOOK = false;       // POST JSON payloads to your server/Discord
  const WEBHOOK_URL = "https://your-webhook-url.example";

  // Which events should trigger signals
  const SIGNAL_ON = {
    finished: true,          // streaming stopped naturally
    need_continue: true,     // "Continue generating" button visible
    error_hint: true         // red banners / retry UIs detected
  };

  // Tone presets (Hz, seconds). Change to taste.
  const TONES = {
    finished:  [880, 0.20],  // A5 short
    need_continue: [660, 0.25], // E5 short-ish
    error_hint: [220, 0.35]  // A3 lower + longer
  };

  // =======================
  // UTIL: SOUND + WEBHOOK
  // =======================
  function beep(freq = 880, secs = 0.2) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "sine";
      o.frequency.value = freq;
      o.connect(g);
      g.connect(ctx.destination);
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.01);
      o.start();
      o.stop(ctx.currentTime + secs);
    } catch (_) {}
  }

  async function hitWebhook(event, reason) {
    if (!ENABLE_WEBHOOK || !WEBHOOK_URL) return;
    const payload = {
      source: "chatgpt",
      event,                // "finished" | "need_continue" | "error_hint"
      reason,
      ts: new Date().toISOString(),
      title: document.title,
      url: location.href,
      // Optional: include last 100 chars of visible assistant text for context
      sample: getLastAssistantText(120)
    };
    try {
      await fetch(WEBHOOK_URL, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
    } catch (_) {}
  }

  function signal(event, reason = "") {
    const now = Date.now();
    if (now - lastSignalAt < DEBOUNCE_MS) return false;
    lastSignalAt = now;

    if (ENABLE_SOUND && TONES[event]) {
      const [f, s] = TONES[event];
      beep(f, s);
    }
    hitWebhook(event, reason);
    return true;
  }

  // =======================
  // HEURISTICS
  // =======================
  let lastMutation = Date.now();
  let lastSignalAt = 0;

  const MO = new MutationObserver(() => {
    lastMutation = Date.now();
  });

  MO.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  function continueButtonVisible() {
    // ChatGPT UI changes often; be fuzzy
    const btns = Array.from(document.querySelectorAll("button"));
    return btns.some(b => /continue generating/i.test(b.textContent || ""));
  }

  function errorBannerVisible() {
    // Look for error/retry indicators, red banners, "network error" texts, etc.
    const text = document.body.innerText.toLowerCase();
    return (
      text.includes("network error") ||
      text.includes("something went wrong") ||
      text.includes("retry") && text.includes("failed") ||
      text.includes("error generating") ||
      // Sometimes a red toast/banner is an aria-live region
      Array.from(document.querySelectorAll('[role="alert"]')).length > 0
    );
  }

  function getLastAssistantText(limit = 120) {
    try {
      // Grab the last assistant message block’s visible text
      const blocks = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
      const last = blocks[blocks.length - 1];
      if (!last) return "";
      const t = (last.innerText || "").trim().replace(/\s+/g, " ");
      return t.slice(-limit);
    } catch {
      return "";
    }
  }

  function isLikelyStreaming() {
    // If DOM changes are happening frequently, we’re streaming
    return (Date.now() - lastMutation) < 500; // sub-half-second churn
  }

  // =======================
  // MAIN LOOP
  // =======================
  setInterval(() => {
    const idleFor = Date.now() - lastMutation;

    if (SIGNAL_ON.need_continue && continueButtonVisible()) {
      signal("need_continue", "continue_button");
      return;
    }

    if (SIGNAL_ON.error_hint && errorBannerVisible()) {
      signal("error_hint", "error_banner_or_retry");
      return;
    }

    // If not streaming and we've been quiet long enough => finished
    if (!isLikelyStreaming() && idleFor >= QUIET_MS) {
      SIGNAL_ON.finished && signal("finished", "quiet_timeout");
    }
  }, CHECK_EVERY_MS);

  // Optional: also react to the “✅ JOB’S DONE” marker if present
  const markerObserver = new MutationObserver(() => {
    const text = document.body.innerText || "";
    if (/\b✅ JOB’S DONE\b/.test(text)) {
      SIGNAL_ON.finished && signal("finished", "marker_detected");
    }
  });
  markerObserver.observe(document.body, { childList: true, subtree: true });
})();
