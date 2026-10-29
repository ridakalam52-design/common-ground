(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const COLORS = ["var(--f1)", "var(--f2)", "var(--f3)", "var(--f4)", "var(--f5)"];
  const SLOT_EMOJI = { watch: "🎬", soundtrack: "🎧", dinner: "🍽️" };
  const TOOL_LABEL = {
    resolve_picks: "GET /search", search_entity: "GET /search", compare_friends: "GET /v2/analysis/compare",
    find_tags: "GET /v2/tags", get_recommendations: "GET /v2/insights", finalize_plan: "Gemini",
  };
  const friendsEl = $("#friends");
  const tpl = $("#friendTpl");
  let colorOf = {};

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const initials = (n) => (n || "?").trim().split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const fmt = (v) => (typeof v === "number" ? v.toFixed(2) : "n/a");

  // ------------------------------------------------------------ form
  function addChip(box, text) {
    text = text.trim().replace(/,$/, "");
    if (!text) return;
    if (box.querySelectorAll(".chip").length >= 6) return;
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `<span>${esc(text)}</span><button type="button" aria-label="Remove ${esc(text)}">×</button>`;
    chip.dataset.value = text;
    chip.querySelector("button").onclick = () => chip.remove();
    box.insertBefore(chip, box.querySelector(".chip-input"));
  }

  function refreshAvatars() {
    [...friendsEl.children].forEach((f, i) => {
      const av = $(".avatar", f);
      av.style.setProperty("--c", COLORS[i % COLORS.length]);
      av.textContent = initials($(".fname", f).value || `F${i + 1}`);
      $(".remove", f).disabled = friendsEl.children.length <= 2;
      $(".remove", f).style.visibility = friendsEl.children.length <= 2 ? "hidden" : "visible";
    });
    $("#addFriend").disabled = friendsEl.children.length >= 5;
  }

  function addFriend(name = "", picks = []) {
    if (friendsEl.children.length >= 5) return;
    const node = tpl.content.firstElementChild.cloneNode(true);
    const input = $(".chip-input", node);
    const box = $(".chips", node);
    $(".fname", node).value = name;
    $(".fname", node).addEventListener("input", refreshAvatars);
    picks.forEach((p) => addChip(box, p));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addChip(box, input.value); input.value = ""; }
      else if (e.key === "Backspace" && !input.value) { const last = [...box.querySelectorAll(".chip")].pop(); last && last.remove(); }
    });
    input.addEventListener("blur", () => { addChip(box, input.value); input.value = ""; });
    input.addEventListener("paste", (e) => {
      const t = (e.clipboardData || window.clipboardData).getData("text");
      if (t.includes(",")) { e.preventDefault(); t.split(",").forEach((p) => addChip(box, p)); }
    });
    box.addEventListener("click", (e) => { if (e.target === box) input.focus(); });
    $(".remove", node).onclick = () => { node.remove(); refreshAvatars(); };
    friendsEl.appendChild(node);
    refreshAvatars();
  }

  function loadExample(ex) {
    friendsEl.innerHTML = "";
    $("#city").value = ex.city;
    ex.friends.forEach((f) => addFriend(f.name, f.picks));
  }

  function readForm() {
    const friends = [...friendsEl.children].map((f) => ({
      name: $(".fname", f).value.trim(),
      picks: [...f.querySelectorAll(".chip")].map((c) => c.dataset.value),
    }));
    const city = $("#city").value.trim();
    const names = friends.map((f) => f.name.toLowerCase());
    if (friends.length < 2) return { error: "Add at least two friends." };
    if (friends.some((f) => !f.name)) return { error: "Every friend needs a name." };
    if (new Set(names).size !== names.length) return { error: "Friend names need to be different." };
    if (friends.some((f) => !f.picks.length)) return { error: "Every friend needs at least one thing they love." };
    if (!city) return { error: "Add a city for dinner." };
    return { body: { city, friends } };
  }

  // ----------------------------------------------------------- trace
  const steps = {};
  function traceItem(ev) {
    const list = $("#trace");
    if (ev.type === "step") {
      let li = steps[ev.id];
      if (!li) {
        li = document.createElement("li");
        li.innerHTML = `<span class="dot"></span><div><div><span class="tool"></span><span class="by"></span><span class="ms"></span></div><div class="sum"></div><ul class="http"></ul></div>`;
        steps[ev.id] = li;
        list.appendChild(li);
        const args = Object.entries(ev.args || {}).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
        $(".tool", li).textContent = `${ev.tool}(${args})`;
        $(".by", li).textContent = `${ev.by === "gemini" ? "planned by Gemini" : "scripted"} · ${TOOL_LABEL[ev.tool] || ""}`;
      }
      li.className = ev.status === "running" ? "running" : ev.status === "error" ? "error" : "";
      $(".dot", li).textContent = ev.status === "done" ? "✓" : ev.status === "error" ? "!" : "";
      if (ev.summary) $(".sum", li).textContent = ev.summary;
      if (ev.ms != null && ev.status !== "running") $(".ms", li).textContent = `${ev.ms} ms`;
    } else if (ev.type === "http") {
      const li = steps[ev.step];
      if (li) {
        const qs = Object.entries(ev.params || {}).map(([k, v]) => `${k}=${v}`).join("&");
        const row = document.createElement("li");
        row.innerHTML = `<code>${esc(ev.method)} ${esc(ev.path)}?${esc(qs)}</code>`;
        $(".http", li).appendChild(row);
      }
    } else if (ev.type === "thought" || ev.type === "note" || ev.type === "error") {
      const li = document.createElement("li");
      li.className = ev.type;
      li.innerHTML = `<span class="dot">${ev.type === "thought" ? "✦" : "!"}</span><div class="sum">${esc(ev.text || ev.message)}${ev.model ? ` <span class="by">${esc(ev.model)}</span>` : ""}</div>`;
      list.appendChild(li);
    }
    list.scrollTop = list.scrollHeight;
  }

  // --------------------------------------------------------- results
  function dots(friends) {
    return `<span class="mini-dots">${friends.map((f) => `<i style="--c:${colorOf[f] || "var(--muted)"}" title="${esc(f)}"></i>`).join("")}</span>`;
  }
  function signalChips(s) {
    const out = [];
    if (typeof s.affinity === "number") out.push(`<span class="sig aff" title="Qloo affinity against everyone's combined picks">affinity ${fmt(s.affinity)}</span>`);
    (s.shared_tags || []).slice(0, 3).forEach((t) => out.push(`<span class="sig tag" title="Shared tag from /v2/analysis/compare">${dots(t.friends)} ${esc(t.name)}${t.score != null ? ` · ${fmt(t.score)}` : ""}</span>`));
    (s.drivers || []).slice(0, 2).forEach((d) => out.push(`<span class="sig" title="Qloo explainability: this pick contributed to the result">${dots([d.friend])} ${esc(d.pick)} · ${fmt(d.score)}</span>`));
    return out.join("");
  }
  function metaLine(p) {
    const bits = [];
    if (p.type) bits.push(p.type.split(":").pop().replace("_", " "));
    if (p.year) bits.push(p.year);
    if (p.address) bits.push(p.address);
    if (p.price_level) bits.push("₹".repeat(p.price_level));
    return bits.map(esc).join(" · ");
  }
  function renderPlan(plan) {
    colorOf = {};
    plan.friends.forEach((f, i) => (colorOf[f] = COLORS[i % COLORS.length]));
    $("#results").classList.remove("hidden");
    $("#resultEyebrow").textContent = `Your evening in ${plan.locality || plan.city}`;
    $("#summary").textContent = plan.summary;
    const un = Object.entries(plan.unresolved || {}).map(([f, l]) => `${f}: ${l.join(", ")}`);
    $("#unresolved").textContent = un.length ? `Qloo couldn't match: ${un.join(" · ")}` : "";
    $("#unresolved").classList.toggle("hidden", !un.length);

    $("#slots").innerHTML = Object.entries(plan.slots).map(([key, slot]) => {
      const p = slot.pick;
      if (!p) return `<article class="card slot"><div class="slot-label"><span class="emoji">${SLOT_EMOJI[key]}</span>${esc(slot.label)}</div><p class="muted">Qloo returned nothing for this slot.</p></article>`;
      const pct = Math.round(Math.min(1, p.group_score || 0) * 100);
      return `<article class="card slot">
        <div class="slot-label"><span class="emoji">${SLOT_EMOJI[key]}</span>${esc(slot.label)}</div>
        <div><h3 class="pick-name">${esc(p.name)}</h3><p class="pick-meta">${metaLine(p)}</p></div>
        <div class="meter" title="Group score ${fmt(p.group_score)}"><span style="width:${pct}%"></span></div>
        <p class="why">${esc(p.why)}</p>
        <div class="signals">${signalChips(p.signals || {})}</div>
        <span class="why-src">why written by ${p.why_source === "gemini" ? "Gemini" : "template"} from Qloo signals</span>
        <div class="alts"><h4>Alternates</h4>${slot.alternates.map((a) => `<div class="alt"><strong>${esc(a.name)}</strong><p class="pick-meta">${metaLine(a)}</p><p>${esc(a.why)}</p></div>`).join("") || '<p class="muted small">No alternates returned.</p>'}</div>
      </article>`;
    }).join("");

    const ov = plan.overlap || { pairs: [], tags: [] };
    $("#pairs").innerHTML = ov.pairs.map((pr) => `<div class="pair">
        <div class="pair-top"><span class="avatar" style="--c:${colorOf[pr.a]}">${esc(initials(pr.a))}</span><span class="avatar" style="--c:${colorOf[pr.b]}">${esc(initials(pr.b))}</span>${esc(pr.a)} × ${esc(pr.b)}</div>
        <div class="pair-tags">${pr.shared.length ? pr.shared.slice(0, 4).map((t) => esc(t.name)).join(" · ") : "No shared tags"}</div>
        <div class="meter" style="margin-top:8px" title="Average of top shared-tag scores: ${fmt(pr.strength)}"><span style="width:${Math.round((pr.strength || 0) * 100)}%"></span></div>
      </div>`).join("");
    if (!ov.tags.length) { $("#overlap").innerHTML = '<p class="muted">Qloo found no shared tags between these friends.</p>'; return; }
    $("#overlap").innerHTML = `<table class="otable"><thead><tr><th>Shared tag</th>${plan.friends.map((f) => `<th title="${esc(f)}">${esc(f)}</th>`).join("")}<th>Score</th></tr></thead><tbody>
      ${ov.tags.slice(0, 14).map((t) => `<tr><td>${esc(t.name)}</td>${plan.friends.map((f) => `<td><span class="cell ${t.friends.includes(f) ? "" : "off"}" style="--c:${colorOf[f]}" aria-label="${t.friends.includes(f) ? "shared by" : "not"} ${esc(f)}"></span></td>`).join("")}<td class="score">${fmt(t.score)}</td></tr>`).join("")}
    </tbody></table>`;
  }

  // ------------------------------------------------------------- run
  async function run(body) {
    const btn = $("#goBtn");
    btn.disabled = true; btn.textContent = "Planning…";
    Object.keys(steps).forEach((k) => delete steps[k]);
    $("#trace").innerHTML = "";
    $("#traceCard").classList.remove("hidden");
    $("#results").classList.add("hidden");
    $("#traceStatus").textContent = "working…";
    $("#traceCard").scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const res = await fetch("/api/plan/stream", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail?.[0]?.msg || `Request failed (${res.status})`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          if (chunk.startsWith("event: done")) continue;
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.type === "start") {
            $("#plannerTag").textContent = ev.planner === "gemini" ? "Gemini plans the calls" : "scripted planner";
            $("#modeBadge").classList.toggle("hidden", ev.mode !== "mock");
          } else if (ev.type === "plan") {
            renderPlan(ev.plan);
          } else traceItem(ev);
        }
      }
      $("#traceStatus").textContent = `${Object.keys(steps).length} steps`;
      $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      traceItem({ type: "error", message: err.message });
      $("#traceStatus").textContent = "stopped";
    } finally {
      btn.disabled = false; btn.textContent = "Plan our evening";
    }
  }

  // ------------------------------------------------------------ init
  $("#planForm").addEventListener("submit", (e) => {
    e.preventDefault();
    [...friendsEl.querySelectorAll(".chip-input")].forEach((inp) => { if (inp.value.trim()) { addChip(inp.parentElement, inp.value); inp.value = ""; } });
    const { body, error } = readForm();
    $("#formError").textContent = error || "";
    $("#formError").classList.toggle("hidden", !error);
    if (body) run(body);
  });
  $("#addFriend").onclick = () => addFriend();
  let example = null;
  $("#exampleBtn").onclick = () => example && loadExample(example);
  fetch("/api/health").then((r) => r.json()).then((h) => $("#modeBadge").classList.toggle("hidden", h.mode !== "mock")).catch(() => {});
  fetch("/api/example").then((r) => r.json()).then((ex) => { example = ex; loadExample(ex); })
    .catch(() => { addFriend(); addFriend(); });
})();
