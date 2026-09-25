/* MAFI Pro v29 — ELO UI, replay, clans, season pass, admin moderation, AFK heartbeat */
(() => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");

  function token() {
    return localStorage.getItem("mafi_token") || "";
  }

  function fingerprint() {
    let fp = localStorage.getItem("mafi_fp");
    if (!fp) {
      fp = `fp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem("mafi_fp", fp);
    }
    return fp;
  }

  function bindSocket(socket) {
    if (!socket || socket.__mafiPro) return;
    socket.__mafiPro = true;

    socket.on("connect", () => {
      socket.emit("set_fingerprint", { fp: fingerprint() });
    });

    setInterval(() => {
      if (socket.connected) socket.emit("heartbeat");
    }, 25000);

    socket.on("season_pass", renderSeasonPass);
    socket.on("clan_info", renderClanInfo);
    socket.on("replay_data", onReplayData);
    socket.on("kicked", (d) => {
      alert(d?.reason || "اخراج شدید");
      if (typeof window.__mafiResetToHome === "function") window.__mafiResetToHome();
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && socket.connected) {
        socket.emit("heartbeat");
      }
    });
  }

  async function loadIceServers() {
    try {
      const r = await fetch("/api/ice");
      const d = await r.json();
      if (d.iceServers && window.VoiceChat?.setIceServers) {
        window.VoiceChat.setIceServers(d.iceServers);
      }
    } catch (_) {}
  }

  function renderSeasonPass(data) {
    const el = $("#season-pass-body");
    if (!el || !data) return;
    const tiers = data.tiers || [];
    el.innerHTML = tiers
      .map((t) => {
        const done = (data.xp || 0) >= t.xp;
        const claimed = (data.claimed || []).includes(t.reward);
        return `<div class="sp-tier ${done ? "done" : ""} ${claimed ? "claimed" : ""}">
          <span>T${t.tier}</span> ${esc(t.label)} — ${t.xp} XP
          ${claimed ? " ✓" : done ? " 🎁" : ""}
        </div>`;
      })
      .join("");
    const xpEl = $("#season-pass-xp");
    if (xpEl) xpEl.textContent = `XP: ${data.xp || 0}`;
  }

  function renderClanInfo(info) {
    const el = $("#clan-body");
    if (!el) return;
    if (!info) {
      el.innerHTML = `<p class="muted-line">عضو کلن نیستید.</p>`;
      return;
    }
    el.innerHTML = `<p><strong>[${esc(info.tag)}]</strong> ${esc(info.name)} — ${info.member_count || 0} عضو</p>
      <ul class="friends-list">${(info.members || [])
        .slice(0, 12)
        .map((m) => `<li>${esc(m.name)} (${esc(m.role)})</li>`)
        .join("")}</ul>`;
  }

  function bindClanUI(socket) {
    $("#btn-create-clan")?.addEventListener("click", () => {
      const name = prompt("نام کلن:", "")?.trim();
      const tag = prompt("تگ (۲–۶ حرف):", "")?.trim();
      if (name && tag) socket.emit("create_clan", { token: token(), name, tag });
    });
    $("#btn-join-clan")?.addEventListener("click", () => {
      const id = prompt("شناسه کلن:", "")?.trim();
      if (id) socket.emit("join_clan", { token: token(), clan_id: id });
    });
    $("#btn-leave-clan")?.addEventListener("click", () => {
      socket.emit("leave_clan", { token: token() });
    });
  }

  function bindReplayUI(socket) {
    $("#match-history-list")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-replay-id]");
      if (!btn) return;
      socket.emit("get_replay", { match_id: parseInt(btn.dataset.replayId, 10) });
    });
  }

  function onReplayData(d) {
    if (!d?.ok || !d.replay) {
      alert("ریپلی پیدا نشد");
      return;
    }
    const modal = $("#modal-replay");
    const body = $("#replay-body");
    if (!modal || !body) return;
    const tl = d.replay.timeline || [];
    body.innerHTML = `<p>اتاق ${esc(d.replay.room_code)} — برنده: ${esc(d.replay.winner)}</p>
      <div class="replay-controls">
        <button type="button" class="btn btn-gold btn-sm" id="replay-play">▶ پخش</button>
        <button type="button" class="btn btn-ghost btn-sm" id="replay-stop">⏹</button>
      </div>
      <div id="replay-stage" class="replay-stage"></div>
      <ol id="replay-timeline" class="replay-timeline">${tl
        .map((e) => `<li data-kind="${esc(e.kind)}">${esc(e.text || e.kind)}</li>`)
        .join("")}</ol>`;
    modal.classList.add("show");
    let idx = 0;
    let timer = null;
    $("#replay-play")?.addEventListener("click", () => {
      const stage = $("#replay-stage");
      if (!stage) return;
      clearInterval(timer);
      idx = 0;
      timer = setInterval(() => {
        if (idx >= tl.length) {
          clearInterval(timer);
          return;
        }
        stage.textContent = tl[idx].text || tl[idx].kind;
        idx += 1;
      }, 1200);
    });
    $("#replay-stop")?.addEventListener("click", () => clearInterval(timer));
  }

  function extendAdminPanel() {
    const tabs = document.querySelector(".admin-tabs");
    if (!tabs || tabs.querySelector('[data-atab="reports"]')) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "admin-tab";
    btn.dataset.atab = "reports";
    btn.textContent = "گزارش‌ها";
    tabs.appendChild(btn);
    const panel = document.createElement("div");
    panel.id = "admin-reports";
    panel.className = "admin-suspect";
    panel.style.display = "none";
    $("#admin-body")?.appendChild(panel);
    btn.addEventListener("click", () => {
      document.querySelectorAll(".admin-tab").forEach((t) => t.classList.remove("on"));
      btn.classList.add("on");
      ["admin-roles", "admin-timeline", "admin-suspect", "admin-whisper", "admin-reports"].forEach(
        (id) => {
          const el = document.getElementById(id);
          if (el) el.style.display = id === "admin-reports" ? "block" : "none";
        }
      );
    });
    window.__mafiRenderAdminReports = (reports) => {
      const el = $("#admin-reports");
      if (!el) return;
      el.innerHTML =
        (reports || [])
          .map(
            (r) =>
              `<div class="atl"><b>${esc(r.target)}</b> توسط ${esc(r.reporter)} — ${esc(r.reason || "")}
              <button type="button" class="btn btn-ghost btn-sm" data-ban-target="${esc(r.target)}">مسدود</button></div>`
          )
          .join("") || "<div class='atl'>گزارشی نیست</div>";
      el.querySelectorAll("[data-ban-target]").forEach((b) => {
        b.onclick = () => {
          const tkn = prompt("توکن بازیکن برای مسدود:", "");
          const pw = window.__mafiAdminPass || prompt("رمز ادمین:", "");
          if (tkn && pw && window.__mafiSocket) {
            window.__mafiSocket.emit("admin_ban", {
              token: tkn,
              reason: `گزارش: ${b.dataset.banTarget}`,
              hours: 24,
              password: pw,
            });
          }
        };
      });
    };
    const orig = window.__mafiOnAdminAuth;
    window.__mafiOnAdminAuth = (d) => {
      if (orig) orig(d);
      if (d?.reports) window.__mafiRenderAdminReports(d.reports);
    };
  }

  function enhanceProfile(socket) {
    const openProfile = $("#btn-profile");
    openProfile?.addEventListener("click", () => {
      socket.emit("get_season_pass", { token: token() });
      socket.emit("get_clan", { token: token() });
    });
  }

  function enhanceMatchHistory(list) {
    if (!list?.length) return;
    const ul = $("#match-history-list");
    if (!ul) return;
    ul.innerHTML = list
      .map(
        (m) =>
          `<li><button type="button" class="btn btn-ghost btn-sm" data-replay-id="${m.id || ""}">
            ${esc(m.room_code)} — ${esc(m.winner)} (${new Date((m.created_at || 0) * 1000).toLocaleDateString("fa-IR")})
          </button></li>`
      )
      .join("");
  }

  window.__mafiEnhanceMatchHistory = enhanceMatchHistory;

  function handleDeepLink() {
    const params = new URLSearchParams(location.search);
    const room = params.get("room") || params.get("code");
    if (room) {
      sessionStorage.setItem("mafi_room", room.toUpperCase());
      const joinInput = document.getElementById("join-code");
      if (joinInput) joinInput.value = room.toUpperCase();
    }
  }

  function init() {
    handleDeepLink();
    loadIceServers();
    extendAdminPanel();
    window.addEventListener("mafi:socket", (ev) => {
      const socket = ev.detail;
      bindSocket(socket);
      bindClanUI(socket);
      bindReplayUI(socket);
      enhanceProfile(socket);
    });
    if (window.__mafiSocket) bindSocket(window.__mafiSocket);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
