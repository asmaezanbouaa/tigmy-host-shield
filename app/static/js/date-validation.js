/**
 * Client-side date rules (mirrors app/services/date_validation.py)
 */
window.GuestDateValidation = {
  MIN_AGE: 16,
  MAX_AGE: 120,
  ARRIVAL_PAST_DAYS: 30,
  ARRIVAL_FUTURE_DAYS: 730,
  MIN_STAY_DAYS: 1,
  MAX_STAY_DAYS: 365,
  ISO_DATE_RE: /^\d{4}-\d{2}-\d{2}$/,

  parseISO(str) {
    if (!str || !this.ISO_DATE_RE.test(str)) return null;
    const parts = str.split("-").map((p) => parseInt(p, 10));
    const y = parts[0];
    const m = parts[1];
    const d = parts[2];
    if (m < 1 || m > 12 || d < 1 || d > 31) return null;

    const t = this.today();
    const minYear = t.getFullYear() - this.MAX_AGE - 1;
    const maxYear = t.getFullYear() + 3;
    if (y < minYear || y > maxYear) return null;

    const date = new Date(y, m - 1, d);
    if (
      date.getFullYear() !== y ||
      date.getMonth() !== m - 1 ||
      date.getDate() !== d
    ) {
      return null;
    }
    return date;
  },

  iso(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  },

  today() {
    const t = new Date();
    return new Date(t.getFullYear(), t.getMonth(), t.getDate());
  },

  addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  },

  applyLimits(form) {
    const limits = window.DATE_LIMITS;
    if (!limits || !form) return;

    const dob = form.date_of_birth;
    const arrival = form.arrival_date;

    if (dob) {
      dob.min = limits.dob_min;
      dob.max = limits.dob_max;
      dob.setAttribute("maxlength", "10");
    }
    if (arrival) {
      arrival.min = limits.arrival_min;
      arrival.max = limits.arrival_max;
      arrival.setAttribute("maxlength", "10");
    }
    this.updateDepartureLimits(form);
    this.setupDateInputs(form);
    this.setupNumberInputs(form);
  },

  updateDepartureLimits(form) {
    const limits = window.DATE_LIMITS;
    const arrival = form.arrival_date;
    const departure = form.departure_date;
    if (!arrival || !departure || !limits) return;

    departure.setAttribute("maxlength", "10");
    const arrVal = arrival.value;

    if (!arrVal || !this.parseISO(arrVal)) {
      departure.min = "";
      departure.max = limits.departure_max_global;
      return;
    }

    const arr = this.parseISO(arrVal);
    const depMin = this.addDays(arr, this.MIN_STAY_DAYS);
    const depMaxStay = this.addDays(arr, this.MAX_STAY_DAYS);
    const globalMax = this.parseISO(limits.departure_max_global);

    departure.min = this.iso(depMin);
    departure.max = this.iso(
      depMaxStay < globalMax ? depMaxStay : globalMax
    );

    this.enforceDateField(departure, departure.min, departure.max);
  },

  /** Clear invalid date immediately (blocks years like 8888) */
  enforceDateField(input, min, max) {
    if (!input) return null;
    const v = input.value.trim();
    if (!v) {
      input.setCustomValidity("");
      return null;
    }

    if (!this.parseISO(v)) {
      input.value = "";
      input.setCustomValidity("Invalid date");
      return "err_date_invalid";
    }

    if (min && v < min) {
      input.value = "";
      input.setCustomValidity("Date too early");
      return "err_date_invalid";
    }
    if (max && v > max) {
      input.value = "";
      input.setCustomValidity("Date too late");
      return "err_date_invalid";
    }

    input.setCustomValidity("");
    return null;
  },

  setupDateInputs(form) {
    const limits = window.DATE_LIMITS;
    if (!limits || form.dataset.datesBound === "1") return;
    form.dataset.datesBound = "1";

    const bind = (el, min, max) => {
      if (!el) return;
      const run = () => this.enforceDateField(el, min, max);
      el.addEventListener("input", run);
      el.addEventListener("change", run);
      el.addEventListener("blur", run);
      el.addEventListener("invalid", (e) => {
        e.preventDefault();
        run();
      });
    };

    bind(form.date_of_birth, limits.dob_min, limits.dob_max);
    bind(form.arrival_date, limits.arrival_min, limits.arrival_max);

    const dep = form.departure_date;
    if (dep) {
      const run = () => {
        this.updateDepartureLimits(form);
        this.enforceDateField(dep, dep.min, dep.max);
      };
      dep.addEventListener("input", run);
      dep.addEventListener("change", run);
      dep.addEventListener("blur", run);
    }
  },

  setupNumberInputs(form) {
    if (form.dataset.numbersBound === "1") return;
    form.dataset.numbersBound = "1";
    const clamp = (el, min, max) => {
      if (!el) return;
      el.addEventListener("keydown", (e) => {
        if (["e", "E", "+", "-", "."].includes(e.key)) e.preventDefault();
      });
      el.addEventListener("input", () => {
        let v = parseInt(el.value, 10);
        if (Number.isNaN(v) || el.value === "") {
          el.value = String(min);
          return;
        }
        if (v < min) v = min;
        if (v > max) v = max;
        el.value = String(v);
      });
    };
    clamp(form.number_of_guests, 1, 50);
    clamp(form.number_of_kids, 0, 30);
  },

  validate(form) {
    const limits = window.DATE_LIMITS;
    const dobVal = form.date_of_birth?.value;
    const arrVal = form.arrival_date?.value;
    const depVal = form.departure_date?.value;

    if (!dobVal || !this.parseISO(dobVal)) return "err_date_invalid";
    const dob = this.parseISO(dobVal);
    const today = this.today();

    const oldest = this.addDays(today, -this.MAX_AGE * 365);
    const youngest = new Date(
      today.getFullYear() - this.MIN_AGE,
      today.getMonth(),
      today.getDate()
    );

    if (dob > today) return "err_dob_future";
    if (dob < oldest) return "err_dob_too_old";
    if (dob > youngest) return "err_dob_too_young";

    if (!arrVal || !this.parseISO(arrVal)) return "err_date_invalid";
    const arrival = this.parseISO(arrVal);
    if (limits && arrVal < limits.arrival_min) return "err_arrival_past";
    if (limits && arrVal > limits.arrival_max) return "err_arrival_future";

    const arrEarliest = this.addDays(today, -this.ARRIVAL_PAST_DAYS);
    const arrLatest = this.addDays(today, this.ARRIVAL_FUTURE_DAYS);
    if (arrival < arrEarliest) return "err_arrival_past";
    if (arrival > arrLatest) return "err_arrival_future";

    if (!depVal || !this.parseISO(depVal)) return "err_date_invalid";
    const departure = this.parseISO(depVal);
    if (departure < arrival) return "err_departure_before";

    const minDep = this.addDays(arrival, this.MIN_STAY_DAYS);
    if (departure < minDep) return "err_departure_min_stay";

    const maxDep = this.addDays(arrival, this.MAX_STAY_DAYS);
    if (departure > maxDep) return "err_departure_max_stay";

    const guests = parseInt(form.number_of_guests?.value, 10) || 0;
    const kids = parseInt(form.number_of_kids?.value, 10) || 0;
    if (guests < 1 || guests > 50) return "err_date_invalid";
    if (kids < 0 || kids > 30) return "err_date_invalid";
    if (kids > guests) return "err_kids_exceed";

    return null;
  },

  markInvalid(form) {
    const errKey = this.validate(form);
    [form.date_of_birth, form.arrival_date, form.departure_date].forEach((el) => {
      el?.classList.remove("date-invalid");
    });
    form.number_of_kids?.classList.remove("date-invalid");
    if (!errKey) return null;

    if (errKey.startsWith("err_dob")) form.date_of_birth?.classList.add("date-invalid");
    if (errKey.startsWith("err_arrival")) form.arrival_date?.classList.add("date-invalid");
    if (errKey.startsWith("err_departure")) form.departure_date?.classList.add("date-invalid");
    if (errKey === "err_kids_exceed") form.number_of_kids?.classList.add("date-invalid");
    return errKey;
  },
};
