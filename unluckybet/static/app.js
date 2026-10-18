(function () {
  'use strict';

  // ---------- Service worker i tryb offline ----------
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
    });
  }
  function syncOnline() { document.body.classList.toggle('is-offline', !navigator.onLine); }
  window.addEventListener('online', syncOnline);
  window.addEventListener('offline', syncOnline);
  document.addEventListener('DOMContentLoaded', syncOnline);

  // ---------- Instalacja PWA (Android / Chrome) ----------
  var deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    var btn = document.getElementById('install-btn');
    if (btn) {
      btn.hidden = false;
      btn.onclick = function () { deferredPrompt.prompt(); deferredPrompt = null; btn.hidden = true; };
    }
  });

  // ---------- Status odświeżania danych ----------
  window.UBRefresh = {
    poll: function (reloadWhenDone) {
      var logBox = document.getElementById('refresh-log');
      var tick = function () {
        fetch('/api/status', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (s) {
          if (logBox && s.log) logBox.innerHTML = s.log.map(function (l) { return '<div>' + l.replace(/</g, '&lt;') + '</div>'; }).join('');
          if (s.running) { setTimeout(tick, 2500); }
          else if (reloadWhenDone) { location.reload(); }
        }).catch(function () { setTimeout(tick, 5000); });
      };
      tick();
    }
  };
  document.addEventListener('DOMContentLoaded', function () {
    if (window.UB && UB.refreshing && document.getElementById('refresh-banner')) UBRefresh.poll(true);
    else if (document.getElementById('refresh-log')) UBRefresh.poll(false);
  });

  // ---------- Web Push ----------
  function b64ToUint8(base64) {
    var padding = '='.repeat((4 - base64.length % 4) % 4);
    var raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function pushSupported() { return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window; }
  function setStatus(text) { var el = document.getElementById('push-status'); if (el) el.textContent = text; }

  function refreshPushStatus() {
    if (!document.getElementById('push-status')) return;
    if (!pushSupported()) {
      var ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
      setStatus(ios ? 'niedostępne – dodaj aplikację do ekranu początkowego (iOS 16.4+) i otwórz ją z ikony' : 'przeglądarka nie obsługuje powiadomień');
      return;
    }
    navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (sub) {
      setStatus(sub ? 'włączone ✓' : (Notification.permission === 'denied' ? 'zablokowane w ustawieniach przeglądarki' : 'wyłączone'));
    });
  }

  function subscribe() {
    if (!pushSupported()) { refreshPushStatus(); return; }
    Notification.requestPermission().then(function (perm) {
      if (perm !== 'granted') { setStatus('brak zgody na powiadomienia'); return; }
      return navigator.serviceWorker.ready.then(function (reg) {
        return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(UB.vapidKey) });
      }).then(function (sub) {
        return fetch('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub) });
      }).then(refreshPushStatus);
    }).catch(function (err) { setStatus('błąd: ' + err.message); });
  }

  function unsubscribe() {
    navigator.serviceWorker.ready.then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (sub) {
      if (!sub) return;
      return fetch('/api/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) })
        .then(function () { return sub.unsubscribe(); });
    }).then(refreshPushStatus);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var on = document.getElementById('push-on');
    if (!on) return;
    on.onclick = subscribe;
    document.getElementById('push-off').onclick = unsubscribe;
    document.getElementById('push-test').onclick = function () {
      fetch('/api/push/test', { method: 'POST' }).then(function (r) { return r.json(); }).then(function (r) {
        setStatus('wysłano testów: ' + r.sent);
      });
    };
    refreshPushStatus();
  });

  // ---------- Wykresy ----------
  var plNum = function (v, d) { return Number(v).toLocaleString('pl-PL', { maximumFractionDigits: d === undefined ? 2 : d }); };
  function baseOptions(unit) {
    return {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#8d9bb5', boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + plNum(c.parsed.y) + (unit || ''); } } }
      },
      scales: {
        x: { ticks: { color: '#8d9bb5', maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { color: 'rgba(36,50,79,.5)' } },
        y: { ticks: { color: '#8d9bb5', callback: function (v) { return plNum(v, 1) + (unit || ''); } }, grid: { color: 'rgba(36,50,79,.5)' } }
      }
    };
  }
  window.UBCharts = {
    line: function (id, labels, sets, unit) {
      var el = document.getElementById(id);
      if (!el || !window.Chart) return;
      new Chart(el, {
        type: 'line',
        data: {
          labels: labels,
          datasets: sets.map(function (s) {
            return {
              label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.fill ? 'rgba(34,197,94,.12)' : s.color,
              fill: !!s.fill, borderDash: s.dash ? [5, 4] : [], pointRadius: labels.length > 40 ? 0 : 2, borderWidth: 2, tension: .15
            };
          })
        },
        options: baseOptions(unit)
      });
    },
    bars: function (id, labels, sets) {
      var el = document.getElementById(id);
      if (!el || !window.Chart) return;
      new Chart(el, {
        data: {
          labels: labels,
          datasets: sets.map(function (s) {
            return { type: s.type, label: s.label, data: s.data, borderColor: s.color, backgroundColor: s.type === 'bar' ? 'rgba(56,189,248,.55)' : s.color, borderWidth: 2, pointRadius: 0 };
          })
        },
        options: baseOptions('')
      });
    }
  };

  // ---------- Kalkulator martingale ----------
  window.UBCalc = {
    init: function () {
      var ids = ['c-base', 'c-mult', 'c-odds', 'c-p', 'c-steps', 'c-tax'];
      var zl = function (v) { return (v < 0 ? '−' : '') + plNum(Math.abs(v)) + ' zł'; };
      var pct = function (v, d) { return plNum(v * 100, d === undefined ? 2 : d) + '%'; };
      var calc = function () {
        var b = +document.getElementById('c-base').value || 10;
        var m = +document.getElementById('c-mult').value || 2;
        var k = +document.getElementById('c-odds').value || 3;
        var p = (+document.getElementById('c-p').value || 25) / 100;
        var n = Math.min(25, Math.max(1, +document.getElementById('c-steps').value || 8));
        var tax = Math.min(50, Math.max(0, +document.getElementById('c-tax').value || 0)) / 100;
        var ke = k * (1 - tax);
        var rows = '<tr><th class="num">Krok</th><th class="num">Stawka</th><th class="num">Suma stawek</th><th class="num">Zysk netto przy remisie</th><th class="num">P(dojścia do kroku)</th><th class="num">P(remisu dokładnie tu)</th></tr>';
        var cum = 0, ev = 0, expStaked = 0;
        for (var i = 1; i <= n; i++) {
          var stake = b * Math.pow(m, i - 1);
          var reach = Math.pow(1 - p, i - 1);
          expStaked += reach * stake;
          var profit = stake * ke - stake - cum;
          cum += stake;
          ev += reach * p * profit;
          rows += '<tr><td class="num">' + i + '</td><td class="num">' + zl(stake) + '</td><td class="num">' + zl(cum) + '</td><td class="num ' + (profit > 0 ? 'pos' : 'neg') + '">' + zl(profit) + '</td><td class="num">' + pct(reach) + '</td><td class="num">' + pct(reach * p) + '</td></tr>';
        }
        var lose = Math.pow(1 - p, n);
        ev -= lose * cum;
        document.getElementById('c-table').innerHTML = rows;
        document.getElementById('k-cap').textContent = zl(cum);
        document.getElementById('k-ruin').textContent = pct(lose) + ' (1 na ' + plNum(1 / lose, 0) + ')';
        var evEl = document.getElementById('k-ev');
        evEl.textContent = zl(ev);
        evEl.className = 'value ' + (ev >= 0 ? 'pos' : 'neg');
        document.getElementById('k-ev-sub').textContent = 'EV na 1 zł stawki: ' + pct(p * ke - 1) + ' · próg opłacalności: kurs ≥ ' + plNum(1 / (p * (1 - tax)));
        document.getElementById('k-opt').textContent = ke > 1 ? plNum(ke / (ke - 1), 3) : 'kurs za niski';
      };
      ids.forEach(function (id) { document.getElementById(id).addEventListener('input', calc); });
      calc();
    }
  };
})();
