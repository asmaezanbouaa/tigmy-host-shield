(function () {
  const form = document.getElementById("submissions-filter-form");
  if (!form) return;

  let debounceTimer = null;

  function submitFilters() {
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  form.querySelectorAll("select").forEach((el) => {
    el.addEventListener("change", submitFilters);
  });

  const search = form.querySelector('input[name="q"]');
  if (search) {
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitFilters();
      }
    });
    search.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(submitFilters, 450);
    });
  }

  form.querySelectorAll('input[type="date"]').forEach((el) => {
    el.addEventListener("change", submitFilters);
  });
})();
