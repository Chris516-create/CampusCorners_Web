// Home page: today's date on the button, and the opening animation once per visit.
(function () {
  var label = document.getElementById("today-label");
  if (label) {
    label.textContent = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
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
