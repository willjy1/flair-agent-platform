(function () {
  const els = {
    groups: document.getElementById("groups"),
    search: document.getElementById("searchInput"),
    status: document.getElementById("statusText"),
    copyAllBtn: document.getElementById("copyAllBtn"),
    cardTemplate: document.getElementById("cardTemplate"),
  };

  let demos = [];

  const verticalLabels = {
    travel: "Travel & Transport",
    insurance: "Insurance",
    health: "Health Plans",
    utilities: "Utilities",
    telecom: "Telecom",
    isp: "Telecom / ISP",
    parcel: "Parcel & Logistics",
    logistics: "Parcel & Logistics",
  };

  function absoluteUrl(path) {
    return new URL(path, window.location.origin).toString();
  }

  function hexToRgb(hex) {
    const clean = String(hex || "").replace("#", "").trim();
    if (clean.length !== 6) return null;
    const n = Number.parseInt(clean, 16);
    if (Number.isNaN(n)) return null;
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  function cardAccentStyle(theme) {
    const accent = theme?.accent || "#1262ff";
    const accent2 = theme?.accent_2 || "#0f172a";
    const rgb = hexToRgb(accent);
    const tint = rgb ? `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.08)` : "rgba(18, 98, 255, 0.08)";
    return {
      borderImage: `linear-gradient(180deg, ${accent}, ${accent2}) 1`,
      background: `linear-gradient(180deg, ${tint} 0%, rgba(255,255,255,1) 26%)`,
    };
  }

  function groupKey(demo) {
    const key = String(demo.vertical || "other").toLowerCase();
    return key;
  }

  function groupTitle(key) {
    return verticalLabels[key] || key.replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase());
  }

  function filterDemos(items, query) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return items;
    return items.filter((d) => {
      const hay = [
        d.display_name,
        d.brand_name,
        d.vertical,
        d.category,
        d.hero_title,
        d.hero_subtitle,
        d.slug,
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }

  function render() {
    const filtered = filterDemos(demos, els.search?.value || "");
    const groups = new Map();
    filtered.forEach((demo) => {
      const key = groupKey(demo);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(demo);
    });

    els.groups.innerHTML = "";
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No demos match your filter.";
      els.groups.appendChild(empty);
      els.status.textContent = "0 demos shown";
      return;
    }

    Array.from(groups.entries()).forEach(([key, items]) => {
      const section = document.createElement("section");
      section.className = "group";

      const head = document.createElement("div");
      head.className = "group-head";
      head.innerHTML = `<h2>${groupTitle(key)}</h2><span class="count">${items.length} demo${items.length === 1 ? "" : "s"}</span>`;
      section.appendChild(head);

      const cards = document.createElement("div");
      cards.className = "cards";

      items.forEach((demo) => {
        const frag = els.cardTemplate.content.cloneNode(true);
        const card = frag.querySelector(".demo-card");
        const mark = frag.querySelector(".mark");
        const title = frag.querySelector(".title");
        const meta = frag.querySelector(".meta");
        const tagline = frag.querySelector(".tagline");
        const path = frag.querySelector(".path");
        const openLink = frag.querySelector(".open-link");
        const copyBtn = frag.querySelector(".copy-link");

        const fullUrl = absoluteUrl(demo.route_path);
        const theme = demo.brand_theme || {};
        const style = cardAccentStyle(theme);
        card.style.background = style.background;
        card.style.borderTop = `2px solid ${theme.accent || "#1262ff"}`;
        mark.style.background = theme.brand_dark || "#101828";
        mark.textContent = String(demo.brand_mark || demo.brand_name || "S").slice(0, 2);

        title.textContent = demo.brand_name || demo.display_name || demo.slug;
        meta.textContent = `${groupTitle(groupKey(demo))}${demo.category ? ` • ${String(demo.category).replaceAll("_", " ")}` : ""}`;
        tagline.textContent = demo.hero_title || demo.hero_subtitle || "Customer-facing support demo";
        path.textContent = fullUrl;
        openLink.href = fullUrl;
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(fullUrl);
            copyBtn.textContent = "Copied";
            window.setTimeout(() => { copyBtn.textContent = "Copy Link"; }, 1200);
          } catch (_) {
            copyBtn.textContent = "Copy failed";
            window.setTimeout(() => { copyBtn.textContent = "Copy Link"; }, 1200);
          }
        });

        cards.appendChild(frag);
      });

      section.appendChild(cards);
      els.groups.appendChild(section);
    });

    els.status.textContent = `${filtered.length} demo${filtered.length === 1 ? "" : "s"} shown`;
  }

  async function loadCatalog() {
    els.status.textContent = "Loading demos...";
    try {
      const resp = await fetch("/api/v1/demos/catalog");
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error("catalog_unavailable");
      demos = Array.isArray(data.demos) ? data.demos : [];
      render();
    } catch (_) {
      els.groups.innerHTML = '<div class="empty">Could not load the demo directory right now. Reload the page and try again.</div>';
      els.status.textContent = "Unavailable";
    }
  }

  async function copyAllLinks() {
    const lines = demos.map((d) => `${d.brand_name || d.display_name}: ${absoluteUrl(d.route_path)}`);
    if (!lines.length) return;
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      els.copyAllBtn.textContent = "Copied All Links";
      window.setTimeout(() => { els.copyAllBtn.textContent = "Copy All Links"; }, 1400);
    } catch (_) {
      els.copyAllBtn.textContent = "Copy Failed";
      window.setTimeout(() => { els.copyAllBtn.textContent = "Copy All Links"; }, 1400);
    }
  }

  els.search?.addEventListener("input", render);
  els.copyAllBtn?.addEventListener("click", copyAllLinks);
  loadCatalog();
})();
