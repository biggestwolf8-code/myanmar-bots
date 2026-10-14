/* English (Gregorian) date picker.
   Replaces native <input type="date">, whose calendar follows the phone's
   locale (e.g. Thai Buddhist calendar). This picker is always Gregorian
   with English month names. The visible field shows "05 Oct 2026"; a hidden
   input carries the ISO "YYYY-MM-DD" value the server expects.
   Usage:
     <div class="dp-wrap">
       <input type="text" class="dp-display" readonly placeholder="Pick a date">
       <input type="hidden" class="dp-value" name="issue_date" value="2026-10-13">
     </div>
*/
(function () {
  "use strict";
  var MONTHS = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"];
  var SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DOW = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function isoOf(y, m, d) { return y + "-" + pad(m + 1) + "-" + pad(d); }

  function displayOf(iso) {
    var p = (iso || "").split("-");
    if (p.length !== 3) return "";
    var y = +p[0], m = +p[1], d = +p[2];
    if (!y || !m || !d) return "";
    return pad(d) + " " + SHORT[m - 1] + " " + y;
  }

  function parseIso(iso) {
    var p = (iso || "").split("-");
    var y = +p[0], m = +p[1], d = +p[2];
    if (y > 1900 && y < 2200 && m >= 1 && m <= 12 && d >= 1 && d <= 31) {
      return { y: y, m: m - 1, d: d };
    }
    var t = new Date();
    return { y: t.getFullYear(), m: t.getMonth(), d: t.getDate() };
  }

  // --- popup (single shared element) ---
  var pop = null, viewY = 0, viewM = 0, target = null;

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div");
    pop.className = "dp-pop";
    pop.innerHTML =
      '<div class="dp-card">' +
        '<div class="dp-head">' +
          '<button type="button" class="dp-nav" data-nav="-12" aria-label="Previous year">&laquo;</button>' +
          '<button type="button" class="dp-nav" data-nav="-1" aria-label="Previous month">&lsaquo;</button>' +
          '<div class="dp-title"></div>' +
          '<button type="button" class="dp-nav" data-nav="1" aria-label="Next month">&rsaquo;</button>' +
          '<button type="button" class="dp-nav" data-nav="12" aria-label="Next year">&raquo;</button>' +
        "</div>" +
        '<div class="dp-dow"></div>' +
        '<div class="dp-grid"></div>' +
        '<div class="dp-foot">' +
          '<button type="button" class="dp-btn" data-act="today">Today</button>' +
          '<button type="button" class="dp-btn" data-act="clear">Clear</button>' +
          '<button type="button" class="dp-btn" data-act="close">Done</button>' +
        "</div>" +
      "</div>";
    document.body.appendChild(pop);

    var dow = pop.querySelector(".dp-dow");
    DOW.forEach(function (d) {
      var s = document.createElement("span");
      s.textContent = d;
      dow.appendChild(s);
    });

    pop.addEventListener("click", function (e) {
      if (e.target === pop) { close(); return; }
      var nav = e.target.getAttribute("data-nav");
      if (nav) {
        var n = +nav;
        viewM += n % 12; viewY += Math.floor(n / 12);
        if (viewM < 0) { viewM += 12; viewY -= 1; }
        if (viewM > 11) { viewM -= 12; viewY += 1; }
        render();
        return;
      }
      var act = e.target.getAttribute("data-act");
      if (act === "today") {
        var t = new Date();
        pick(t.getFullYear(), t.getMonth(), t.getDate());
        return;
      }
      if (act === "clear") { pick(null); return; }
      if (act === "close") { close(); return; }
      var day = e.target.getAttribute("data-day");
      if (day) pick(viewY, viewM, +day);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
    return pop;
  }

  function render() {
    var title = pop.querySelector(".dp-title");
    title.textContent = MONTHS[viewM] + " " + viewY;
    var grid = pop.querySelector(".dp-grid");
    grid.innerHTML = "";
    var first = new Date(viewY, viewM, 1).getDay();
    var days = new Date(viewY, viewM + 1, 0).getDate();
    var sel = target ? parseIso(target.valueEl.value) : null;
    var t = new Date();
    for (var i = 0; i < first; i++) {
      var b = document.createElement("span");
      b.className = "dp-day dp-blank";
      grid.appendChild(b);
    }
    for (var d = 1; d <= days; d++) {
      (function (day) {
        var s = document.createElement("button");
        s.type = "button";
        s.className = "dp-day";
        s.textContent = day;
        s.setAttribute("data-day", day);
        if (sel && sel.y === viewY && sel.m === viewM && sel.d === day) {
          s.classList.add("dp-sel");
        }
        if (t.getFullYear() === viewY && t.getMonth() === viewM &&
            t.getDate() === day) {
          s.classList.add("dp-today");
        }
        grid.appendChild(s);
      })(d);
    }
  }

  function openFor(wrap) {
    target = {
      displayEl: wrap.querySelector(".dp-display"),
      valueEl: wrap.querySelector(".dp-value")
    };
    var cur = parseIso(target.valueEl.value);
    viewY = cur.y; viewM = cur.m;
    ensurePop();
    render();
    pop.classList.add("open");
  }

  function close() {
    if (pop) pop.classList.remove("open");
    target = null;
  }

  function pick(y, m, d) {
    if (!target) return;
    if (y === null) {
      target.valueEl.value = "";
      target.displayEl.value = "";
    } else {
      var iso = isoOf(y, m, d);
      target.valueEl.value = iso;
      target.displayEl.value = displayOf(iso);
    }
    close();
  }

  function init() {
    document.querySelectorAll(".dp-wrap").forEach(function (wrap) {
      var display = wrap.querySelector(".dp-display");
      var value = wrap.querySelector(".dp-value");
      if (!display || !value) return;
      display.value = displayOf(value.value);
      display.addEventListener("click", function () { openFor(wrap); });
      display.addEventListener("focus", function () {
        display.blur();
        openFor(wrap);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
