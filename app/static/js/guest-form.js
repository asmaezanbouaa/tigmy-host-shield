(function () {
  const TOTAL_STEPS = 4;
  const MAX_ID_BYTES = 10 * 1024 * 1024;
  const LANG_LABEL = { fr: "FR", en: "EN", ar: "ع" };

  function loadConfig() {
    const el = document.getElementById("guest-config");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      console.error("Guest config JSON invalid", e);
      return {};
    }
  }

  function init() {
    const I18n = window.GuestI18n;
    const Dates = window.GuestDateValidation;
    const config = loadConfig();

    window.RULES_BY_LANG = config.rules || {};
    window.DATE_LIMITS = config.date_limits || {};

    const langScreen = document.getElementById("lang-screen");
    const formScreen = document.getElementById("form-screen");
    const form = document.getElementById("guest-form");
    const changeLangBtn = document.getElementById("change-lang-btn");
    const errorBox = document.getElementById("form-error");

    if (!I18n) {
      console.error("GuestI18n not loaded");
      return;
    }

    function lang() {
      return I18n.getLang() || "fr";
    }

    function msg(key, vars) {
      let s = I18n.t[lang()]?.[key] || I18n.t.en[key] || key;
      if (vars) Object.keys(vars).forEach((k) => (s = s.replace(`{${k}}`, vars[k])));
      return s;
    }

    function applyLang(l) {
      I18n.apply(l);
      const rules = document.getElementById("rules-full");
      if (rules) rules.textContent = (window.RULES_BY_LANG || {})[l] || "";
      const label = document.getElementById("current-lang-label");
      if (label) label.textContent = LANG_LABEL[l] || l.toUpperCase();
      if (form) renderStep();
    }

    function showScreen(screen) {
      langScreen?.classList.toggle("g-screen--hidden", screen !== "lang");
      formScreen?.classList.toggle("g-screen--hidden", screen !== "form");
      if (changeLangBtn) changeLangBtn.hidden = screen !== "form";
    }

    function showError(text, focusEl) {
      if (!errorBox) return;
      errorBox.textContent = text;
      errorBox.hidden = false;
      if (focusEl && typeof focusEl.focus === "function") {
        focusEl.focus({ preventScroll: true });
        focusEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }

    function clearError() {
      if (errorBox) errorBox.hidden = true;
    }

    // ---------- Steps ----------
    let current = 1;
    const steps = form ? Array.from(form.querySelectorAll("[data-form-step]")) : [];
    const backBtn = document.getElementById("back-btn");
    const nextBtn = document.getElementById("next-btn");
    const submitBtn = document.getElementById("submit-btn");
    const fileInput = document.getElementById("id_scan");
    const upload = document.getElementById("id-upload");
    let idCheck = { file: null, status: "none", code: "" };
    const ICON_OK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
    const ICON_BAD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
    const preview = document.getElementById("id-preview");
    let previewUrl = null;
    const checks = ["accept_internal_rules", "accept_terms"];

    function renderStep() {
      steps.forEach((el) => el.classList.toggle("is-active", Number(el.dataset.formStep) === current));
      document.querySelectorAll(".g-progress__seg").forEach((seg) => {
        const n = Number(seg.dataset.seg);
        seg.classList.toggle("is-done", n < current);
        seg.classList.toggle("is-active", n === current);
      });
      const active = steps.find((el) => Number(el.dataset.formStep) === current);
      const title = document.getElementById("step-title");
      if (title && active) title.textContent = msg(active.dataset.titleKey);
      const count = document.getElementById("step-count");
      if (count) count.textContent = msg("step_count", { n: current, total: TOTAL_STEPS });
      document.getElementById("progress-bar")?.setAttribute("aria-valuenow", String(current));
      if (backBtn) backBtn.hidden = current === 1;
      updateNextState();
      if (nextBtn) nextBtn.hidden = current === TOTAL_STEPS;
      if (submitBtn) submitBtn.hidden = current !== TOTAL_STEPS;
      if (current === TOTAL_STEPS) {
        renderRecap();
        window.dispatchEvent(new Event("signature-resize"));
      }
      updateSubmit();
    }

    function goTo(step) {
      current = Math.min(Math.max(step, 1), TOTAL_STEPS);
      clearError();
      renderStep();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function markField(el, bad) {
      el?.classList.toggle("is-invalid", !!bad);
    }

    function validateStep(step) {
      const scope = steps.find((el) => Number(el.dataset.formStep) === step);
      if (!scope) return true;

      const required = Array.from(scope.querySelectorAll("input.g-input[required]"));
      let firstBad = null;
      required.forEach((el) => {
        const bad = !el.value.trim();
        markField(el, bad);
        if (bad && !firstBad) firstBad = el;
      });
      if (firstBad) {
        showError(msg("err_required"), firstBad);
        return false;
      }

      if (step === 1 && Dates) {
        const err = Dates.validate(form);
        if (err && (err.startsWith("err_dob") || !Dates.parseISO(form.date_of_birth.value))) {
          Dates.markInvalid(form);
          showError(msg(err), form.date_of_birth);
          return false;
        }
      }
      if (step === 2 && Dates) {
        const err = Dates.markInvalid(form);
        if (err) {
          const target = err === "err_kids_exceed" ? form.number_of_kids : err.startsWith("err_departure") ? form.departure_date : form.arrival_date;
          showError(msg(err), target);
          return false;
        }
      }
      if (step === 3) {
        const choices = document.getElementById("id-type-choices");
        const picked = form.querySelector('input[name="id_document_type"]:checked');
        choices?.classList.toggle("is-invalid", !picked);
        if (!picked) {
          showError(msg("err_id_type"), choices.querySelector("input"));
          return false;
        }
        const file = document.getElementById("id_scan")?.files?.[0];
        const upload = document.getElementById("id-upload");
        if (!file) {
          upload?.classList.add("is-invalid");
          showError(msg("err_id_scan"), upload);
          return false;
        }
        if (file.size > MAX_ID_BYTES) {
          upload?.classList.add("is-invalid");
          showError(msg("upload_too_big"), upload);
          return false;
        }
        if (idCheck.file !== file || idCheck.status === "error") {
          runIdCheck(file);
          showError(msg("id_checking_wait"), upload);
          return false;
        }
        if (idCheck.status === "checking") {
          showError(msg("id_checking_wait"), upload);
          return false;
        }
        if (idCheck.status !== "ok") {
          showError(idMsg(idCheck), upload);
          return false;
        }
      }
      clearError();
      return true;
    }

    // ---------- Language flow ----------
    function resetGuestForm() {
      if (!form) return;
      form.reset();
      form.querySelectorAll(".date-invalid, .is-invalid").forEach((el) => el.classList.remove("date-invalid", "is-invalid"));
      document.getElementById("clear-signature")?.click();
      resetUpload();
      current = 1;
      clearError();
    }

    function showForm(l) {
      I18n.setLang(l);
      applyLang(l);
      showScreen("form");
      const url = new URL(window.location.href);
      url.searchParams.set("lang", l);
      window.history.replaceState({}, "", url);
      if (form && Dates) {
        try {
          Dates.applyLimits(form);
        } catch (e) {
          console.warn("Date limits", e);
        }
      }
      goTo(current);
    }

    function showLangPicker() {
      applyLang(lang());
      showScreen("lang");
      resetGuestForm();
      const url = new URL(window.location.href);
      url.searchParams.delete("lang");
      url.searchParams.delete("fresh");
      window.history.replaceState({}, "", url.pathname + url.search);
      window.scrollTo({ top: 0 });
    }

    document.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const l = btn.getAttribute("data-lang");
        if (l) showForm(l);
      });
    });
    changeLangBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      showLangPicker();
    });

    const url = new URL(window.location.href);
    const isFresh = url.searchParams.get("fresh") === "1" || config.fresh_start === true;
    if (isFresh) {
      try {
        localStorage.removeItem("guest_form_lang");
      } catch (e) {
        /* ignore */
      }
      url.searchParams.delete("fresh");
      url.searchParams.delete("lang");
      window.history.replaceState({}, "", url.pathname + url.search);
      showScreen("lang");
      applyLang("fr");
      resetGuestForm();
    } else {
      const urlLang = url.searchParams.get("lang");
      const initial = urlLang && I18n.langs.includes(urlLang) ? urlLang : config.selected_lang || null;
      if (initial && form) showForm(initial);
      else {
        showScreen("lang");
        applyLang("fr");
      }
    }

    if (!form) return;

    // ---------- Navigation ----------
    nextBtn?.addEventListener("click", () => {
      if (validateStep(current)) goTo(current + 1);
    });
    backBtn?.addEventListener("click", () => goTo(current - 1));
    form.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.tagName === "INPUT" && current < TOTAL_STEPS) {
        e.preventDefault();
        nextBtn?.click();
      }
    });

    // ---------- Steppers ----------
    form.querySelectorAll("[data-stepper]").forEach((wrap) => {
      const input = wrap.querySelector("input");
      const [minus, plus] = wrap.querySelectorAll("button");
      const sync = () => {
        const v = parseInt(input.value, 10) || 0;
        minus.disabled = v <= Number(input.min);
        plus.disabled = v >= Number(input.max);
      };
      wrap.querySelectorAll("button").forEach((b) =>
        b.addEventListener("click", () => {
          const v = (parseInt(input.value, 10) || 0) + Number(b.dataset.stepDir);
          input.value = String(Math.min(Math.max(v, Number(input.min)), Number(input.max)));
          input.dispatchEvent(new Event("input", { bubbles: true }));
          sync();
        })
      );
      input.addEventListener("input", sync);
      form.addEventListener("reset", () => setTimeout(sync));
      sync();
    });

    // ---------- Nights summary ----------
    function updateNights() {
      const box = document.getElementById("stay-summary");
      const out = document.getElementById("stay-nights");
      if (!box || !out || !Dates) return;
      const a = Dates.parseISO(form.arrival_date.value);
      const d = Dates.parseISO(form.departure_date.value);
      const n = a && d ? Math.round((d - a) / 86400000) : 0;
      box.hidden = !(n > 0);
      if (n > 0) out.textContent = msg(n === 1 ? "nights_one" : "nights_many", { n });
    }

    // ---------- Upload ----------

    // ---------- ID photo quality (checked on the server, same rules as on submit) ----------

    function showIdCheck(status, text) {
      const box = document.getElementById("id-check");
      if (!box) return;
      box.hidden = status === "none";
      box.className = "g-check-result " + ({ ok: "is-ok", checking: "is-wait" }[status] || "is-bad");
      document.getElementById("id-check-icon").innerHTML = status === "ok" ? ICON_OK : status === "checking" ? "" : ICON_BAD;
      document.getElementById("id-check-text").textContent = text || "";
      upload?.classList.toggle("is-checking", status === "checking");
      upload?.classList.toggle("is-invalid", status === "bad" || status === "error");
    }

    async function runIdCheck(file) {
      idCheck = { file, status: "checking", code: "" };
      showIdCheck("checking", msg("id_checking"));
      updateNextState();
      const fd = new FormData();
      fd.append("id_scan", file);
      try {
        const res = await fetch(`/api/form/${form.dataset.token}/check-id`, { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (idCheck.file !== file) return; // a newer photo was chosen meanwhile
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "");
        idCheck = { file, status: data.ok ? "ok" : "bad", code: data.code || "id_no_document", size: { w: data.width, h: data.height } };
        showIdCheck(idCheck.status, data.ok ? msg("id_ok") : idMsg(idCheck));
        if (data.ok) clearError();
      } catch (e) {
        if (idCheck.file !== file) return;
        idCheck = { file, status: "error", code: "id_check_failed" };
        showIdCheck("error", e.message || msg("id_check_failed"));
      }
      updateNextState();
    }

    function idMsg(check) {
      if (check.code === "id_too_small" && check.size && check.size.w) return msg("id_too_small_size", check.size);
      return msg(check.code);
    }

    function updateNextState() {
      if (nextBtn) nextBtn.disabled = current === 3 && idCheck.status === "checking";
    }

    function resetUpload() {
      idCheck = { file: null, status: "none", code: "" };
      showIdCheck("none");
      upload?.classList.remove("has-file", "is-invalid", "is-checking");
      if (preview) {
        preview.hidden = true;
        preview.removeAttribute("src");
      }
      document.getElementById("id-upload-icon")?.removeAttribute("hidden");
      const title = document.getElementById("id-upload-title");
      const sub = document.getElementById("id-upload-sub");
      if (title) title.textContent = msg("upload_title");
      if (sub) sub.textContent = msg("upload_sub");
    }

    fileInput?.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
      if (!file) return resetUpload();
      upload.classList.add("has-file");
      upload.classList.toggle("is-invalid", file.size > MAX_ID_BYTES);
      const title = document.getElementById("id-upload-title");
      const sub = document.getElementById("id-upload-sub");
      if (title) title.textContent = file.name;
      if (sub) sub.textContent = file.size > MAX_ID_BYTES ? msg("upload_too_big") : msg("upload_change");
      if (file.type.startsWith("image/") && preview) {
        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        preview.hidden = false;
        document.getElementById("id-upload-icon")?.setAttribute("hidden", "");
      } else if (preview) {
        preview.hidden = true;
        document.getElementById("id-upload-icon")?.removeAttribute("hidden");
      }
      if (file.size <= MAX_ID_BYTES) {
        clearError();
        runIdCheck(file);
      } else {
        idCheck = { file, status: "bad", code: "upload_too_big" };
        showIdCheck("bad", msg("upload_too_big"));
      }
      updateSubmit();
    });
    ["dragenter", "dragover"].forEach((ev) => upload?.addEventListener(ev, () => upload.classList.add("is-drag")));
    ["dragleave", "drop"].forEach((ev) => upload?.addEventListener(ev, () => upload.classList.remove("is-drag")));

    // ---------- Recap ----------
    function renderRecap() {
      const box = document.getElementById("recap");
      if (!box) return;
      const idType = form.querySelector('input[name="id_document_type"]:checked');
      const idLabel = idType ? idType.closest(".g-choice").querySelector("[data-i18n]").textContent : "";
      const guests = parseInt(form.number_of_guests.value, 10) || 1;
      const kids = parseInt(form.number_of_kids.value, 10) || 0;
      const rows = [
        [msg("recap_guest"), `${form.first_name.value.trim()} ${form.last_name.value.trim()}`],
        [msg("recap_stay"), `${form.arrival_date.value} → ${form.departure_date.value}`],
        [msg("recap_people"), kids ? `${guests} (${kids} ${msg("recap_kids")})` : String(guests)],
        [msg("recap_id"), `${idLabel} · ${form.id_document_number.value.trim()}`],
      ];
      box.replaceChildren(
        ...rows.map(([k, v]) => {
          const row = document.createElement("div");
          row.className = "g-recap__row";
          const kEl = document.createElement("span");
          kEl.className = "g-recap__k";
          kEl.textContent = k;
          const vEl = document.createElement("span");
          vEl.className = "g-recap__v";
          vEl.textContent = v;
          row.append(kEl, vEl);
          return row;
        })
      );
    }

    // ---------- Final step validity ----------
    function finalValid() {
      if (!checks.every((id) => document.getElementById(id)?.checked)) return false;
      if (typeof window.hasSignature === "function" && !window.hasSignature()) return false;
      return true;
    }
    function updateSubmit() {
      if (submitBtn && !submitBtn.dataset.busy) submitBtn.disabled = !finalValid();
    }

    checks.forEach((id) => document.getElementById(id)?.addEventListener("change", updateSubmit));
    window.addEventListener("signature-changed", (e) => {
      document.getElementById("sign-box")?.classList.toggle("has-ink", !!e.detail?.hasStroke);
      updateSubmit();
    });

    form.querySelectorAll("input").forEach((el) => {
      el.addEventListener("input", () => {
        el.classList.remove("is-invalid");
        if (el.name === "id_document_type") document.getElementById("id-type-choices")?.classList.remove("is-invalid");
      });
    });
    ["arrival_date", "departure_date"].forEach((n) => {
      form[n]?.addEventListener("change", updateNights);
      form[n]?.addEventListener("input", updateNights);
    });
    ["date_of_birth", "arrival_date", "departure_date", "number_of_guests", "number_of_kids"].forEach((n) => {
      form[n]?.addEventListener("change", () => {
        if (Dates) Dates.updateDepartureLimits(form);
      });
    });

    // ---------- Submit ----------
    function setBusy(busy) {
      if (!submitBtn) return;
      if (busy) submitBtn.dataset.busy = "1";
      else delete submitBtn.dataset.busy;
      submitBtn.disabled = busy || !finalValid();
      document.getElementById("form-loading").hidden = !busy;
      document.getElementById("submit-label").textContent = msg(busy ? "loading" : "submit");
      if (backBtn) backBtn.disabled = busy;
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (current !== TOTAL_STEPS) return;

      for (let s = 1; s < TOTAL_STEPS; s++) {
        if (!validateStep(s)) {
          const errText = errorBox?.textContent;
          goTo(s);
          if (errText) showError(errText);
          return;
        }
      }
      if (!checks.every((id) => document.getElementById(id)?.checked)) {
        showError(msg("err_accept"));
        return;
      }
      const sig = window.getSignatureDataUrl();
      if (!sig) {
        showError(msg("err_sign"), document.getElementById("sign-box"));
        return;
      }

      setBusy(true);
      clearError();

      const fd = new FormData();
      fd.append("last_name", form.last_name.value.trim());
      fd.append("first_name", form.first_name.value.trim());
      fd.append("nationality", form.nationality.value.trim());
      fd.append("date_of_birth", form.date_of_birth.value);
      fd.append("country_of_residence", form.country_of_residence.value.trim());
      fd.append("number_of_guests", String(parseInt(form.number_of_guests.value, 10) || 1));
      fd.append("number_of_kids", String(parseInt(form.number_of_kids.value, 10) || 0));
      fd.append("arrival_date", form.arrival_date.value);
      fd.append("departure_date", form.departure_date.value);
      fd.append("id_document_type", form.querySelector('input[name="id_document_type"]:checked').value);
      fd.append("id_document_number", form.id_document_number.value.trim());
      fd.append("accept_internal_rules", "true");
      fd.append("accept_terms", "true");
      fd.append("signature_data_url", sig);
      fd.append("id_scan", fileInput.files[0]);

      const token = form.dataset.token;
      try {
        const res = await fetch(`/api/form/${token}/submit`, { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail;
          if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.code) {
            setBusy(false);
            if (detail.code.startsWith("id_")) {
              idCheck = { file: fileInput.files[0], status: "bad", code: detail.code, size: { w: detail.width, h: detail.height } };
              goTo(3);
              showIdCheck("bad", idMsg(idCheck));
            }
            showError(detail.code.startsWith("id_") ? idMsg(idCheck) : msg(detail.code) || detail.message);
            return;
          }
          let errMsg = msg("err_generic");
          if (typeof detail === "string") errMsg = detail;
          else if (Array.isArray(detail)) errMsg = detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
          throw new Error(errMsg);
        }
        window.location.href = data.redirect_url || `/f/${token}/success`;
      } catch (err) {
        showError(err.message || msg("err_generic"));
        setBusy(false);
      }
    });

    renderStep();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
