/* ═══════════════════════════════════════════════════════════════════════════
   PROJECT DEMETRIOS — Shared JS
   ═══════════════════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  // ── Active nav link ───────────────────────────────────────────────────────
  const currentPage = window.location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".nav-links a").forEach(a => {
    const href = a.getAttribute("href");
    if (href === currentPage || (currentPage === "" && href === "index.html")) {
      a.classList.add("active");
    }
  });

  // ── Hamburger menu ────────────────────────────────────────────────────────
  const burger = document.querySelector(".hamburger");
  const navLinks = document.querySelector(".nav-links");
  if (burger && navLinks) {
    burger.addEventListener("click", () => {
      navLinks.classList.toggle("open");
      const isOpen = navLinks.classList.contains("open");
      burger.setAttribute("aria-expanded", isOpen);
      burger.querySelectorAll("span")[0].style.transform = isOpen ? "rotate(45deg) translate(5px, 4.5px)" : "";
      burger.querySelectorAll("span")[1].style.opacity  = isOpen ? "0" : "1";
      burger.querySelectorAll("span")[2].style.transform = isOpen ? "rotate(-45deg) translate(5px, -4.5px)" : "";
    });

    // Close on link click
    navLinks.querySelectorAll("a").forEach(a => {
      a.addEventListener("click", () => {
        navLinks.classList.remove("open");
        burger.querySelectorAll("span").forEach(s => { s.style.transform = ""; s.style.opacity = ""; });
      });
    });
  }

  // ── Scroll-reveal ─────────────────────────────────────────────────────────
  const revealEls = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e, i) => {
        if (e.isIntersecting) {
          const delay = e.target.dataset.delay || 0;
          setTimeout(() => e.target.classList.add("visible"), delay);
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    revealEls.forEach(el => io.observe(el));
  } else {
    revealEls.forEach(el => el.classList.add("visible"));
  }

  // ── Nav scroll effect ─────────────────────────────────────────────────────
  const nav = document.querySelector(".site-nav");
  if (nav) {
    window.addEventListener("scroll", () => {
      if (window.scrollY > 40) {
        nav.style.boxShadow = "0 4px 32px rgba(0,0,0,0.35)";
      } else {
        nav.style.boxShadow = "none";
      }
    }, { passive: true });
  }

})();
