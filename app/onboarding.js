(function () {
  const KEY = "cc:onboarding:v1";
  const STEPS = ["filter", "details", "save", "route"];
  const TITLES = { filter: "Find your kind of event", details: "Take a closer look", save: "Keep a favorite", route: "Find the way" };
  const COPY = {
    filter: "Squeak! Pick something you like.",
    details: "This one looks interesting. Take a peek!",
    save: "Love it? Tap the heart.",
    route: "Come on, I’ll show you the way."
  };
  let bridge, progress, active = false, stepDone = false, selectedId = null;
  let fallback = false, routeError = false, showingMine = false, replay = false;
  let snapshot = null, focusReturn = null, highlighted = null, listeners = false, saves = Promise.resolve();
  let resizeHandler = null, motionPreference = null;

  function emptyProgress() {
    return { version: 1, intro_seen: false, tour_status: "not_started", current_step: "filter", skipped_steps: [], selected_tutorial_event_id: null, intro_screen: 1 };
  }
  function normalize(value) {
    const p = Object.assign(emptyProgress(), value || {});
    if (STEPS.indexOf(p.current_step) < 0) p.current_step = "filter";
    if (!Array.isArray(p.skipped_steps)) p.skipped_steps = [];
    p.skipped_steps = p.skipped_steps.filter(function (s) { return STEPS.indexOf(s) >= 0; });
    if (["not_started", "in_progress", "completed", "skipped"].indexOf(p.tour_status) < 0) p.tour_status = "not_started";
    if (p.intro_screen < 1 || p.intro_screen > 3) p.intro_screen = 1;
    return p;
  }
  function A() { return window.CampusCornersAccount; }
  function readGuest() {
    try { return normalize(JSON.parse(localStorage.getItem(KEY) || "null")); }
    catch (_) { return emptyProgress(); }
  }
  function accountUIKey(id) { return "cc:onboarding:ui:" + id; }
  function introScreenForAccount(id) {
    try {
      const v = JSON.parse(localStorage.getItem(accountUIKey(id)) || "null");
      return v && v.intro_screen >= 1 && v.intro_screen <= 3 ? v.intro_screen : 1;
    } catch (_) { return 1; }
  }
  function persistIntroScreen(screen) {
    progress.intro_screen = screen;
    if (A().isAuthenticated()) {
      const user = A().getUser();
      localStorage.setItem(accountUIKey(user.id), JSON.stringify({ intro_screen: screen }));
    } else if (A().getStatus() === "guest") {
      localStorage.setItem(KEY, JSON.stringify(progress));
    }
  }
  function serverData() {
    return {
      version: 1,
      intro_seen: !!progress.intro_seen,
      tour_status: progress.tour_status,
      current_step: progress.current_step,
      skipped_steps: progress.skipped_steps.slice(),
      selected_tutorial_event_id: selectedId || null
    };
  }
  function persist() {
    if (replay) return;
    progress.current_step = STEPS.indexOf(progress.current_step) >= 0 ? progress.current_step : "filter";
    progress.selected_tutorial_event_id = selectedId || null;
    if (A().isAuthenticated()) {
      const data = serverData();
      saves = saves.then(function () { return A().saveOnboarding(data); }).catch(function () {
        announce("Tour progress could not be saved. Retry your account connection when you can.");
      });
    } else if (A().getStatus() === "guest") {
      localStorage.setItem(KEY, JSON.stringify(progress));
    }
  }
  function announce(text) {
    const el = document.getElementById("ccActionStatus");
    if (el) el.textContent = text;
  }
  function btn(text, cls, action) {
    const el = document.createElement("button");
    el.type = "button"; el.className = cls || "cc-button"; el.textContent = text;
    el.addEventListener("click", action); return el;
  }
  function text(parent, tag, cls, value) {
    const el = document.createElement(tag);
    if (cls) el.className = cls; el.textContent = value; parent.appendChild(el); return el;
  }
  function escapeHTML(value) {
    return String(value || "").replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }
  function introMarkup(screen) {
    const progress = '<div class="cc-intro-progress" role="img" aria-label="Welcome screen ' + screen + ' of 3">' + [1, 2, 3].map(function (dot) {
      return '<span' + (dot === screen ? ' class="is-current"' : '') + '></span>';
    }).join("") + '</div>';
    const mascot = '<picture class="cc-intro-mascot"><source srcset="app/sparko-idle.gif" media="(prefers-reduced-motion: no-preference)"><img src="app/sparko-idle.png" alt="" class="cc-intro-sparko"></picture>';
    const before = '<div class="cc-intro">' + progress + '<div class="cc-intro-art">' + mascot + '</div>';
    if (screen === 1) return before + '<h3 class="cc-kicker">Hi, I’m Sparko.</h3><p>Let’s find something fun around campus.</p><div class="cc-modal-actions"><button class="cc-button cc-button-primary" data-next type="button">Meet the map</button></div><button class="cc-text-button" data-skip type="button">Skip</button></div>';
    if (screen === 2) return before + '<h3 class="cc-kicker">A little plan for your day.</h3><p>Find an event, save a favorite, and see the way there.</p><div class="cc-intro-previews" aria-hidden="true"><span><b>⌖</b> Find</span><span><b>♡</b> Save</span><span><b>➜</b> Go</span></div><div class="cc-modal-actions"><button class="cc-button" data-back type="button">Back</button><button class="cc-button cc-button-primary" data-next type="button">Next</button></div><button class="cc-text-button" data-skip type="button">Skip</button></div>';
    if (A().isAuthenticated()) {
      const nickname = escapeHTML(A().getUser().nickname);
      return before + '<h3 class="cc-kicker">Ready, ' + nickname + '?</h3><p>Let’s explore.</p><div class="cc-modal-actions"><button class="cc-button" data-back type="button">Back</button><button class="cc-button cc-button-primary" data-start type="button">Let’s explore</button></div><button class="cc-text-button" data-skip type="button">Skip</button></div>';
    }
    return before + '<h3 class="cc-kicker">Keep your favorites close.</h3><p>Create an account, or come explore with me.</p><div class="cc-modal-actions cc-modal-actions-stack"><button class="cc-button cc-button-primary" data-register type="button">Create account</button><button class="cc-button" data-login type="button">Log in</button><button class="cc-button cc-button-quiet" data-start type="button">Continue as guest</button></div><div class="cc-modal-actions"><button class="cc-button" data-back type="button">Back</button></div><button class="cc-text-button" data-skip type="button">Skip</button></div>';
  }
  function showIntro(screen) {
    const current = Math.max(1, Math.min(3, screen || 1));
    persistIntroScreen(current);
    A().showModal(introMarkup(current), {
      title: "Welcome to Campus Corners",
      onEscape: finishIntro,
      onClose: finishIntro
    });
    syncMascotMotion();
    const root = document.getElementById("ccModalRoot");
    const next = root.querySelector("[data-next]");
    const back = root.querySelector("[data-back]");
    const start = root.querySelector("[data-start]");
    const skip = root.querySelector("[data-skip]");
    if (next) next.onclick = function () { showIntro(current + 1); };
    if (back) back.onclick = function () { showIntro(current - 1); };
    if (start) start.onclick = finishIntro;
    if (skip) skip.onclick = finishIntro;
    const invite = function (mode) {
      A().openAuthModal(mode, { fromInvitation: true, onCancel: function () { showIntro(3); } });
    };
    const register = root.querySelector("[data-register]");
    const login = root.querySelector("[data-login]");
    if (register) register.onclick = function () { invite("register"); };
    if (login) login.onclick = function () { invite("login"); };
  }
  function finishIntro() {
    if (!progress) progress = emptyProgress();
    progress.intro_seen = true;
    progress.tour_status = "in_progress";
    progress.current_step = "filter";
    progress.skipped_steps = [];
    selectedId = null;
    persist();
    A().closeModal({ silent: true });
    beginTour("filter", false);
  }
  function guestProgressExists(p) {
    return !!(p && (p.intro_seen || ["in_progress", "completed", "skipped"].indexOf(p.tour_status) >= 0));
  }
  function serverProgressToUI(value) {
    const p = normalize(value);
    const user = A().getUser();
    p.intro_screen = user ? introScreenForAccount(user.id) : 1;
    return p;
  }
  function beginTour(step, isReplay) {
    if (!bridge) return;
    if (A() && A().closeModal && document.getElementById("ccModalRoot") && !document.getElementById("ccModalRoot").hidden) {
      A().closeModal({ silent: true });
    }
    replay = !!isReplay && ["completed", "skipped"].indexOf(progress.tour_status) >= 0;
    focusReturn = document.activeElement;
    snapshot = bridge.captureUIState();
    bridge.prepareTour();
    active = true;
    enter(step || "filter", true);
  }
  function enter(step, initial) {
    progress.current_step = STEPS.indexOf(step) >= 0 ? step : "filter";
    showingMine = false; fallback = false; routeError = false;
    if (progress.current_step === "filter") {
      selectedId = null; stepDone = false;
    } else if (progress.current_step === "details") {
      if (!selectedId) {
        const visible = bridge.findCurrentTourEvent();
        if (visible) selectedId = visible.id; else fallback = true;
      }
      stepDone = false;
      if (selectedId && initial) bridge.selectSampleEvent(selectedId);
    } else if (progress.current_step === "save") {
      stepDone = !!(selectedId && bridge.isEventSaved(selectedId));
      if (selectedId) bridge.openEvent(selectedId);
    } else {
      stepDone = !!(selectedId && bridge.isRouteVisible(selectedId));
      if (selectedId) bridge.openEvent(selectedId);
    }
    progress.selected_tutorial_event_id = selectedId;
    persist(); drawCard(); placeCard(true);
  }
  function index() { return STEPS.indexOf(progress.current_step); }
  function selector() {
    if (showingMine) return '[data-tour="my-events"]';
    if (progress.current_step === "filter") return '[data-tour^="category-"]';
    if (progress.current_step === "details") return stepDone ? "#sheetTitle" : (selectedId ? '[data-tour="event-' + selectedId + '"]' : "#mapwrap");
    if (progress.current_step === "save") return '[data-tour="event-save"]';
    return stepDone ? "#routebar" : '[data-tour="event-route"]';
  }
  function drawCard() {
    const layer = document.getElementById("ccTourLayer"), card = document.getElementById("ccTourCard");
    if (!active || !layer || !card) return;
    card.className = "cc-tour-card cc-tour-step-" + progress.current_step;
    card.replaceChildren();
    const head = document.createElement("div"); head.className = "cc-tour-heading";
    text(head, "span", "cc-tour-count", (index() + 1) + " / 4");
    text(head, "b", "", TITLES[progress.current_step]); card.appendChild(head);
    const guide = document.createElement("div"); guide.className = "cc-tour-guide";
    const sparko = document.createElement("img"); sparko.className = "cc-tour-sparko"; sparko.src = "app/sparko-idle.png"; sparko.alt = "Sparko";
    const speech = document.createElement("div"); speech.className = "cc-tour-speech";
    const spoken = progress.current_step === "save" && stepDone ? "Tucked into My Events!" : COPY[progress.current_step];
    text(speech, "p", "cc-tour-copy", spoken);
    guide.append(sparko, speech); card.appendChild(guide);
    if (progress.current_step === "details" && fallback) {
      text(card, "p", "cc-tour-note", "There isn’t a mapped event in this selection. Choose a sample event to keep going.");
      card.appendChild(btn("Use a sample event", "cc-button cc-button-primary", useSample));
    }
    if (progress.current_step === "route" && routeError) {
      text(card, "p", "cc-tour-note", "That event has no walkable route in this sample. Try another mapped event.");
      card.appendChild(btn("Use a sample event", "cc-button", useAlternative));
    }
    if (progress.current_step === "save" && showingMine) {
      text(card, "p", "cc-tour-note", "Your saved event is here. Return to its details when you’re ready.");
      card.appendChild(btn("Back to event", "cc-button", returnToEvent));
    } else if (progress.current_step === "save" && stepDone) {
      card.appendChild(btn("Show My Events", "cc-button", showMine));
    }
    const actions = document.createElement("div"); actions.className = "cc-tour-actions";
    const back = btn("Back", "cc-text-button", goBack); back.disabled = index() === 0;
    actions.append(back, btn("Skip step", "cc-text-button", skipStep), btn("Skip tour", "cc-text-button", skipTour));
    card.appendChild(actions);
    const next = btn(progress.current_step === "route" ? "Finish" : "Continue", "cc-button cc-button-primary cc-tour-next", continueTour);
    next.disabled = !stepDone || showingMine || fallback || routeError;
    card.appendChild(next);
    if (progress.current_step === "details" && selectedId) {
      const item = bridge.getEventSummary(selectedId);
      if (item) text(card, "p", "cc-tour-event", item.title);
    }
    layer.hidden = false;
  }
  function placeCard(scrollTarget) {
    if (!active) return;
    const app = document.getElementById("app"), layer = document.getElementById("ccTourLayer"), card = document.getElementById("ccTourCard");
    if (!app || !layer || !card) return;
    let pointer = layer.querySelector(".cc-tour-tail");
    if (!pointer) {
      pointer = document.createElement("span");
      pointer.className = "cc-tour-tail";
      pointer.setAttribute("aria-hidden", "true");
      layer.appendChild(pointer);
    }
    const target = document.querySelector(selector());
    if (highlighted && highlighted !== target) highlighted.classList.remove("cc-tour-highlight");
    highlighted = target;
    if (target) {
      target.classList.add("cc-tour-highlight");
      if (scrollTarget) target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    }
    const a = app.getBoundingClientRect(), t = target && target.getBoundingClientRect();
    const width = Math.max(250, Math.min(340, a.width - 24));
    card.style.width = width + "px";
    const h = card.getBoundingClientRect().height;
    const nav = app.querySelector(".tabs"), navTop = nav && !nav.hidden ? nav.getBoundingClientRect().top - a.top : a.height;
    const bottomLimit = Math.max(120, navTop - 12);
    let x = a.width - width - 12, y = Math.max(12, bottomLimit - h), tail = "none", targetX = x + width / 2;
    if (t) {
      x = Math.max(12, Math.min(a.width - width - 12, t.left - a.left + t.width / 2 - width / 2));
      const relTop = t.top - a.top, relBottom = t.bottom - a.top;
      targetX = t.left - a.left + t.width / 2;
      if (relTop > h + 20) { y = relTop - h - 14; tail = "bottom"; }
      else { y = relBottom + 14; tail = "top"; }
      if (y + h > bottomLimit) { y = Math.max(12, relTop - h - 14); tail = "bottom"; }
      y = Math.max(12, Math.min(bottomLimit - h, y));
    }
    card.dataset.tail = tail;
    const tailX = Math.max(18, Math.min(width - 30, targetX - x));
    card.style.setProperty("--cc-tour-tail-x", tailX + "px");
    pointer.dataset.direction = tail;
    pointer.hidden = tail === "none";
    pointer.style.left = (x + tailX - 8) + "px";
    pointer.style.top = (tail === "top" ? y - 8 : y + h - 8) + "px";
    card.style.left = x + "px"; card.style.top = y + "px"; layer.hidden = false;
  }
  function useSample() {
    const item = bridge.getSampleEvent(); if (!item) return;
    selectedId = item.id; fallback = false; progress.selected_tutorial_event_id = item.id;
    bridge.selectSampleEvent(item.id); persist(); drawCard(); placeCard(true);
  }
  function useAlternative() {
    const item = bridge.getAlternativeSample(selectedId);
    if (!item) { routeError = false; drawCard(); return; }
    selectedId = item.id; progress.selected_tutorial_event_id = item.id; routeError = false; stepDone = false;
    bridge.selectSampleEvent(item.id); bridge.openEvent(item.id); persist(); drawCard(); placeCard(true);
  }
  function continueTour() {
    if (!stepDone || showingMine) return;
    if (progress.current_step === "route") { endTour("completed"); return; }
    if (progress.current_step === "filter") {
      const item = bridge.findCurrentTourEvent();
      selectedId = item ? item.id : null; fallback = !item;
      progress.selected_tutorial_event_id = selectedId;
      if (item) bridge.centerEvent(item.id);
      enter("details", false); return;
    }
    if (progress.current_step === "details") { enter("save", false); return; }
    if (progress.current_step === "save") enter("route", false);
  }
  function goBack() { if (index() > 0) enter(STEPS[index() - 1], false); }
  function skipStep() {
    if (progress.skipped_steps.indexOf(progress.current_step) < 0) progress.skipped_steps.push(progress.current_step);
    if (index() >= STEPS.length - 1) endTour("skipped"); else enter(STEPS[index() + 1], false);
  }
  function skipTour() { progress.tour_status = "skipped"; persist(); endTour("skipped"); }
  function showMine() { showingMine = true; bridge.showMyEvents(); drawCard(); placeCard(true); }
  function returnToEvent() { showingMine = false; bridge.openEvent(selectedId); drawCard(); placeCard(true); }
  function endTour(result) {
    if (!replay) {
      progress.tour_status = result === "completed" ? "completed" : "skipped";
      if (result === "completed") progress.first_completed_at = progress.first_completed_at || new Date().toISOString();
      persist();
    }
    active = false;
    if (highlighted) highlighted.classList.remove("cc-tour-highlight");
    highlighted = null;
    const layer = document.getElementById("ccTourLayer"); if (layer) layer.hidden = true;
    if (snapshot) bridge.restoreUIState(snapshot);
    snapshot = null; replay = false;
    if (focusReturn && focusReturn.isConnected) focusReturn.focus({ preventScroll: true });
    focusReturn = null;
    if (result === "completed") announce("You’re ready. Let’s find your next little discovery.");
  }
  function categoryChanged() {
    if (!active || progress.current_step !== "filter") return;
    stepDone = true; persist(); drawCard(); placeCard(true);
  }
  function detailOpened(event) {
    if (!active || progress.current_step !== "details" || !selectedId || !event.detail || event.detail.eventId !== selectedId) return;
    stepDone = true; persist(); drawCard(); placeCard(false);
  }
  function eventSaved(event) {
    if (!active || progress.current_step !== "save" || !selectedId || !event.detail || event.detail.eventId !== selectedId) return;
    stepDone = true; showingMine = false; persist(); drawCard(); placeCard(false);
  }
  function routeAttempt(event) {
    if (!active || progress.current_step !== "route" || !selectedId || !event.detail || event.detail.eventId !== selectedId) return;
    window.setTimeout(function () {
      if (active && progress.current_step === "route" && selectedId === event.detail.eventId && !bridge.isRouteVisible(selectedId)) {
        routeError = true; drawCard(); placeCard(false);
      }
    }, 350);
  }
  function routeVisible(event) {
    if (!active || progress.current_step !== "route" || !selectedId || !event.detail || event.detail.eventId !== selectedId) return;
    stepDone = true; routeError = false; persist(); drawCard(); placeCard(false);
  }
  function onRender() {
    if (!active) return;
    if (progress.current_step === "save" && selectedId && bridge.isEventSaved(selectedId)) stepDone = true;
    if (progress.current_step === "route" && selectedId && bridge.isRouteVisible(selectedId)) stepDone = true;
    if (showingMine && bridge.getUIState().tab !== "mine") showingMine = false;
    drawCard(); placeCard(false);
  }
  function installListeners() {
    if (listeners) return; listeners = true;
    window.addEventListener("cc:category-change", categoryChanged);
    window.addEventListener("cc:detail-open", detailOpened);
    window.addEventListener("cc:event-saved", eventSaved);
    window.addEventListener("cc:route-attempt", routeAttempt);
    window.addEventListener("cc:route-visible", routeVisible);
    window.addEventListener("cc:render", onRender);
    resizeHandler = function () { placeCard(false); };
    window.addEventListener("resize", resizeHandler);
    document.addEventListener("visibilitychange", syncMascotMotion);
    motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (motionPreference.addEventListener) motionPreference.addEventListener("change", syncMascotMotion);
    else if (motionPreference.addListener) motionPreference.addListener(syncMascotMotion);
  }
  function removeListeners() {
    if (!listeners) return;
    listeners = false;
    window.removeEventListener("cc:category-change", categoryChanged);
    window.removeEventListener("cc:detail-open", detailOpened);
    window.removeEventListener("cc:event-saved", eventSaved);
    window.removeEventListener("cc:route-attempt", routeAttempt);
    window.removeEventListener("cc:route-visible", routeVisible);
    window.removeEventListener("cc:render", onRender);
    if (resizeHandler) window.removeEventListener("resize", resizeHandler);
    resizeHandler = null;
    document.removeEventListener("visibilitychange", syncMascotMotion);
    if (motionPreference && motionPreference.removeEventListener) motionPreference.removeEventListener("change", syncMascotMotion);
    else if (motionPreference && motionPreference.removeListener) motionPreference.removeListener(syncMascotMotion);
    motionPreference = null;
  }
  function suspend() {
    if (active) persist();
    active = false;
    if (highlighted) highlighted.classList.remove("cc-tour-highlight");
    highlighted = null;
    const layer = document.getElementById("ccTourLayer"); if (layer) layer.hidden = true;
    snapshot = null; replay = false; focusReturn = null;
    removeListeners();
  }
  function stopForLogout() {
    active = false;
    if (highlighted) highlighted.classList.remove("cc-tour-highlight");
    highlighted = null;
    const layer = document.getElementById("ccTourLayer"); if (layer) layer.hidden = true;
    snapshot = null; replay = false; focusReturn = null;
    removeListeners();
  }
  function syncMascotMotion() {
    const source = document.querySelector(".cc-intro-mascot source");
    if (!source) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    source.media = document.hidden || reduce ? "not all" : "(prefers-reduced-motion: no-preference)";
  }
  function showGuestChoice(guest) {
    A().showModal(
      '<p class="cc-modal-copy">This device has guest tutorial progress. Bring that progress into your account, or start fresh.</p>' +
      '<div class="cc-modal-actions cc-modal-actions-stack"><button class="cc-button cc-button-primary" data-continue type="button">Continue with guest progress</button><button class="cc-button" data-fresh type="button">Start fresh</button></div>',
      { title: "Continue your tour?", onEscape: function () { A().closeModal(); } }
    );
    const root = document.getElementById("ccModalRoot");
    root.querySelector("[data-continue]").onclick = async function () {
      progress = normalize(guest); selectedId = progress.selected_tutorial_event_id;
      try {
        await A().saveOnboarding(serverData()); A().closeModal({ silent: true });
        if (progress.tour_status === "in_progress") beginTour(progress.current_step, false);
        else if (progress.tour_status === "not_started") showIntro(progress.intro_screen || 1);
      } catch (_) { text(root.querySelector(".cc-dialog-body"), "p", "cc-form-error", "Couldn't save this progress. Retry your account connection and try again."); }
    };
    root.querySelector("[data-fresh]").onclick = function () {
      A().closeModal({ silent: true }); progress = emptyProgress(); selectedId = null; showIntro(1);
    };
  }
  async function start() {
    installListeners();
    if (!bridge || !A() || A().getStatus() === "loading" || bridge.getUIState().tab !== "map") return;
    if (A().isAuthenticated()) {
      let server; try { server = serverProgressToUI(await A().getOnboarding()); } catch (_) { return; }
      progress = server; selectedId = progress.selected_tutorial_event_id;
      if (progress.tour_status === "in_progress") beginTour(progress.current_step, false);
      else if (progress.tour_status !== "completed" && progress.tour_status !== "skipped") {
        const guest = readGuest();
        if (guestProgressExists(guest)) showGuestChoice(guest);
        else showIntro(progress.intro_seen ? 3 : progress.intro_screen);
      }
      return;
    }
    if (A().getStatus() === "error") return;
    progress = readGuest(); selectedId = progress.selected_tutorial_event_id;
    if (progress.tour_status === "in_progress") beginTour(progress.current_step, false);
    else if (progress.tour_status !== "completed" && progress.tour_status !== "skipped") showIntro(progress.intro_screen);
  }
  async function onAccountLogin(user, options) {
    options = options || {};
    let server; try { server = serverProgressToUI(await A().getOnboarding()); } catch (_) { return; }
    if (options.defer) { progress = server; selectedId = progress.selected_tutorial_event_id; return; }
    if (server.tour_status === "in_progress") {
      progress = server; selectedId = progress.selected_tutorial_event_id; beginTour(progress.current_step, false); return;
    }
    if (server.tour_status === "completed" || server.tour_status === "skipped") { progress = server; return; }
    const guest = readGuest();
    if (guestProgressExists(guest)) { showGuestChoice(guest); return; }
    if (options.fromInvitation) {
      progress = server; progress.intro_seen = true; progress.tour_status = "in_progress";
      progress.current_step = "filter"; selectedId = null; persist(); beginTour("filter", false); return;
    }
    progress = server; showIntro(progress.intro_seen ? 3 : introScreenForAccount(user.id));
  }
  function replayTour() {
    installListeners();
    if (A().getStatus() === "loading") { A().ready().then(replayTour); return; }
    if (A().isAuthenticated()) {
      A().getOnboarding().then(function (data) {
        progress = serverProgressToUI(data); selectedId = null; beginTour("filter", true);
      }).catch(function () { announce("Couldn't load your tour progress. Retry your account connection and try again."); });
    } else {
      progress = readGuest(); selectedId = null; beginTour("filter", true);
    }
  }
  function continueAsGuest() { finishIntro(); }
  function init(uiBridge) { bridge = uiBridge; installListeners(); }
  window.CampusCornersOnboarding = {
    init: init,
    start: start,
    isActive: function () { return active; },
    onAccountLogin: onAccountLogin,
    continueAsGuest: continueAsGuest,
    replay: replayTour,
    onRender: onRender,
    suspend: suspend,
    stopForLogout: stopForLogout
  };
})();
