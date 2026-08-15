// Mintique — shared front-end behaviors
document.addEventListener("DOMContentLoaded", () => {

  /* ---------------- Theme toggle ---------------- */
  const themeToggle = document.getElementById("themeToggle");
  const root = document.documentElement;
  const applyTheme = (theme) => {
    if (theme === "light") root.setAttribute("data-theme", "light");
    else root.removeAttribute("data-theme");
    try { localStorage.setItem("mintique-theme", theme); } catch (e) {}
  };
  themeToggle?.addEventListener("click", () => {
    const isLight = root.getAttribute("data-theme") === "light";
    applyTheme(isLight ? "dark" : "light");
  });

  /* ---------------- Navbar scroll effect ---------------- */
  const navbar = document.getElementById("siteNavbar");
  const onScroll = () => {
    if (!navbar) return;
    if (window.scrollY > 12) navbar.classList.add("scrolled");
    else navbar.classList.remove("scrolled");
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  /* ---------------- Mobile nav toggle (with scrim + staggered links) ---------------- */
  const burger = document.getElementById("navBurger");
  const links = document.getElementById("navLinks");
  const scrim = document.getElementById("navScrim");
  const linkItems = links ? Array.from(links.querySelectorAll("a")) : [];
  linkItems.forEach((a, i) => a.style.setProperty("--i", i));

  const closeMobileNav = () => {
    burger?.classList.remove("open");
    burger?.setAttribute("aria-expanded", "false");
    links?.classList.remove("open-mobile");
    scrim?.classList.remove("show");
    document.body.style.overflow = "";
  };
  const openMobileNav = () => {
    burger?.classList.add("open");
    burger?.setAttribute("aria-expanded", "true");
    links?.classList.add("open-mobile");
    scrim?.classList.add("show");
    document.body.style.overflow = "hidden";
  };
  if (burger && links) {
    burger.addEventListener("click", () => {
      const isOpen = links.classList.contains("open-mobile");
      isOpen ? closeMobileNav() : openMobileNav();
    });
    scrim?.addEventListener("click", closeMobileNav);
    linkItems.forEach((a) => a.addEventListener("click", closeMobileNav));
    window.addEventListener("resize", () => { if (window.innerWidth > 980) closeMobileNav(); });
  }

  /* ---------------- Scroll-reveal animations ---------------- */
  const revealSelectors = [
    ".section-head", ".nft-card", ".feature-card", ".stat-card", ".chart-card",
    ".value-card", ".timeline-item", ".contact-info-card", ".auth-card",
    ".newsletter", ".empty-state", ".price-box", ".detail-img", ".detail-info"
  ];
  const revealEls = document.querySelectorAll(revealSelectors.join(","));
  if ("IntersectionObserver" in window && revealEls.length) {
    revealEls.forEach((el, i) => {
      el.classList.add("reveal", "reveal-stagger");
      el.style.setProperty("--stagger", i % 6);
    });
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach((el) => io.observe(el));
  } else {
    revealEls.forEach((el) => el.classList.add("in-view"));
  }

  /* ---------------- 3D tilt on NFT / featured cards ---------------- */
  const tiltEls = document.querySelectorAll(".nft-card, .float-card");
  tiltEls.forEach((el) => {
    el.style.transformStyle = "preserve-3d";
    el.addEventListener("pointermove", (e) => {
      const rect = el.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - 0.5;
      const py = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `perspective(800px) rotateX(${(-py * 7).toFixed(2)}deg) rotateY(${(px * 9).toFixed(2)}deg) translateY(-8px) scale(1.02)`;
    });
    el.addEventListener("pointerleave", () => {
      el.style.transform = "";
    });
  });

  /* ---------------- Count-up animation for numeric stats ---------------- */
  document.querySelectorAll(".stat b, .stat-card .value").forEach((el) => {
    const raw = el.textContent.trim();
    if (!/^\d+$/.test(raw)) return; // only animate pure numbers, leave "25K+" style text alone
    const target = parseInt(raw, 10);
    if (!target) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        io.unobserve(el);
        const start = performance.now();
        const dur = 1200;
        const tick = (now) => {
          const p = Math.min(1, (now - start) / dur);
          const eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased).toLocaleString();
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.4 });
    io.observe(el);
  });

  /* ---------------- Cursor-tracking spotlight on cards ---------------- */
  const spotlightEls = document.querySelectorAll(
    ".nft-card, .value-card, .chart-card, .card, .contact-info-card, .feature-card, .stat-card"
  );
  spotlightEls.forEach((el) => {
    el.addEventListener("pointermove", (e) => {
      const rect = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
      el.style.setProperty("--my", `${e.clientY - rect.top}px`);
    });
  });

  /* ---------------- Button ripple effect ---------------- */
  document.querySelectorAll(".btn").forEach((btn) => {
    btn.addEventListener("click", function (e) {
      const rect = this.getBoundingClientRect();
      const ripple = document.createElement("span");
      const size = Math.max(rect.width, rect.height);
      ripple.className = "ripple";
      ripple.style.width = ripple.style.height = `${size}px`;
      ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
      ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 650);
    });
  });

  /* ---------------- Auto-dismiss toasts after 5s ---------------- */
  document.querySelectorAll(".toast").forEach((toast, i) => {
    setTimeout(() => {
      toast.classList.add("leaving");
      setTimeout(() => toast.remove(), 300);
    }, 5500 + i * 300);
  });

  /* ---------------- Password visibility toggles ---------------- */
  document.querySelectorAll(".password-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      input.type = input.type === "password" ? "text" : "password";
      btn.textContent = input.type === "password" ? "👁" : "🙈";
    });
  });

  /* ---------------- Drag & drop / image preview for the mint form ---------------- */
  const dropzone = document.querySelector(".dropzone");
  if (dropzone) {
    const fileInput = dropzone.querySelector("input[type=file]");
    const previewImg = dropzone.querySelector(".preview-img");
    const dzIcon = dropzone.querySelector(".dz-icon");
    const dzText = dropzone.querySelector(".dz-text");

    const showPreview = (file) => {
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        if (previewImg) {
          previewImg.src = e.target.result;
          previewImg.style.display = "block";
        }
        if (dzIcon) dzIcon.style.display = "none";
        if (dzText) dzText.textContent = file.name;
      };
      reader.readAsDataURL(file);
    };

    fileInput?.addEventListener("change", () => showPreview(fileInput.files[0]));

    ["dragenter", "dragover"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); })
    );
    ["dragleave", "drop"].forEach((evt) =>
      dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); })
    );
    dropzone.addEventListener("drop", (e) => {
      const file = e.dataTransfer.files[0];
      if (file && fileInput) {
        fileInput.files = e.dataTransfer.files;
        showPreview(file);
      }
    });
  }

  /* ---------------- Generic client-side "required" validation with shake + inline error ---------------- */
  document.querySelectorAll("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      let valid = true;
      form.querySelectorAll("[required]").forEach((field) => {
        const wrap = field.closest(".field") || field.parentElement;
        if (!field.value.trim()) {
          valid = false;
          wrap?.classList.add("field-invalid", "shake");
          field.addEventListener("input", () => {
            wrap?.classList.remove("field-invalid");
          }, { once: true });
          setTimeout(() => wrap?.classList.remove("shake"), 400);
        } else {
          wrap?.classList.remove("field-invalid");
        }
      });
      if (!valid) e.preventDefault();
    });
  });
});

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return null;
}

function showToast(message, type = "info") {
  const root = document.getElementById("toastRoot");
  if (!root) return;
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span>${message}</span><button class="toast-close" onclick="this.parentElement.remove()">&times;</button>`;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 300);
  }, 5500);
}
