/* MAFI v28 — tutorial, battery, a11y, PTT, reconnect, friends, reports, export */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const KEY = {
    tutorial: "mafi_tutorial_done_v28",
    battery: "mafi_battery_v28",
    a11y: "mafi_a11y_v28",
    ptt: "mafi_ptt_v28",
  };

  function toast(msg) {
    if (typeof window.__mafiToast === "function") window.__mafiToast(msg, "info");
  }

  function bindTutorial() {
    if (localStorage.getItem(KEY.tutorial)) return;
    const steps = [
      "به MAFI خوش آمدید! اتاق بسازید یا با کد وارد شوید.",
      "حداقل ۶ نفر لازم است. میزبان بازی را شروع می‌کند.",
      "شب نقش خود را انجام دهید؛ روز بحث و رأی بگیرید.",
      "از QR دعوت برای دوستان استفاده کنید.",
    ];
    let i = 0;
    const box = document.createElement("div");
    box.id = "tutorial-overlay";
    box.className = "tutorial-overlay";
    box.innerHTML = `<div class="tutorial-card"><p id="tutorial-text"></p><button type="button" class="btn btn-gold" id="tutorial-next">بعدی</button></div>`;
    document.body.appendChild(box);
    const txt = $("#tutorial-text", box);
    const next = $("#tutorial-next", box);
    const show = () => {
      txt.textContent = steps[i];
      next.textContent = i >= steps.length - 1 ? "شروع!" : "بعدی";
    };
    show();
    next.onclick = () => {
      i++;
      if (i >= steps.length) {
        localStorage.setItem(KEY.tutorial, "1");
        box.remove();
        return;
      }
      show();
    };
  }

  function applyBattery(on) {
    document.documentElement.dataset.battery = on ? "1" : "0";
    localStorage.setItem(KEY.battery, on ? "1" : "0");
    if (window.Scene3D?.setQuality) window.Scene3D.setQuality(on ? "low" : "medium");
    if (window.AudioSys?.setAmbientVolume) window.AudioSys.setAmbientVolume(on ? 0.15 : 0.45);
  }

  function applyA11y(mode) {
    document.documentElement.dataset.a11y = mode || "";
    localStorage.setItem(KEY.a11y, mode || "");
  }

  function bindSettingsExtras() {
    const bat = $("#set-battery");
    if (bat) {
      bat.checked = localStorage.getItem(KEY.battery) === "1";
      bat.onchange = () => applyBattery(bat.checked);
      if (bat.checked) applyBattery(true);
    }
    const a11y = $("#set-a11y");
    if (a11y) {
      a11y.value = localStorage.getItem(KEY.a11y) || "";
      a11y.onchange = () => applyA11y(a11y.value);
      applyA11y(a11y.value);
    }
    const ptt = $("#set-ptt");
    if (ptt) {
      ptt.checked = localStorage.getItem(KEY.ptt) === "1";
      ptt.onchange = () => {
        localStorage.setItem(KEY.ptt, ptt.checked ? "1" : "0");
        if (window.VoiceChat?.setPttMode) window.VoiceChat.setPttMode(ptt.checked);
      };
      if (ptt.checked && window.VoiceChat?.setPttMode) window.VoiceChat.setPttMode(true);
    }
  }

  function bindReconnectBanner() {
    window.addEventListener("mafi:socket", (ev) => {
      const socket = ev.detail;
      if (!socket) return;
      let banner = $("#reconnect-banner");
      if (!banner) {
        banner = document.createElement("div");
        banner.id = "reconnect-banner";
        banner.className = "reconnect-banner hidden";
        banner.textContent = "در حال اتصال مجدد...";
        document.body.appendChild(banner);
      }
      socket.on("disconnect", () => banner.classList.remove("hidden"));
      socket.on("connect", () => banner.classList.add("hidden"));
      socket.on("kicked", () => {
        toast("از اتاق اخراج شدید");
        location.href = "/";
      });
    });
  }

  function bindClientErrors() {
    window.onerror = (msg, src, line, col, err) => {
      fetch("/api/client-error", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: String(msg),
          detail: `${src}:${line}:${col} ${err?.stack || ""}`.slice(0, 2000),
          token: localStorage.getItem("mafi_token") || "",
        }),
      }).catch(() => {});
    };
  }

  function bindAdminExport() {
    const btn = $("#btn-admin-export");
    btn?.addEventListener("click", async () => {
      const code = window.__mafiRoomCode || "";
      if (!code) return toast("کد اتاق نیست");
      try {
        const res = await fetch(`/api/admin/export?code=${encodeURIComponent(code)}&password=mafi`);
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `mafi-${code}.json`;
        a.click();
      } catch (_) {
        toast("خطا در export");
      }
    });
  }

  function bindFriendsHome() {
    const btn = $("#btn-friends-refresh");
    btn?.addEventListener("click", () => {
      window.__mafiSocket?.emit("get_friends", { token: localStorage.getItem("mafi_token") });
    });
    window.addEventListener("mafi:socket", (ev) => {
      ev.detail?.on("friends", (d) => {
        const ul = $("#friends-list");
        if (!ul) return;
        ul.innerHTML = (d.rows || [])
          .map((f) => `<li>${f.name || f.token?.slice(0, 8)}</li>`)
          .join("") || "<li>دوستی ثبت نشده</li>";
      });
      ev.detail?.on("matches", (d) => {
        if (window.__mafiEnhanceMatchHistory) {
          window.__mafiEnhanceMatchHistory(d.rows || []);
          return;
        }
        const ul = $("#match-history-list");
        if (!ul) return;
        ul.innerHTML = (d.rows || [])
          .slice(0, 8)
          .map(
            (m) =>
              `<li>${m.mode || "?"} · برنده ${m.winner || "?"} · ${new Date((m.created_at || 0) * 1000).toLocaleDateString("fa-IR")}</li>`
          )
          .join("") || "<li>هنوز بازی ثبت نشده</li>";
      });
    });
  }

  function bindCreatorTemplates() {
    $("#btn-save-template")?.addEventListener("click", () => {
      const name = prompt("نام قالب:", "پیش‌فرض");
      if (name) window.__mafiSocket?.emit("save_template", { name });
    });
    $("#btn-load-templates")?.addEventListener("click", () => {
      window.__mafiSocket?.emit("load_templates", { token: localStorage.getItem("mafi_token") });
      window.__mafiSocket?.once("templates", (d) => {
        const names = (d.rows || []).map((r) => r.name).join("، ");
        toast(names ? `قالب‌ها: ${names}` : "قالبی نیست");
      });
    });
  }

  function bindPhaseAnnounce() {
    window.addEventListener("mafi:phase", (ev) => {
      const el = $("#live-region");
      if (el && ev.detail) el.textContent = ev.detail;
    });
  }

  function init() {
    bindTutorial();
    bindSettingsExtras();
    bindReconnectBanner();
    bindClientErrors();
    bindAdminExport();
    bindFriendsHome();
    bindCreatorTemplates();
    bindPhaseAnnounce();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  window.MafiExtras = { applyBattery, applyA11y };
})();
