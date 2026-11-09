// Home page account entry and opening animation.
(function () {
  var account = document.getElementById("siteAccount");
  var accounts = window.CampusCornersAccount;
  if (account && accounts) {
    function renderAccountEntry() {
      var status = accounts.getStatus();
      var user = accounts.getUser();
      account.classList.remove("is-authenticated", "is-error");
      if (status === "authenticated" && user) {
        account.classList.add("is-authenticated");
        account.setAttribute("aria-label", "Account for " + user.nickname);
        account.replaceChildren();
        var avatar = document.createElement("span");
        avatar.className = "site-account-avatar" + (user.is_verified_ucla ? " is-ucla-verified" : "");
        var image = document.createElement("img");
        image.src = accounts.profileIconUrl(user.profile_icon);
        image.alt = "";
        avatar.appendChild(image);
        if (user.is_verified_ucla) {
          var star = document.createElement("span");
          star.className = "site-account-star";
          star.setAttribute("aria-hidden", "true");
          star.textContent = "★";
          avatar.appendChild(star);
        }
        var nickname = document.createElement("span");
        nickname.className = "site-account-name";
        nickname.textContent = user.nickname;
        account.append(avatar, nickname);
      } else if (status === "error") {
        account.classList.add("is-error");
        account.setAttribute("aria-label", "Retry account connection");
        account.replaceChildren();
        var retry = document.createElement("span");
        retry.className = "site-account-retry";
        retry.textContent = "Retry";
        account.appendChild(retry);
      } else if (status === "loading") {
        account.setAttribute("aria-label", "Checking your account");
        account.replaceChildren();
        var pending = document.createElement("span");
        pending.className = "site-account-pending";
        pending.setAttribute("aria-hidden", "true");
        account.appendChild(pending);
      } else {
        account.setAttribute("aria-label", "Create or access your account");
        account.replaceChildren();
        var avatar = document.createElement("span");
        avatar.className = "site-account-avatar";
        var image = document.createElement("img");
        image.src = "app/profile-guest.svg";
        image.alt = "";
        avatar.appendChild(image);
        account.appendChild(avatar);
      }
    }
    var unsubscribe = accounts.subscribe(renderAccountEntry);
    window.addEventListener("pagehide", unsubscribe, { once: true });
    accounts.init(null);
  }
  var home = document.getElementById("home");
  if (!home || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  try {
    if (sessionStorage.getItem("campus-intro-played")) return;
    sessionStorage.setItem("campus-intro-played", "true");
  } catch (e) {}
  home.classList.add("is-opening");
  setTimeout(function () { home.classList.remove("is-opening"); }, 4200);
})();
