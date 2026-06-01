/**
 * Responsive signature pad for touch and mouse.
 */
(function () {
  const canvas = document.getElementById("signature-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  let drawing = false;
  let hasStroke = false;

  function resize() {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.scale(ratio, ratio);
    ctx.strokeStyle = "#1a1a2e";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  }

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const touch = e.touches && e.touches[0];
    const clientX = touch ? touch.clientX : e.clientX;
    const clientY = touch ? touch.clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  }

  function start(e) {
    e.preventDefault();
    drawing = true;
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  }

  function move(e) {
    if (!drawing) return;
    e.preventDefault();
    const p = pos(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    hasStroke = true;
    window.dispatchEvent(new CustomEvent("signature-changed", { detail: { hasStroke } }));
  }

  function end(e) {
    if (!drawing) return;
    e.preventDefault();
    drawing = false;
  }

  function safeResize() {
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2) return;
    resize();
  }

  safeResize();
  window.addEventListener("resize", () => {
    const img = hasStroke ? canvas.toDataURL() : null;
    safeResize();
    if (img && canvas.getBoundingClientRect().width >= 2) {
      const image = new Image();
      image.onload = () => {
        ctx.drawImage(image, 0, 0, canvas.getBoundingClientRect().width, canvas.getBoundingClientRect().height);
      };
      image.src = img;
    }
  });

  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  canvas.addEventListener("mouseup", end);
  canvas.addEventListener("mouseleave", end);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", end, { passive: false });

  const clearBtn = document.getElementById("clear-signature");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasStroke = false;
      window.dispatchEvent(new CustomEvent("signature-changed", { detail: { hasStroke: false } }));
    });
  }

  window.getSignatureDataUrl = function () {
    if (!hasStroke) return null;
    return canvas.toDataURL("image/png");
  };

  window.hasSignature = function () {
    return hasStroke;
  };

  window.addEventListener("signature-resize", () => {
    safeResize();
  });
})();
