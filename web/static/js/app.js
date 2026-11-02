const $ = (id) => document.getElementById(id);
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit" });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let map, trackLayer, hitLayer, selected = null;

function initMap() {
  map = L.map("map").setView([50.0755, 14.4378], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "© OpenStreetMap",
  }).addTo(map);
  trackLayer = L.layerGroup().addTo(map);
  hitLayer = L.layerGroup().addTo(map);
}

async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

async function send(method, url, body) {
  const r = await fetch(url, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `chyba ${r.status}`);
  return data;
}

function say(msg) {
  $("calib-msg").textContent = msg;
}
function personRow(p) {
  const tr = document.createElement("tr");
  if (p.suspicious) tr.classList.add("susp");
  const key = p.cluster_id ? `c${p.cluster_id}` : p.devices[0].mac;
  if (key === selected) tr.classList.add("selected");

  const label = p.cluster_id
    ? `Osoba #${p.cluster_id}<span class="tag group">${p.devices.length} zařízení</span>`
    : "Jednotlivé zařízení";
  const devs = p.devices.map((d) =>
    `<span class="mac">${esc(d.mac)}<span class="tag src">${d.source}</span>${d.randomized ? '<span class="tag src">náhodná MAC</span>' : ""}</span>`
  ).join("");
  const pct = Math.round(p.score * 100);

  tr.innerHTML = `
    <td>${label}${p.suspicious ? '<span class="tag susp">podezřelé</span>' : ""}</td>
    <td>${devs}</td>
    <td>${p.score.toFixed(2)}<div class="bar"><i style="width:${pct}%"></i></div></td>
    <td>${p.sightings}</td>
    <td>${fmtTime(p.last_seen)}</td>
    <td><button class="btn small" title="Přidat na seznam ignorovaných">Ignorovat</button></td>`;
  tr.addEventListener("click", () => { selected = key; showPerson(p); refreshPersons(); });
  tr.querySelector("button").addEventListener("click", async (e) => {
    e.stopPropagation();
    const macs = p.devices.map((d) => d.mac);
    try {
      await send("POST", "/api/ignored", { macs, label: "z přehledu" });
      say(`Ignorováno: ${macs.join(", ")}`);
      if (selected === key) { selected = null; hitLayer.clearLayers(); }
      refreshAll();
    } catch (err) { say(err.message); }
  });
  return tr;
}

async function showPerson(p) {
  hitLayer.clearLayers();
  const color = p.suspicious ? "#dc2626" : "#7c3aed";
  const pts = [];
  for (const d of p.devices) {
    const rows = await getJSON(`/api/device/${encodeURIComponent(d.mac)}`);
    for (const r of rows) {
      if (r.lat == null) continue;
      pts.push([r.lat, r.lon]);
      L.circleMarker([r.lat, r.lon], { radius: 6, color, fillOpacity: 0.6 })
        .bindTooltip(`${esc(d.mac)} · ${fmtTime(r.ts)}${r.rssi != null ? ` · ${r.rssi} dBm` : ""}`)
        .addTo(hitLayer);
    }
  }
  $("map-hint").textContent = pts.length
    ? `${p.cluster_id ? "Osoba #" + p.cluster_id : p.devices[0].mac}: ${pts.length} výskytů s GPS`
    : "Pro tuto osobu nejsou GPS záznamy.";
  if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 16 });
}

async function refreshPersons() {
  const only = $("only-susp").checked ? "?suspicious=1" : "";
  const persons = await getJSON(`/api/persons${only}`);
  const tbody = $("persons");
  tbody.replaceChildren(...persons.slice(0, 60).map(personRow));
  if (!persons.length) tbody.innerHTML = '<tr><td colspan="6" class="muted">Zatím nic.</td></tr>';
}

async function refreshTrack() {
  const pts = await getJSON("/api/track?hours=2");
  trackLayer.clearLayers();
  if (!pts.length) return;
  const latlngs = pts.map((p) => [p.lat, p.lon]).reverse();
  L.polyline(latlngs, { color: "#2563eb", weight: 3, opacity: 0.6 }).addTo(trackLayer);
  L.circleMarker(latlngs[latlngs.length - 1], { radius: 7, color: "#2563eb", fillOpacity: 1 })
    .bindTooltip("Vy").addTo(trackLayer);
  if (!selected) map.fitBounds(latlngs, { padding: [30, 30], maxZoom: 16 });
}

