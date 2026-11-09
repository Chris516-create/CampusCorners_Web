(function () {
  const state = {
    status: "loading", user: null, savedIds: new Set(), csrfToken: "", error: "", readyPromise: null,
    profileDraft: null, profileSaving: false, accountNotice: "", logoutPending: false, logoutError: ""
  };
  const subscribers = new Set();
  let bridge = null;
  let modalState = null;
  let pending = false;
  let formMode = "login";

  class ApiError extends Error {
    constructor(status, payload) {
      super(payload && payload.error ? payload.error.message : "Could not reach the account service.");
      this.name = "ApiError";
      this.status = status;
      this.payload = payload || {};
    }
  }

  function notify() {
    if (bridge && typeof bridge.redraw === "function") bridge.redraw();
    const snapshot = { status: state.status, user: state.user, error: state.error };
    subscribers.forEach(function (listener) { try { listener(snapshot); } catch (_) {} });
  }

  function closeAccountState(navigateToMap) {
    const hadAccount = state.status === "authenticated" || !!state.user;
    if (hadAccount && window.CampusCornersOnboarding && typeof window.CampusCornersOnboarding.stopForLogout === "function") {
      window.CampusCornersOnboarding.stopForLogout();
    }
    state.status = "guest";
    state.user = null;
    state.savedIds = new Set();
    state.error = "";
    state.profileDraft = null;
    state.profileSaving = false;
    state.accountNotice = "";
    state.logoutPending = false;
    state.logoutError = "";
    if (hadAccount && bridge && typeof bridge.restoreGuestData === "function") bridge.restoreGuestData();
    if (hadAccount && navigateToMap && bridge && typeof bridge.afterLogout === "function") {
      bridge.afterLogout();
    }
    notify();
  }

  async function csrfToken() {
    if (state.csrfToken) return state.csrfToken;
    const response = await fetch("/api/csrf", {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    const payload = await response.json();
    if (!response.ok || !payload.csrfToken) throw new ApiError(response.status, payload);
    state.csrfToken = payload.csrfToken;
    return state.csrfToken;
  }

  async function apiRequest(path, options, retried) {
    options = options || {};
    const method = (options.method || "GET").toUpperCase();
    const headers = Object.assign({ Accept: "application/json" }, options.headers || {});
    if (method !== "GET" && method !== "HEAD") {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = await csrfToken();
    }
    let response;
    try {
      response = await fetch(path, {
        method: method,
        credentials: "same-origin",
        cache: "no-store",
        headers: headers,
        body: options.body
      });
    } catch (_) {
      throw new ApiError(0, { error: { message: "The account service is unavailable. Try again." } });
    }
    let payload = {};
    if (response.status !== 204) {
      try {
        payload = await response.json();
      } catch (_) {
        payload = {};
      }
    }
    if (payload.csrfToken) state.csrfToken = payload.csrfToken;
    if (response.status === 403 && payload.error && payload.error.code === "csrf_failed" && !retried) {
      state.csrfToken = "";
      await csrfToken();
      return apiRequest(path, options, true);
    }
    if (response.status === 401 && (path === "/api/auth/me" || path.indexOf("/api/me/") === 0)) {
      closeAccountState(false);
    }
    if (!response.ok) throw new ApiError(response.status, payload);
    return payload;
  }

  function setAccount(user, savedIds) {
    if (state.user && state.user.id !== user.id) state.profileDraft = null;
    state.status = "authenticated";
    state.user = user;
    state.savedIds = new Set(savedIds || []);
    state.error = "";
    state.logoutError = "";
    if (bridge && typeof bridge.applyAccountData === "function") {
      bridge.applyAccountData(state.user, Array.from(state.savedIds));
    }
    notify();
  }

  async function restoreSession() {
    state.status = "loading";
    state.error = "";
    notify();
    try {
      await csrfToken();
      const response = await apiRequest("/api/auth/me", { method: "GET" });
      setAccount(response.user, response.saved_event_ids || []);
    } catch (error) {
      if (error.status === 401) {
        if (state.status !== "guest") closeAccountState();
        return state.status;
      }
      state.status = "error";
      state.error = "We couldn't check your account. Retry when you're ready.";
      notify();
    }
    return state.status;
  }

  function ready() {
    return state.readyPromise || Promise.resolve(state.status);
  }

  function isAuthenticated() {
    return state.status === "authenticated" && !!state.user;
  }

  function getUser() {
    return state.user;
  }

  function getStatus() {
    return state.status;
  }

  function subscribe(listener) {
    if (typeof listener !== "function") return function () {};
    subscribers.add(listener);
    listener({ status: state.status, user: state.user, error: state.error });
    return function () { subscribers.delete(listener); };
  }

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function button(text, className, action) {
    const el = node("button", className || "cc-button", text);
    el.type = "button";
    el.addEventListener("click", action);
    return el;
  }

  function nicknameIsValid(value) {
    const nickname = String(value || "").trim();
    const chars = Array.from(nickname);
    const control = /[\p{Cc}\p{Cs}\p{Zl}\p{Zp}]/u;
    const format = /\p{Cf}/u;
    return chars.length >= 1 && chars.length <= 30 && !chars.some(function (char) {
      return control.test(char) || (format.test(char) && char !== "\u200c" && char !== "\u200d");
    });
  }

  async function saveProfile(draft) {
    if (!isAuthenticated() || state.profileSaving || !nicknameIsValid(draft.nickname) || !PROFILE_ICON_ASSETS[draft.profile_icon]) return;
    const userId = state.user.id;
    state.profileDraft = { userId: userId, nickname: draft.nickname, profile_icon: draft.profile_icon };
    state.profileSaving = true;
    state.accountNotice = "";
    notify();
    try {
      const result = await apiRequest("/api/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ nickname: draft.nickname.trim(), profile_icon: draft.profile_icon })
      });
      if (!isAuthenticated() || state.user.id !== userId) return;
      state.user = result.user;
      state.profileDraft = null;
      state.accountNotice = "Saved";
    } catch (error) {
      if (state.status !== "guest") {
        const fields = error.payload && error.payload.error && error.payload.error.fields;
        const firstError = fields && (fields.nickname || fields.profile_icon);
        state.accountNotice = firstError ? firstError.join(" ") : "Couldn't save your profile. Try again.";
      }
    } finally {
      state.profileSaving = false;
      notify();
    }
  }

  function renderProfileAvatar(parent, user, sizeClass) {
    const avatar = node("span", "cc-profile-avatar " + (sizeClass || "") + (user.is_verified_ucla ? " is-ucla-verified" : ""));
    const image = node("img");
    image.src = profileIconUrl(user.profile_icon);
    image.alt = "";
    avatar.appendChild(image);
    if (user.is_verified_ucla) {
      const star = node("span", "cc-profile-star", "★");
      star.setAttribute("aria-hidden", "true");
      avatar.appendChild(star);
    }
    parent.appendChild(avatar);
  }

  const PROFILE_ICON_LABELS = { sparkle: "Star", sparko: "Sparko", flower: "Flower", heart: "Heart" };
  const PROFILE_ICON_ASSETS = {
    sparkle: "app/profile-sparkle.svg",
    sparko: "app/sparko-idle.png",
    flower: "app/profile-flower.svg",
    heart: "app/profile-heart.svg"
  };
  function profileIconUrl(profileIcon) {
    return PROFILE_ICON_ASSETS[profileIcon] || PROFILE_ICON_ASSETS.sparko;
  }

  function navigateTo(tab) {
    if (bridge && typeof bridge.navigateTab === "function") bridge.navigateTab(tab);
  }

  function renderAccount(container) {
    if (!container) return;
    container.replaceChildren();
    const section = node("section", "cc-account-screen");
    const header = node("header", "cc-account-header");
    header.appendChild(node("h3", "", isAuthenticated() ? "Your account" : "Account"));
    section.appendChild(header);

    const card = node("div", "cc-profile-card");
    if (state.status === "loading") {
      card.appendChild(node("p", "cc-account-note", "Checking your account…"));
    } else if (state.status === "error") {
      card.appendChild(node("p", "cc-account-note", state.error));
      card.appendChild(button("Retry", "cc-button cc-button-primary", function () {
        state.readyPromise = restoreSession();
      }));
    } else if (!isAuthenticated()) {
      const defaultAvatar = node("div", "cc-profile-identity cc-profile-guest");
      const guestAvatar = node("span", "cc-profile-avatar cc-profile-avatar-large");
      const guestImage = node("img");
      guestImage.src = "app/profile-guest.svg";
      guestImage.alt = "";
      guestAvatar.appendChild(guestImage);
      defaultAvatar.appendChild(guestAvatar);
      card.appendChild(defaultAvatar);
      card.appendChild(node("p", "cc-account-note", "Sign in to keep your favorites close, or explore as a guest."));
      const actions = node("div", "cc-account-actions");
      actions.appendChild(button("Create account", "cc-button cc-button-primary", function () { openAuthModal("register"); }));
      actions.appendChild(button("Log in", "cc-button", function () { openAuthModal("login"); }));
      actions.appendChild(button("Continue as guest", "cc-button cc-button-quiet", function () { navigateTo("map"); }));
      card.appendChild(actions);
    } else {
      const user = state.user;
      const profileHead = node("div", "cc-profile-identity");
      renderProfileAvatar(profileHead, user, "cc-profile-avatar-large");
      const identity = node("div", "cc-profile-identity-copy");
      identity.appendChild(node("h4", "cc-account-name", user.nickname));
      identity.appendChild(node("p", "cc-account-email", user.email));
      const statusText = user.is_verified_ucla ? "UCLA email verified" : (user.email_verified_at ? "Email verified" : "Email unverified");
      const statusChip = node("span", "cc-email-status" + (user.is_verified_ucla ? " is-ucla-verified" : ""), statusText);
      identity.appendChild(statusChip);
      profileHead.appendChild(identity);
      card.appendChild(profileHead);

      if (!state.profileDraft || state.profileDraft.userId !== user.id) {
        state.profileDraft = { userId: user.id, nickname: user.nickname, profile_icon: user.profile_icon || "sparko" };
      }
      const draft = state.profileDraft;
      const form = node("form", "cc-nickname-form");
      const label = node("label", "cc-field");
      label.appendChild(node("span", "", "Nickname"));
      const input = node("input");
      input.type = "text";
      input.name = "nickname";
      input.maxLength = 30;
      input.autocomplete = "nickname";
      input.value = draft.nickname;
      input.setAttribute("aria-label", "Nickname");
      label.appendChild(input);
      form.appendChild(label);
      const iconPicker = node("fieldset", "cc-profile-icon-picker");
      iconPicker.appendChild(node("legend", "", "Profile icon"));
      const iconOptions = node("div", "cc-profile-icon-options");
      Object.entries(PROFILE_ICON_ASSETS).forEach(function (entry) {
        const key = entry[0];
        const option = button("", "cc-profile-icon-option", function () {
          if (state.profileSaving) return;
          state.profileDraft = { userId: user.id, nickname: input.value, profile_icon: key };
          state.accountNotice = "";
          profileHead.querySelector("img").src = profileIconUrl(key);
          iconOptions.querySelectorAll(".cc-profile-icon-option").forEach(function (item) {
            item.setAttribute("aria-pressed", String(item.dataset.icon === key));
          });
          save.disabled = state.profileSaving || !profileChanged();
        });
        option.dataset.icon = key;
        option.setAttribute("aria-label", "Use " + PROFILE_ICON_LABELS[key] + " profile icon");
        option.setAttribute("aria-pressed", String(draft.profile_icon === key));
        const image = node("img");
        image.src = profileIconUrl(key);
        image.alt = "";
        option.append(image, node("span", "", PROFILE_ICON_LABELS[key]));
        iconOptions.appendChild(option);
      });
      iconPicker.appendChild(iconOptions);
      form.appendChild(iconPicker);
      const status = node("p", "cc-account-status", state.accountNotice || state.logoutError);
      status.id = "ccAccountStatus";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      form.appendChild(status);
      const actions = node("div", "cc-account-actions cc-profile-actions");
      const save = node("button", "cc-button cc-button-primary", state.profileSaving ? "Saving…" : "Save changes");
      save.type = "submit";
      const cancel = button("Cancel", "cc-button cc-button-quiet", function () {
        state.profileDraft = { userId: user.id, nickname: user.nickname, profile_icon: user.profile_icon || "sparko" };
        state.accountNotice = "";
        renderAccount(container);
      });
      cancel.disabled = state.profileSaving;
      actions.append(save, cancel);
      form.appendChild(actions);
      function profileChanged() {
        const current = state.profileDraft;
        return !!current && nicknameIsValid(current.nickname) && (
          current.nickname.trim() !== user.nickname || current.profile_icon !== (user.profile_icon || "sparko")
        );
      }
      input.addEventListener("input", function () {
        state.profileDraft = {
          userId: user.id,
          nickname: input.value,
          profile_icon: state.profileDraft.profile_icon
        };
        state.accountNotice = "";
        save.disabled = state.profileSaving || !profileChanged();
        cancel.disabled = state.profileSaving;
      });
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        saveProfile(state.profileDraft);
      });
      save.disabled = state.profileSaving || !profileChanged();
      card.appendChild(form);

      const footerActions = node("div", "cc-account-actions cc-account-footer-actions");
      footerActions.appendChild(button("Back to map", "cc-button", function () { navigateTo("map"); }));
      const logout = button(state.logoutPending ? "Logging out…" : "Log out & continue as guest", "cc-button cc-button-quiet", logoutUser);
      logout.disabled = state.logoutPending;
      footerActions.appendChild(logout);
      section.appendChild(card);
      section.appendChild(footerActions);
      container.appendChild(section);
      return;
    }
    section.appendChild(card);
    container.appendChild(section);
  }

  function showModal(content, options) {
    options = options || {};
    const root = document.getElementById("ccModalRoot");
    if (!root) return;
    if (modalState) closeModal({ silent: true, restore: false });
    const previousFocus = document.activeElement;
    root.innerHTML =
      '<div class="cc-modal-backdrop">' +
      '<section class="cc-modal" role="dialog" aria-modal="true" aria-labelledby="ccDialogTitle" tabindex="-1">' +
      '<button class="cc-modal-close" type="button" aria-label="Close">×</button>' +
      '<h2 id="ccDialogTitle"></h2><div class="cc-dialog-body"></div></section></div>';
    root.hidden = false;
    root.querySelector("#ccDialogTitle").textContent = options.title || "Campus Corners";
    root.querySelector(".cc-dialog-body").innerHTML = content;
    modalState = {
      previousFocus: previousFocus,
      onEscape: options.onEscape || null,
      onClose: options.onClose || null,
      keydown: null
    };
    root.querySelector(".cc-modal-close").addEventListener("click", function () {
      closeModal();
    });
    modalState.keydown = function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (modalState && modalState.onEscape) modalState.onEscape();
        else closeModal();
      } else if (event.key === "Tab") {
        trapFocus(event, root.querySelector(".cc-modal"));
      }
    };
    document.addEventListener("keydown", modalState.keydown);
    const focusable = root.querySelector("input,button,select,textarea,[href]");
    (focusable || root.querySelector(".cc-modal")).focus({ preventScroll: true });
  }

  function trapFocus(event, dialog) {
    if (!dialog) return;
    const elements = Array.from(dialog.querySelectorAll(
      'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex="0"]'
    )).filter(function (el) { return el.offsetParent !== null; });
    if (!elements.length) return;
    const first = elements[0];
    const last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function closeModal(options) {
    options = options || {};
    if (!modalState) return;
    const current = modalState;
    modalState = null;
    document.removeEventListener("keydown", current.keydown);
    const root = document.getElementById("ccModalRoot");
    if (root) {
      root.hidden = true;
      root.replaceChildren();
    }
    if (!options.silent && current.onClose) current.onClose();
    if (options.restore !== false && current.previousFocus && current.previousFocus.isConnected) {
      current.previousFocus.focus({ preventScroll: true });
    }
  }

  function openAuthModal(mode, options) {
    options = options || {};
    formMode = mode === "register" ? "register" : "login";
    const title = formMode === "register" ? "Create your account" : "Log in";
    const nicknameField = formMode === "register"
      ? '<label class="cc-field"><span>Nickname</span><input name="nickname" type="text" maxlength="60" autocomplete="nickname" required><small data-error-for="nickname"></small></label>'
      : "";
    const passwordAuto = formMode === "register" ? "new-password" : "current-password";
    const passwordLimits = formMode === "register" ? ' minlength="8" maxlength="128"' : "";
    const passwordHint = formMode === "register" ? '<small class="cc-field-hint">8–128 characters.</small>' : "";
    const submitText = formMode === "register" ? "Create account" : "Log in";
    const switchText = formMode === "register" ? "Already have an account? Log in" : "New here? Create an account";
    const html =
      '<form class="cc-auth-form" novalidate>' +
      '<div class="cc-auth-brand"><img src="app/sparko-idle.png" alt=""><span>Campus Corners</span></div>' +
      nicknameField +
      '<label class="cc-field"><span>Email</span><input name="email" type="email" maxlength="254" autocomplete="username" required><small data-error-for="email"></small></label>' +
      '<label class="cc-field"><span>Password</span><span class="cc-password-row"><input name="password" type="password" autocomplete="' + passwordAuto + '"' + passwordLimits + ' required><button type="button" class="cc-password-toggle" aria-pressed="false">Show</button></span>' + passwordHint + '<small data-error-for="password"></small></label>' +
      '<p class="cc-form-error" data-general-error role="alert"></p>' +
      '<button class="cc-button cc-button-primary cc-submit" type="submit">' + submitText + '</button>' +
      '<div class="cc-auth-footer"><button class="cc-text-button cc-switch" type="button">' + switchText + '</button>' +
      '<button class="cc-text-button cc-cancel" type="button">Cancel</button></div>' +
      '<button class="cc-text-button cc-continue-guest" type="button">Continue as guest</button>' +
      '</form>';
    showModal(html, {
      title: title,
      onEscape: function () { closeModal(); },
      onClose: options.onCancel || null
    });
    const root = document.getElementById("ccModalRoot");
    const form = root.querySelector(".cc-auth-form");
    const email = form.elements.email;
    const password = form.elements.password;
    const nickname = form.elements.nickname;
    const toggle = form.querySelector(".cc-password-toggle");
    const submit = form.querySelector(".cc-submit");
    if (options.email) email.value = options.email;
    toggle.addEventListener("click", function () {
      const showing = password.type === "text";
      password.type = showing ? "password" : "text";
      toggle.textContent = showing ? "Show" : "Hide";
      toggle.setAttribute("aria-pressed", String(!showing));
      password.focus({ preventScroll: true });
    });
    form.querySelector(".cc-switch").addEventListener("click", function () {
      const next = formMode === "register" ? "login" : "register";
      const emailValue = email.value;
      closeModal({ silent: true });
      openAuthModal(next, { email: emailValue, onCancel: options.onCancel, onGuestContinue: options.onGuestContinue, fromInvitation: options.fromInvitation });
    });
    form.querySelector(".cc-cancel").addEventListener("click", function () {
      closeModal();
    });
    form.querySelector(".cc-continue-guest").addEventListener("click", function () {
      closeModal({ silent: true });
      if (options.fromInvitation && window.CampusCornersOnboarding && window.CampusCornersOnboarding.continueAsGuest) {
        window.CampusCornersOnboarding.continueAsGuest();
      }
      else if (typeof options.onGuestContinue === "function") options.onGuestContinue();
      else if (bridge && typeof bridge.navigateTab === "function") bridge.navigateTab("map");
    });
    form.addEventListener("input", function (event) {
      const target = event.target;
      const error = form.querySelector('[data-error-for="' + target.name + '"]');
      if (error) error.textContent = "";
      target.removeAttribute("aria-invalid");
      form.querySelector("[data-general-error]").textContent = "";
    });
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (pending) return;
      pending = true;
      submit.disabled = true;
      submit.textContent = "Please wait…";
      form.querySelectorAll("[data-error-for]").forEach(function (el) { el.textContent = ""; });
      form.querySelector("[data-general-error]").textContent = "";
      const requestData = { email: email.value.trim(), password: password.value };
      if (formMode === "register") requestData.nickname = nickname.value.trim();
      try {
        const endpoint = formMode === "register" ? "/api/auth/register" : "/api/auth/login";
        const response = await apiRequest(endpoint, {
          method: "POST",
          body: JSON.stringify(requestData)
        });
        await finishAuthentication(response, options.fromInvitation);
      } catch (error) {
        password.value = "";
        const fields = error.payload && error.payload.error && error.payload.error.fields;
        if (fields) {
          Object.keys(fields).forEach(function (name) {
            const errorNode = form.querySelector('[data-error-for="' + name + '"]');
            const input = form.elements[name];
            if (errorNode) errorNode.textContent = Array.isArray(fields[name]) ? fields[name].join(" ") : String(fields[name]);
            if (input) input.setAttribute("aria-invalid", "true");
          });
        }
        form.querySelector("[data-general-error]").textContent = error.message;
      } finally {
        pending = false;
        if (submit.isConnected) {
          submit.disabled = false;
          submit.textContent = formMode === "register" ? "Create account" : "Log in";
        }
      }
    });
  }

  async function finishAuthentication(response, fromInvitation) {
    setAccount(response.user, response.saved_event_ids || []);
    closeModal({ silent: true });
    await offerGuestImport();
    if (window.CampusCornersOnboarding && typeof window.CampusCornersOnboarding.onAccountLogin === "function") {
      const currentTab = bridge && typeof bridge.getUIState === "function" ? bridge.getUIState().tab : "map";
      await window.CampusCornersOnboarding.onAccountLogin(state.user, {
        fromInvitation: !!fromInvitation,
        defer: currentTab === "account" || currentTab === "settings"
      });
    }
  }

  async function offerGuestImport() {
    if (!isAuthenticated() || !bridge || typeof bridge.getGuestSavedIds !== "function") return;
    const guestIds = bridge.getGuestSavedIds();
    if (!guestIds.length) return;
    const key = "cc:guest:import-offer:" + state.user.id;
    if (localStorage.getItem(key)) return;
    return new Promise(function (resolve) {
      let completed = false;
      function finish(skip) {
        if (completed) return;
        completed = true;
        localStorage.setItem(key, skip ? "skipped" : "imported");
        closeModal({ silent: true });
        resolve();
      }
      showModal(
      '<p class="cc-modal-copy">Bring your ' + guestIds.length + ' guest save' + (guestIds.length === 1 ? "" : "s") +
      ' into this account? Choose Skip to leave them private on this device.</p>' +
      '<div class="cc-modal-actions"><button class="cc-button cc-button-primary" type="button" data-import>Import saves</button>' +
      '<button class="cc-button" type="button" data-skip>Skip</button></div><p class="cc-form-error" data-import-error role="alert"></p>',
      {
        title: "Bring your saves?",
        onEscape: function () { finish(true); },
        onClose: function () { finish(true); }
      }
      );
      const root = document.getElementById("ccModalRoot");
      root.querySelector("[data-skip]").addEventListener("click", function () { finish(true); });
      root.querySelector("[data-import]").addEventListener("click", async function (event) {
        const action = event.currentTarget;
        action.disabled = true;
        try {
          const result = await apiRequest("/api/me/import-saves", {
            method: "POST",
            body: JSON.stringify({ event_ids: guestIds })
          });
          state.savedIds = new Set(Array.from(state.savedIds).concat(result.imported || []));
          if (bridge && typeof bridge.applyAccountData === "function") {
            bridge.applyAccountData(state.user, Array.from(state.savedIds));
          }
          finish(false);
        } catch (error) {
          action.disabled = false;
          root.querySelector("[data-import-error]").textContent = error.message;
        }
      });
    });
  }

  async function logoutUser() {
    if (state.logoutPending) return;
    state.logoutPending = true;
    state.logoutError = "";
    notify();
    try {
      await apiRequest("/api/auth/logout", { method: "POST" });
      closeAccountState(true);
    } catch (_) {
      state.logoutPending = false;
      state.logoutError = "Couldn't log out. Try again.";
      notify();
    }
  }

  async function saveEvent(eventId, shouldSave) {
    await ready();
    if (!isAuthenticated()) {
      if (state.status === "error") throw new ApiError(0, { error: { message: state.error } });
      return false;
    }
    const url = "/api/me/saved-events/" + encodeURIComponent(eventId);
    await apiRequest(url, { method: shouldSave ? "PUT" : "DELETE", body: shouldSave ? "{}" : undefined });
    if (shouldSave) state.savedIds.add(eventId);
    else state.savedIds.delete(eventId);
    return true;
  }

  async function getOnboarding() {
    await ready();
    if (!isAuthenticated()) return null;
    return apiRequest("/api/me/onboarding", { method: "GET" });
  }

  async function saveOnboarding(progress) {
    await ready();
    if (!isAuthenticated()) {
      if (state.status === "error") throw new ApiError(0, { error: { message: state.error } });
      return null;
    }
    return apiRequest("/api/me/onboarding", {
      method: "PUT",
      body: JSON.stringify(progress)
    });
  }

  function init(uiBridge) {
    if (uiBridge) bridge = uiBridge;
    if (!state.readyPromise) state.readyPromise = restoreSession();
    return ready();
  }

  window.CampusCornersAccount = {
    init: init,
    ready: ready,
    refresh: function () { state.readyPromise = restoreSession(); return state.readyPromise; },
    isAuthenticated: isAuthenticated,
    getUser: getUser,
    getStatus: getStatus,
    subscribe: subscribe,
    saveEvent: saveEvent,
    getOnboarding: getOnboarding,
    saveOnboarding: saveOnboarding,
    showModal: showModal,
    closeModal: closeModal,
    openAuthModal: openAuthModal,
    renderAccount: renderAccount,
    profileIconUrl: profileIconUrl
  };
})();
