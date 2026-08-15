document.addEventListener("DOMContentLoaded", () => {
  // Keep the sticky sidebar/topbar flush under the shared site header,
  // whatever its real rendered height is at the current breakpoint.
  const syncHeaderHeight = () => {
    const header = document.getElementById("siteNavbar");
    if (!header) return;
    document.documentElement.style.setProperty("--dash-header-h", header.offsetHeight + "px");
  };
  syncHeaderHeight();
  window.addEventListener("resize", syncHeaderHeight);

  const shell = document.getElementById("dashAppShell");
  if (!shell) return; // anonymous fallback page — nothing else to wire up

  const burger = document.getElementById("dashBurger");
  const scrim = document.getElementById("dashScrim");
  const collapseBtn = document.getElementById("sidebarCollapseBtn");

  const openMobile = () => { shell.classList.add("mobile-open"); scrim.classList.add("show"); };
  const closeMobile = () => { shell.classList.remove("mobile-open"); scrim.classList.remove("show"); };

  burger?.addEventListener("click", () => {
    shell.classList.contains("mobile-open") ? closeMobile() : openMobile();
  });
  scrim?.addEventListener("click", closeMobile);

  // Close the off-canvas sidebar automatically on nav (better small-screen UX)
  shell.querySelectorAll(".dash-nav-item").forEach((link) => {
    link.addEventListener("click", closeMobile);
  });

  // Desktop collapse — remembered across page loads.
  const COLLAPSE_KEY = "mintique-sidebar-collapsed";
  try {
    if (localStorage.getItem(COLLAPSE_KEY) === "1") shell.classList.add("collapsed");
  } catch (e) { /* localStorage unavailable — ignore */ }

  collapseBtn?.addEventListener("click", () => {
    shell.classList.toggle("collapsed");
    try {
      localStorage.setItem(COLLAPSE_KEY, shell.classList.contains("collapsed") ? "1" : "0");
    } catch (e) { /* ignore */ }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMobile();
  });
});