async function refreshStats() {
  const s = await getJSON("/api/stats");
  $("s-devices").textContent = s.devices;
  $("s-persons").textContent = s.persons;
  $("s-groups").textContent = s.groups;
  $("s-suspicious").textContent = s.suspicious;
  $("s-ignored").textContent = s.ignored;
}

let ambientCount = 0;
async function refreshAmbient() {
  const m = $("amb-minutes").value;
  const a = await getJSON(`/api/ambient?minutes=${m}`);
  ambientCount = a.count;
  $("amb-count").innerHTML = `<b>${a.count}</b> zařízení k odrušení`;
  $("amb-ignore").disabled = a.count === 0;
}

const SOURCE = { baseline: "odrušení", manual: "ručně" };
async function refreshIgnored() {
  const rows = await getJSON("/api/ignored");
  $("ign-count").textContent = rows.length;
  const tbody = $("ignored");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">Seznam je prázdný.</td></tr>';
    return;
  }
  tbody.replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><span class="mac">${esc(r.mac)}</span></td><td>${esc(r.label || "")}</td>
      <td>${SOURCE[r.source] || esc(r.source)}</td>
      <td>${new Date(r.added_at * 1000).toLocaleString("cs-CZ", { dateStyle: "short", timeStyle: "short" })}</td>
      <td><button class="btn small">Vrátit</button></td>`;
    tr.querySelector("button").addEventListener("click", async () => {
      await send("DELETE", `/api/ignored/${encodeURIComponent(r.mac)}`);
      say(`${r.mac} se znovu vyhodnocuje.`);
      refreshAll();
    });
    return tr;
  }));
}

$("amb-minutes").addEventListener("change", refreshAmbient);

$("amb-ignore").addEventListener("click", async () => {
  const sel = $("amb-minutes");
  const label = sel.options[sel.selectedIndex].text;
  if (!confirm(`Ignorovat ${ambientCount} zařízení viděných za ${label}?\n\n` +
    "Udělejte to ve chvíli, kdy jste v klidu a v okolí jsou jen známá zařízení.")) return;
  try {
    const r = await send("POST", "/api/ambient/ignore", { minutes: Number(sel.value) });
    say(`Odrušeno ${r.added} zařízení. Od teď se vyhodnocuje jen to, co přibude.`);
    refreshAll();
  } catch (err) { say(err.message); }
});

$("amb-clear").addEventListener("click", async () => {
  if (!confirm("Zrušit odrušení? Zařízení přidaná ručně na seznamu zůstanou.")) return;
  const r = await send("DELETE", "/api/ambient");
  say(`Vráceno ${r.removed} zařízení z odrušení.`);
  refreshAll();
});

$("ign-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await send("POST", "/api/ignored", { macs: [$("ign-mac").value], label: $("ign-label").value });
    say(`${$("ign-mac").value.trim().toUpperCase().replaceAll("-", ":")} přidáno na seznam ignorovaných.`);
    $("ign-mac").value = ""; $("ign-label").value = "";
    refreshAll();
  } catch (err) { say(err.message === "neplatná MAC adresa" ? "Neplatná MAC adresa, formát AA:BB:CC:DD:EE:FF." : err.message); }
});

async function refreshAlerts() {
  const alerts = await getJSON("/api/alerts");
  $("alerts").innerHTML = alerts.length
    ? alerts.map((a) => `<li><time>${new Date(a.ts * 1000).toLocaleString("cs-CZ")}</time>${esc(a.message)}</li>`).join("")
    : '<li class="muted">Žádná upozornění.</li>';
}

async function refreshAll() {
  try {
    await Promise.all([refreshStats(), refreshPersons(), refreshAlerts(), refreshTrack(),
      refreshAmbient(), refreshIgnored()]);
    $("updated").textContent = "aktualizováno " + new Date().toLocaleTimeString("cs-CZ");
  } catch (e) {
    $("updated").textContent = "nelze načíst data";
  }
}

initMap();
$("only-susp").addEventListener("change", refreshPersons);
refreshAll();
setInterval(refreshAll, 10000);
