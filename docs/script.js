(function () {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));
  const wechatModal = $('[data-modal="wechat"]');
  const lightboxModal = $('[data-modal="lightbox"]');
  const lightboxImage = $("[data-lightbox-image]");
  const toast = $(".toast");
  let toastTimer = null;

  function openModal(modal) {
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    const close = modal.querySelector("[data-close-modal]");
    if (close) close.focus({ preventScroll: true });
  }

  function closeModals() {
    $$(".modal-backdrop").forEach((modal) => {
      modal.hidden = true;
    });
    document.body.style.overflow = "";
  }

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.hidden = true;
    }, 2400);
  }

  $$("[data-open-wechat]").forEach((button) => {
    button.addEventListener("click", () => openModal(wechatModal));
  });

  $$("[data-coming-soon]").forEach((button) => {
    button.addEventListener("click", () => {
      const label = button.getAttribute("data-coming-soon") || "This link";
      showToast(`${label} link coming soon.`);
    });
  });

  $$("[data-lightbox]").forEach((button) => {
    button.addEventListener("click", () => {
      const src = button.getAttribute("data-lightbox");
      const img = button.querySelector("img");
      if (!src || !lightboxImage) return;
      lightboxImage.src = src;
      lightboxImage.alt = img ? img.alt : "Screenshot preview";
      openModal(lightboxModal);
    });
  });

  $$("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", closeModals);
  });

  $$(".modal-backdrop").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModals();
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModals();
      closeVideoModal();
    }
  });

  // ── Video modal ──
  const videoOverlay = $("#video-modal-overlay");
  const videoModalPlayer = $("#video-modal-player");
  const demoVideoWrap = $("#demo-video-wrap");
  const demoVideo = $("#demo-video");

  function openVideoModal() {
    if (!demoVideo || !videoModalPlayer) return;
    videoModalPlayer.src = demoVideo.querySelector("source")?.src || demoVideo.src;
    videoModalPlayer.currentTime = 0;
    videoOverlay.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  function closeVideoModal() {
    if (!videoOverlay || !videoOverlay.classList.contains("active")) return;
    videoOverlay.classList.remove("active");
    videoModalPlayer.pause();
    videoModalPlayer.removeAttribute("src");
    document.body.style.overflow = "";
  }

  if (demoVideoWrap) {
    demoVideoWrap.addEventListener("click", openVideoModal);
  }
  if ($("#video-modal-close")) {
    $("#video-modal-close").addEventListener("click", closeVideoModal);
  }
  if (videoOverlay) {
    videoOverlay.addEventListener("click", (e) => {
      if (e.target === videoOverlay) closeVideoModal();
    });
  }
})();
