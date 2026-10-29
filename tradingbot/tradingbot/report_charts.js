(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("report-data").textContent);
  var NS = "http://www.w3.org/2000/svg";
  var MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function el(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function frNum(v, d) {
    return v.toLocaleString("fr-FR", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
  }
  var FMT = {
    eur: function (v) { return frNum(v) + " €"; },
    eur0: function (v) { return frNum(v) + " €"; },
    pct: function (v) { return frNum(v) + " %"; },
  };
  function fmtDate(s) {
    var p = s.split("-");
    return parseInt(p[2], 10) + " " + MONTHS[parseInt(p[1], 10) - 1] + " " + p[0];
  }

  function niceTicks(min, max, count) {
    var span = max - min || 1;
    var step = Math.pow(10, Math.floor(Math.log10(span / count)));
    var err = (span / count) / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [];
    for (var v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function logTicks(min, max) {
    var out = [];
    for (var e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) {
      [1, 2, 5].forEach(function (m) { var v = m * Math.pow(10, e); if (v >= min && v <= max) out.push(v); });
    }
    return out;
  }

  function lineChart(root, cfg) {
    var tip = document.createElement("div");
    tip.className = "tip"; tip.hidden = true;
    function draw() {
      root.innerHTML = "";
      root.appendChild(tip);
      var W = root.clientWidth || 600, H = cfg.height || 280;
      var narrow = W < 560;
      var M = { l: 58, r: narrow ? 10 : 104, t: 10, b: 26 };
      var iw = W - M.l - M.r, ih = H - M.t - M.b;
      var n = cfg.dates.length;
      var all = [];
      cfg.series.forEach(function (s) { s.values.forEach(function (v) { if (v != null) all.push(v); }); });
      var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
      if (cfg.zeroTop) hi = 0;
      var fy;
      if (cfg.log) {
        var a = Math.log10(lo * 0.95), b = Math.log10(hi * 1.05);
        fy = function (v) { return M.t + ih - (Math.log10(v) - a) / (b - a) * ih; };
        var ticks = logTicks(lo * 0.95, hi * 1.05);
      } else {
        var pad = (hi - lo) * 0.06;
        var y0 = lo - pad, y1 = cfg.zeroTop ? 0 : hi + pad;
        fy = function (v) { return M.t + ih - (v - y0) / (y1 - y0) * ih; };
        var ticks = niceTicks(y0, y1, 5);
      }
      var fx = function (i) { return M.l + (n > 1 ? i / (n - 1) : 0) * iw; };
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H, height: H, role: "img", "aria-label": cfg.label });
      root.insertBefore(svg, tip);

      ticks.forEach(function (t) {
        var y = fy(t);
        if (y < M.t - 1 || y > M.t + ih + 1) return;
        el("line", { x1: M.l, x2: M.l + iw, y1: y, y2: y, stroke: css("--grid"), "stroke-width": 1 }, svg);
        el("text", { x: M.l - 8, y: y + 4, "text-anchor": "end" }, svg).textContent = cfg.tick(t);
      });
      // Axe des dates : mois si moins de 14 mois, sinon années
      var spanDays = n;
      var last = null;
      cfg.dates.forEach(function (d, i) {
        var key = spanDays > 430 ? d.slice(0, 4) : d.slice(0, 7);
        if (key === last) return;
        last = key;
        if (i === 0) return;
        if (spanDays <= 430) { var m = parseInt(d.slice(5, 7), 10); if (narrow ? m % 3 !== 1 : m % 2 !== 1) return; }
        var x = fx(i);
        el("line", { x1: x, x2: x, y1: M.t + ih, y2: M.t + ih + 4, stroke: css("--line") }, svg);
        el("text", { x: x, y: H - 6, "text-anchor": "middle" }, svg).textContent =
          spanDays > 430 ? key : MONTHS[parseInt(d.slice(5, 7), 10) - 1] + (d.slice(5, 7) === "01" ? " " + d.slice(2, 4) : "");
      });
      el("line", { x1: M.l, x2: M.l + iw, y1: M.t + ih, y2: M.t + ih, stroke: css("--line") }, svg);

      var ends = [];
      cfg.series.forEach(function (s) {
        var d = "", pen = false, lastI = -1;
        s.values.forEach(function (v, i) {
          if (v == null) { pen = false; return; }
          d += (pen ? "L" : "M") + fx(i).toFixed(1) + " " + fy(v).toFixed(1);
          pen = true; lastI = i;
        });
        if (cfg.area) {
          var first = s.values.findIndex(function (v) { return v != null; });
          el("path", { d: d + "L" + fx(lastI).toFixed(1) + " " + fy(0) + "L" + fx(first).toFixed(1) + " " + fy(0) + "Z",
            fill: css(s.color), "fill-opacity": 0.12, stroke: "none" }, svg);
        }
        el("path", { d: d, fill: "none", stroke: css(s.color), "stroke-width": s.width || 2,
          "stroke-linejoin": "round", "stroke-linecap": "round", "stroke-dasharray": s.dash || "" }, svg);
        if (lastI >= 0) ends.push({ s: s, x: fx(lastI), y: fy(s.values[lastI]), v: s.values[lastI] });
      });
      // Points finaux + étiquettes directes (écartées pour ne pas se chevaucher)
      ends.forEach(function (e) {
        el("circle", { cx: e.x, cy: e.y, r: 4, fill: css(e.s.color), stroke: css("--surface"), "stroke-width": 2 }, svg);
      });
      if (!narrow) {
        ends.sort(function (a, b) { return a.y - b.y; });
        var prev = -Infinity;
        ends.forEach(function (e) {
          var ly = Math.max(e.y, prev + 15);
          prev = ly;
          el("text", { x: M.l + iw + 10, y: ly + 4, class: "end" }, svg).textContent = e.s.short + " " + cfg.fmt(e.v);
        });
      }

      // Survol : réticule + infobulle
      var cross = el("line", { y1: M.t, y2: M.t + ih, stroke: css("--ink-3"), "stroke-width": 1, "stroke-dasharray": "3 3", visibility: "hidden" }, svg);
      var marks = cfg.series.map(function (s) {
        return el("circle", { r: 4, fill: css(s.color), stroke: css("--surface"), "stroke-width": 2, visibility: "hidden" }, svg);
      });
      var hit = el("rect", { x: M.l, y: M.t, width: iw, height: ih, fill: "transparent", tabindex: 0 }, svg);
      function show(i) {
        var x = fx(i);
        cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.setAttribute("visibility", "visible");
        var rows = "";
        cfg.series.forEach(function (s, k) {
          var v = s.values[i];
          if (v == null) { marks[k].setAttribute("visibility", "hidden"); return; }
          marks[k].setAttribute("cx", x); marks[k].setAttribute("cy", fy(v)); marks[k].setAttribute("visibility", "visible");
          rows += '<div class="r"><span><i style="background:' + css(s.color) + '"></i>' + s.name + "</span><span>" + cfg.fmt(v) + "</span></div>";
        });
        tip.innerHTML = '<div class="d">' + fmtDate(cfg.dates[i]) + "</div>" + rows;
        tip.hidden = false;
        var tw = tip.offsetWidth;
        var left = x + 14 + tw > W ? x - 14 - tw : x + 14;
        tip.style.left = Math.max(0, left) + "px";
        tip.style.top = M.t + 4 + "px";
      }
      function hide() {
        tip.hidden = true; cross.setAttribute("visibility", "hidden");
        marks.forEach(function (m) { m.setAttribute("visibility", "hidden"); });
      }
      var cur = n - 1;
      hit.addEventListener("pointermove", function (ev) {
        var r = svg.getBoundingClientRect();
        var px = (ev.clientX - r.left) * (W / r.width);
        cur = Math.max(0, Math.min(n - 1, Math.round((px - M.l) / iw * (n - 1))));
        show(cur);
      });
      hit.addEventListener("pointerleave", hide);
      hit.addEventListener("focus", function () { show(cur); });
      hit.addEventListener("blur", hide);
      hit.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowLeft") { cur = Math.max(0, cur - 1); show(cur); ev.preventDefault(); }
        if (ev.key === "ArrowRight") { cur = Math.min(n - 1, cur + 1); show(cur); ev.preventDefault(); }
      });
    }
    draw();
    var w = root.clientWidth;
    if (window.ResizeObserver) new ResizeObserver(function () { if (root.clientWidth !== w) { w = root.clientWidth; draw(); } }).observe(root);
    if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
    new MutationObserver(draw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  function legend(id, series, line) {
    document.getElementById(id).innerHTML = series.map(function (s) {
      return '<li><i class="' + (line ? "line " : "") + s.cls + '"></i>' + s.name + "</li>";
    }).join("");
  }

  function monthlyTable(id, dates, series, fmt) {
    var idx = [];
    dates.forEach(function (d, i) { if (i === dates.length - 1 || dates[i + 1].slice(0, 7) !== d.slice(0, 7)) idx.push(i); });
    var h = "<table><thead><tr><th>Date</th>" + series.map(function (s) { return '<th class="num">' + s.name + "</th>"; }).join("") + "</tr></thead><tbody>";
    idx.reverse().forEach(function (i) {
      h += "<tr><td>" + dates[i] + "</td>" + series.map(function (s) {
        var v = s.values[i]; return '<td class="num">' + (v == null ? "—" : fmt(v)) + "</td>";
      }).join("") + "</tr>";
    });
    document.getElementById(id).innerHTML = h + "</tbody></table>";
  }

  // 1) Bitcoin et ses moyennes
  var b = DATA.btc;
  var btcSeries = [
    { name: "Prix BTC", short: "Prix", values: b.price, color: "--s1", cls: "s1", width: 2.25 },
    { name: "Moyenne 50 j", short: "MM50", values: b.sma50, color: "--s2", cls: "s2", width: 1.5 },
    { name: "Moyenne 100 j", short: "MM100", values: b.sma100, color: "--s3", cls: "s3", width: 1.5 },
    { name: "Moyenne 200 j", short: "MM200", values: b.sma200, color: "--s4", cls: "s4", width: 1.5 },
  ];
  legend("btc-legend", btcSeries, true);
  lineChart(document.getElementById("btc-chart"), {
    dates: b.dates, series: btcSeries, fmt: FMT.eur0, label: "Prix du bitcoin et moyennes mobiles sur un an",
    tick: function (v) { return v >= 1000 ? frNum(v / 1000) + " k€" : frNum(v) + " €"; },
  });
  monthlyTable("btc-table", b.dates, btcSeries, FMT.eur0);

  // 2) Valeur de 100 € et chutes
  var s = DATA.strategy;
  var eqSeries = [
    { name: "Stratégie", short: "Stratégie", values: s.strat, color: "--s1", cls: "s1" },
    { name: "Acheter et garder", short: "Garder", values: s.hold, color: "--s2", cls: "s2" },
  ];
  legend("eq-legend", eqSeries, true);
  lineChart(document.getElementById("eq-chart"), {
    dates: s.dates, series: eqSeries, log: true, fmt: FMT.eur, label: "Valeur de 100 euros investis",
    tick: function (v) { return frNum(v) + " €"; },
  });
  monthlyTable("eq-table", s.dates, eqSeries, FMT.eur);

  var ddSeries = [
    { name: "Stratégie", short: "Stratégie", values: s.dd_strat, color: "--s1", cls: "s1" },
    { name: "Acheter et garder", short: "Garder", values: s.dd_hold, color: "--s2", cls: "s2" },
  ];
  legend("dd-legend", ddSeries, true);
  lineChart(document.getElementById("dd-chart"), {
    dates: s.dates, series: ddSeries, zeroTop: true, fmt: FMT.pct, label: "Chute depuis le dernier plus haut",
    tick: function (v) { return frNum(v) + " %"; },
  });
  monthlyTable("dd-table", s.dates, ddSeries, FMT.pct);
})();
