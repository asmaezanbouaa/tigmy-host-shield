(function () {
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

    if (!I18n) {
      console.error("GuestI18n not loaded");
      return;
    }

    function showScreen(screen) {
      if (langScreen) {
        langScreen.classList.toggle("guest-screen--active", screen === "lang");
        langScreen.classList.toggle("guest-screen--hidden", screen !== "lang");
      }
      if (formScreen) {
        formScreen.classList.toggle("guest-screen--active", screen === "form");
        formScreen.classList.toggle("guest-screen--hidden", screen !== "form");
      }
    }

    function showForm(lang) {
      I18n.setLang(lang);
      I18n.apply(lang);
      showScreen("form");

      const url = new URL(window.location.href);
      url.searchParams.set("lang", lang);
      window.history.replaceState({}, "", url);

      if (form && Dates) {
        try {
          Dates.applyLimits(form);
        } catch (e) {
          console.warn("Date limits", e);
        }
      }

      requestAnimationFrame(() => {
        formScreen?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (typeof window.dispatchEvent === "function") {
          window.dispatchEvent(new Event("signature-resize"));
        }
      });
    }

    function resetGuestForm() {
      if (form) {
        form.reset();
        form.querySelectorAll(".date-invalid").forEach((el) => {
          el.classList.remove("date-invalid");
        });
      }
      const clearSig = document.getElementById("clear-signature");
      if (clearSig) clearSig.click();
      if (errorBox) errorBox.hidden = true;
    }

    function showLangPicker(clearSavedLang) {
      if (clearSavedLang) {
        try {
          localStorage.removeItem("guest_form_lang");
        } catch (e) {
          /* ignore */
        }
      }
      const lang = I18n.getLang() || "fr";
      I18n.apply(lang);
      showScreen("lang");
      resetGuestForm();
      const url = new URL(window.location.href);
      url.searchParams.delete("lang");
      url.searchParams.delete("fresh");
      window.history.replaceState({}, "", url.pathname + url.search);
    }

    document.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const lang = btn.getAttribute("data-lang");
        if (lang) showForm(lang);
      });
    });

    document.getElementById("change-lang-btn")?.addEventListener("click", (e) => {
      e.preventDefault();
      showLangPicker(false);
    });

    const submitBtn = document.getElementById("submit-btn");
    const loading = document.getElementById("form-loading");
    const errorBox = document.getElementById("form-error");

    const url = new URL(window.location.href);
    const isFresh =
      url.searchParams.get("fresh") === "1" || config.fresh_start === true;

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
      I18n.apply("fr");
      resetGuestForm();
    } else {
      const urlLang = url.searchParams.get("lang");
      const initial =
        urlLang && I18n.langs.includes(urlLang) ? urlLang : config.selected_lang || null;

      if (initial && form) {
        showForm(initial);
      } else if (langScreen) {
        showScreen("lang");
        I18n.apply("fr");
      }
    }

    if (!form) return;

    function msg(key) {
      const lang = I18n.getLang() || "fr";
      return I18n.t[lang]?.[key] || I18n.t.en[key] || key;
    }

    const checks = ["accept_internal_rules", "accept_terms"];

    function allChecksOk() {
      return checks.every((id) => document.getElementById(id)?.checked);
    }

    function datesOk() {
      if (!Dates) return true;
      return Dates.validate(form) === null;
    }

    function formValid() {
      if (!allChecksOk()) return false;
      if (!datesOk()) return false;
      const idFile = document.getElementById("id_scan");
      if (!idFile?.files?.length) return false;
      if (typeof window.hasSignature === "function" && !window.hasSignature()) return false;
      return true;
    }

    function updateSubmit() {
      if (submitBtn) submitBtn.disabled = !formValid();
    }

    function onDateChange() {
      if (Dates) {
        Dates.updateDepartureLimits(form);
        const errKey = Dates.markInvalid(form);
        if (errKey && errorBox) {
          errorBox.textContent = msg(errKey);
          errorBox.hidden = false;
        } else if (errorBox) {
          errorBox.hidden = true;
        }
      }
      updateSubmit();
    }

    checks.forEach((id) => {
      document.getElementById(id)?.addEventListener("change", updateSubmit);
    });

    ["date_of_birth", "arrival_date", "departure_date", "number_of_guests", "number_of_kids"].forEach(
      (name) => {
        form[name]?.addEventListener("change", onDateChange);
        form[name]?.addEventListener("input", onDateChange);
      }
    );

    form.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("input", updateSubmit);
      el.addEventListener("change", updateSubmit);
    });
    document.getElementById("id_scan")?.addEventListener("change", updateSubmit);
    window.addEventListener("signature-changed", updateSubmit);
    updateSubmit();

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (Dates) {
        const errKey = Dates.markInvalid(form);
        if (errKey) {
          errorBox.textContent = msg(errKey);
          errorBox.hidden = false;
          return;
        }
      }

      if (!formValid()) return;

      const sig = window.getSignatureDataUrl();
      if (!sig) {
        errorBox.textContent = msg("err_sign");
        errorBox.hidden = false;
        return;
      }

      submitBtn.disabled = true;
      loading.hidden = false;
      loading.style.display = "block";
      errorBox.hidden = true;

      const idFile = document.getElementById("id_scan");
      if (!idFile?.files?.[0]) {
        errorBox.textContent = msg("err_id_scan");
        errorBox.hidden = false;
        submitBtn.disabled = false;
        loading.style.display = "none";
        loading.hidden = true;
        return;
      }

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
      fd.append("id_document_type", form.id_document_type.value);
      fd.append("id_document_number", form.id_document_number.value.trim());
      fd.append("accept_internal_rules", "true");
      fd.append("accept_terms", "true");
      fd.append("signature_data_url", sig);
      fd.append("id_scan", idFile.files[0]);

      const token = form.dataset.token;
      try {
        const res = await fetch(`/api/form/${token}/submit`, {
          method: "POST",
          body: fd,
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail;
          let errMsg = msg("err_generic");
          if (typeof detail === "string") errMsg = detail;
          else if (Array.isArray(detail))
            errMsg = detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
          throw new Error(errMsg);
        }
        window.location.href = data.redirect_url || `/f/${token}/success`;
      } catch (err) {
        errorBox.textContent = err.message || msg("err_generic");
        errorBox.hidden = false;
        submitBtn.disabled = false;
        loading.style.display = "none";
        loading.hidden = true;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
