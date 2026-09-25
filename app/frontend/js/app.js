/* MAFI — کلاینت اصلی بازی مافیا */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const toFa = (n) =>
    String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);

  const PHASE_LABEL = {
    lobby: "لابی",
    dealing: "توزیع نقش",
    night_mafia: "شب · مافیا",
    night_silencer: "شب · سایلنسر",
    night_natasha: "شب · ناتاشا",
    night_doctor: "شب · دکتر",
    night_bodyguard: "شب · بادیگارد",
    night_detective: "شب · کارآگاه",
    night_psych: "شب · روان‌پزشک",
    night_killer: "شب · جانی",
    night_sniper: "شب · اسنایپر",
    day_announce: "صبح",
    day_discuss: "بحث",
    day_defense: "دفاع نهایی",
    day_trust: "رأی اعتماد",
    day_vote: "رأی‌گیری",
    day_result: "نتیجه رأی",
    game_over: "پایان",
  };

  const AVATARS_FALLBACK = ["🦁","🐺","🦅","🦊","🦉","🐉","🦂","🦇","🐯","🐆","🦈","🐍","🕷️","🖤","⚔️","🔥","🎭","🎩","💎","🌙"];

  function playerToken() {
    let t = localStorage.getItem("mafi_token");
    if (!t) {
      t = ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, (c) =>
        (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)
      );
      localStorage.setItem("mafi_token", t);
    }
    return t;
  }

  function selectedAvatar() {
    return localStorage.getItem("mafi_avatar") || "🦁";
  }

  const LOADING_HINTS = [
    "در حال بیدار کردن شهر...",
    "سایه‌ها جمع می‌شوند...",
    "نقشه‌ی شب آماده می‌شود...",
    "گرداننده بیدار می‌شود...",
    "خون و طلا در هم می‌آمیزند...",
    "MAFI آماده است...",
  ];

  let socket = null;
  let state = null;
  let mySid = null;
  let isHost = false;
  let chatTab = "public";
  let timerInterval = null;
  let timerTotal = 30;
  let cardFlipped = false;
  let settingsLocked = false;
  /** When true: arrived via QR/?room= — stay on home, only name + Join */
  let invitePending = false;
  let lobbyTab = "players";
  let telegramMode = false;
  let telegramConfig = null;
  let telegramWebApp = null;
  /** Assigned in bindUI */
  let doLeaveGame = () => {};

  function telegramInitData() {
    return (
      localStorage.getItem("mafi_tg_init") ||
      window.Telegram?.WebApp?.initData ||
      ""
    );
  }

  function telegramPayload(extra = {}) {
    const init = telegramInitData();
    if (!telegramMode && !init) return extra;
    return {
      ...extra,
      telegram: true,
      telegram_init_data: init,
    };
  }

  function initTelegramWebApp() {
    const tg = window.Telegram?.WebApp;
    if (!tg) return false;
    telegramWebApp = tg;
    telegramMode = true;
    document.body.classList.add("telegram-webapp", "telegram-mode");
    const banner = $("#telegram-banner");
    if (banner) banner.hidden = false;
    try {
      tg.ready();
      tg.expand();
      tg.setHeaderColor("#0a0808");
      tg.setBackgroundColor("#0a0808");
    } catch (_) {}
    bindTelegramMainButton();
    const initData = tg.initData || "";
    if (initData) localStorage.setItem("mafi_tg_init", initData);
    const user = tg.initDataUnsafe?.user;
    if (user) {
      const display = [user.first_name, user.last_name]
        .filter(Boolean)
        .join(" ")
        .trim();
      if (display) {
        localStorage.setItem("mafi_name", display.slice(0, 20));
        const nameEl = $("#player-name");
        if (nameEl && !nameEl.value.trim()) nameEl.value = display.slice(0, 20);
      }
    }
    const startParam = String(tg.initDataUnsafe?.start_param || "").trim();
    if (startParam) {
      const code = startParam
        .replace(/^(join_|room_)/i, "")
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, "")
        .slice(0, 6);
      if (code) {
        const url = new URL(location.href);
        url.searchParams.set("room", code);
        url.searchParams.set("tg", "1");
        history.replaceState({}, "", url.pathname + url.search);
      }
    }
    applyTelegramUrlHints();
    $("#player-name")?.addEventListener("input", () => updateTelegramChrome());
    setTimeout(updateTelegramChrome, 300);
    return true;
  }

  function applyTelegramUrlHints() {
    const params = new URLSearchParams(location.search);
    if (params.get("tg") === "1") {
      telegramMode = true;
      document.body.classList.add("telegram-mode");
      const banner = $("#telegram-banner");
      if (banner) banner.hidden = false;
    }
    if (params.get("action") === "create" && (telegramMode || params.get("tg") === "1")) {
      document.body.classList.add("telegram-create");
    }
  }

  async function loadTelegramConfig() {
    try {
      const res = await fetch("/api/telegram/config", { cache: "no-store" });
      if (!res.ok) return;
      telegramConfig = await res.json();
      if (telegramConfig?.enabled) {
        document.body.classList.add("telegram-server-on");
        const shareBtn = $("#btn-share-telegram");
        const tgHint = $("#invite-telegram-hint");
        if (shareBtn) shareBtn.hidden = false;
        if (tgHint) tgHint.hidden = false;
      }
    } catch (_) {}
  }

  function telegramDeepLink(code) {
    const c = String(code || "").trim().toUpperCase().slice(0, 6);
    if (!c) return null;
    const tpl = telegramConfig?.invite_deep_link_template;
    if (tpl) return tpl.replace("{code}", c);
    const u = telegramConfig?.bot_username;
    return u ? `https://t.me/${u}?start=join_${c}` : null;
  }

  function telegramWebAppInviteUrl(code) {
    const c = String(code || "").trim().toUpperCase().slice(0, 6);
    if (!c) return null;
    const base =
      telegramConfig?.webapp_url ||
      telegramConfig?.webapp_base ||
      location.origin;
    return `${String(base).replace(/\/$/, "")}/?room=${encodeURIComponent(c)}&tg=1`;
  }

  function tgHaptic(type) {
    try {
      telegramWebApp?.HapticFeedback?.impactOccurred?.(type || "light");
    } catch (_) {}
  }

  function updateTelegramChrome() {
    const tg = telegramWebApp;
    if (!tg || !telegramMode) return;

    const homeActive = $("#screen-home")?.classList.contains("active");
    const lobbyActive = $("#screen-lobby")?.classList.contains("active");
    const gameActive = $("#screen-game")?.classList.contains("active");

    try {
      if (gameActive && state && state.phase !== "lobby" && state.phase !== "game_over") {
        tg.enableClosingConfirmation?.();
      } else {
        tg.disableClosingConfirmation?.();
      }
    } catch (_) {}

    if (typeof tg.BackButton?.offClick === "function") {
      try {
        tg.BackButton.offClick(doTelegramBack);
      } catch (_) {}
    }

    if (homeActive) {
      try {
        tg.BackButton?.hide?.();
      } catch (_) {}
      const nameOk = ($("#player-name")?.value.trim().length || 0) >= 2;
      if (invitePending) {
        tg.MainButton?.setText?.("ورود به اتاق");
        nameOk ? tg.MainButton?.show?.() : tg.MainButton?.hide?.();
      } else if (document.body.classList.contains("telegram-create") || !$("#room-code")?.value.trim()) {
        tg.MainButton?.setText?.("ساخت اتاق");
        nameOk ? tg.MainButton?.show?.() : tg.MainButton?.hide?.();
      } else {
        tg.MainButton?.setText?.("ورود");
        nameOk ? tg.MainButton?.show?.() : tg.MainButton?.hide?.();
      }
      return;
    }

    if (lobbyActive) {
      try {
        tg.BackButton?.show?.();
        tg.BackButton?.onClick?.(doTelegramBack);
      } catch (_) {}
      const players = (state?.players || []).filter((p) => !p.is_spectator);
      const connected = players.filter((p) => p.connected !== false).length;
      if (isHost && connected >= 6) {
        tg.MainButton?.setText?.("شروع بازی 🎭");
        tg.MainButton?.show?.();
      } else if (isHost) {
        tg.MainButton?.setText?.(`منتظر بازیکن (${connected}/۶)`);
        tg.MainButton?.show?.();
        tg.MainButton?.disable?.();
      } else {
        tg.MainButton?.hide?.();
      }
      if (isHost && connected >= 6) tg.MainButton?.enable?.();
      return;
    }

    if (gameActive) {
      try {
        tg.BackButton?.show?.();
        tg.BackButton?.onClick?.(doTelegramBack);
      } catch (_) {}
      tg.MainButton?.hide?.();
    }
  }

  function doTelegramBack() {
    tgHaptic("light");
    if ($("#screen-home")?.classList.contains("active")) return;
    doLeaveGame();
  }

  function bindTelegramMainButton() {
    const tg = telegramWebApp;
    if (!tg?.MainButton) return;
    try {
      tg.MainButton.offClick(onTelegramMainClick);
    } catch (_) {}
    tg.MainButton.onClick(onTelegramMainClick);
    tg.MainButton.setParams?.({ color: "#b8860b", text_color: "#0a0808", is_active: true });
  }

  async function onTelegramMainClick() {
    tgHaptic("medium");
    await AudioSys.unlock();
    if ($("#screen-lobby")?.classList.contains("active") && isHost) {
      AudioSys.sfx("deal");
      socket.emit("start_game");
      return;
    }
    if (invitePending || $("#room-code")?.value.trim()) {
      $("#btn-join")?.click();
      return;
    }
    $("#btn-create")?.click();
  }

  async function shareTelegramInvite(code) {
    const c = String(code || state?.code || "").trim().toUpperCase();
    if (!c) return toast("کد اتاق آماده نیست", "warn");
    let deep = telegramDeepLink(c);
    let web = telegramWebAppInviteUrl(c);
    try {
      const res = await fetch(`/api/telegram/invite/${encodeURIComponent(c)}`, {
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        deep = data.deep_link || deep;
        web = data.webapp_url || web;
      }
    } catch (_) {}
    const text = `🎭 بیا مافیا بازی کنیم!\nاتاق: ${c}`;
    const tg = telegramWebApp;
    if (tg?.shareUrl && (deep || web)) {
      try {
        tg.shareUrl(deep || web, text);
        toast("پنجره اشتراک تلگرام", "success");
        return;
      } catch (_) {}
    }
    if (tg?.openTelegramLink && deep) {
      try {
        tg.openTelegramLink(
          `https://t.me/share/url?url=${encodeURIComponent(deep)}&text=${encodeURIComponent(text)}`
        );
        return;
      } catch (_) {}
    }
    const copy = deep || web;
    if (copy) {
      copyText(copy).then(
        () => toast("لینک دعوت تلگرام کپی شد", "success"),
        () => toast(copy, "info")
      );
    }
  }

  function normName(n) {
    return String(n || "")
      .trim()
      .replace(/\s+/g, " ")
      .toLocaleLowerCase("fa");
  }

  function applyInviteFromUrl() {
    const params = new URLSearchParams(location.search);
    const joinCode = String(params.get("room") || "")
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "")
      .slice(0, 6);
    if (!joinCode) {
      invitePending = false;
      document.body.classList.remove("invite-join");
      return false;
    }

    invitePending = true;
    document.body.classList.add("invite-join");

    // Don't auto-rejoin an old room while accepting a fresh invite
    try {
      sessionStorage.removeItem("mafi_room");
    } catch (_) {}

    const codeEl = $("#room-code");
    if (codeEl) {
      codeEl.value = joinCode;
      codeEl.readOnly = true;
      codeEl.classList.add("code-locked");
      codeEl.title = "کد از دعوت‌نامه آمده است";
    }

    const banner = $("#invite-join-banner");
    const codeLabel = $("#invite-join-code");
    if (codeLabel) codeLabel.textContent = joinCode;
    if (banner) banner.hidden = false;

    const hint = $("#join-hint");
    if (hint) hint.hidden = false;

    const createBtn = $("#btn-create");
    if (createBtn) createBtn.style.display = "none";

    // Clear previous display name so guest types their own (avoid accidental dup)
    const nameEl = $("#player-name");
    if (nameEl) {
      nameEl.value = "";
      nameEl.placeholder = "نام خود را بنویسید (یکتا)";
      setTimeout(() => {
        try {
          nameEl.focus({ preventScroll: false });
        } catch (_) {
          nameEl.focus();
        }
      }, 400);
    }
    return true;
  }

  function clearInviteMode() {
    invitePending = false;
    document.body.classList.remove("invite-join");
    const codeEl = $("#room-code");
    if (codeEl) {
      codeEl.readOnly = false;
      codeEl.classList.remove("code-locked");
      codeEl.title = "";
    }
    const banner = $("#invite-join-banner");
    if (banner) banner.hidden = true;
    const hint = $("#join-hint");
    if (hint) hint.hidden = true;
    const createBtn = $("#btn-create");
    if (createBtn) createBtn.style.display = "";
  }

  // ---------- Init ----------
  document.addEventListener("DOMContentLoaded", () => {
    try {
      if ($("#bg-canvas") && typeof Scene3D !== "undefined") Scene3D.init($("#bg-canvas"));
    } catch (e) {
      console.warn("Scene3D init failed", e);
    }
    try {
      bindUI();
    } catch (e) {
      console.error("bindUI failed", e);
    }
    applyTelegramUrlHints();
    showPhoneHostAddress();
    initTelegramWebApp();
    applyInviteFromUrl();
    loadTelegramConfig().then(() => {
      if (state?.code) refreshInviteQr(true);
      updateTelegramChrome();
    });
    runLoading();
    window.addEventListener("resize", () => {
      if ($("#screen-lobby")?.classList.contains("active")) syncInvitePanelMode();
    });
    window.addEventListener("orientationchange", () => {
      setTimeout(() => {
        if ($("#screen-lobby")?.classList.contains("active")) syncInvitePanelMode();
      }, 200);
    });
  });

  function runLoading() {
    if (window.__mafiLoadingOwned) {
      const go = () => {
        try {
          connectSocket();
        } catch (e) {
          console.error("connectSocket failed", e);
        }
      };
      if (window.__mafiLoadingDone) go();
      else window.addEventListener("mafi-loading-done", go, { once: true });
      return;
    }
    const bar = $("#loading-bar");
    const pct = $("#loading-pct");
    const hint = $("#loading-hint");
    const sparks = $("#loading-sparks");
    const duration = 2800;
    const start = performance.now();

    // جرقه‌های شناور
    if (sparks) {
      for (let i = 0; i < 28; i++) {
        const s = document.createElement("span");
        s.style.left = Math.random() * 100 + "%";
        s.style.bottom = Math.random() * 20 + "%";
        s.style.animationDuration = 4 + Math.random() * 6 + "s";
        s.style.animationDelay = Math.random() * 5 + "s";
        sparks.appendChild(s);
      }
    }

    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 2);
      const p = Math.floor(eased * 100);
      if (bar) bar.style.width = p + "%";
      if (pct) pct.textContent = toFa(p) + "٪";
      if (hint) {
        const hi = Math.min(
          LOADING_HINTS.length - 1,
          Math.floor(t * LOADING_HINTS.length)
        );
        hint.textContent = LOADING_HINTS[hi];
      }

      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        setTimeout(() => {
          const sc = $("#screen-loading");
          if (sc) {
            sc.style.transition = "opacity 0.5s ease, transform 0.5s ease";
            sc.style.opacity = "0";
            sc.style.transform = "scale(1.04)";
          }
          setTimeout(() => {
            if (sc) {
              sc.classList.remove("active");
              sc.style.opacity = "";
              sc.style.transform = "";
            }
            $("#screen-home")?.classList.add("active");
            connectSocket();
          }, 500);
        }, 200);
      }
    }
    requestAnimationFrame(frame);
  }

  function connectSocket() {
    socket = io({ transports: ["websocket", "polling"], reconnection: true });
    window.__mafiSocket = socket;
    window.dispatchEvent(new CustomEvent("mafi:socket", { detail: socket }));
    VoiceChat.init(socket);

    socket.on("connect", () => {
      mySid = socket.id;
      VoiceChat.setIdentity(socket.id);
      tryRejoin();
    });
    socket.io.on("reconnect", () => {
      tryRejoin();
      toast("اتصال برگشت. اتاق سر جایش است.", "ok");
    });

    socket.on("connected", (d) => {
      mySid = d.sid;
      VoiceChat.setIdentity(d.sid);
    });

    socket.on("error", (d) => toast(d?.message || "خطا", "error"));
    socket.on("toast", (d) => {
      if (d?.message) toast(d.message, d.type || "info");
    });
    socket.on("room_created", (d) => {
      if (!d?.code) return;
      const qs = telegramMode ? `?room=${d.code}&tg=1` : `?room=${d.code}`;
      history.replaceState({}, "", qs);
      sessionStorage.setItem("mafi_room", d.code);
    });

    socket.on("game_state", onState);
    socket.on("narrator", onNarrator);
    socket.on("role_reveal", onRoleReveal);
    socket.on("atmosphere", onAtmosphere);
    socket.on("death_effect", onDeath);
    socket.on("speak_turn", onSpeakTurn);
    socket.on("challenge_pending", onChallengePending);
    socket.on("chat", (msg) => {
      if (!msg) return;
      appendChat("#game-chat", msg, false);
      if ($("#screen-lobby")?.classList.contains("active")) {
        appendChat("#lobby-chat", msg, false);
      }
    });
    socket.on("mafia_chat", (msg) => {
      if (msg) appendChat("#mafia-chat", msg, true);
    });
    socket.on("left_game", () => {
      if (typeof window.__mafiResetToHome === "function") {
        window.__mafiResetToHome();
      }
    });
    socket.on("session", (d) => {
      if (d?.token) localStorage.setItem("mafi_token", d.token);
      if (d?.code) sessionStorage.setItem("mafi_room", d.code);
    });
    socket.on("profile", (p) => renderProfile(p));
    socket.on("leaderboard", (d) => {
      renderLeaderboard(d);
      renderLeaderboardHome(d);
    });
    socket.on("host_preview", (d) => {
      toast("پیش‌نمایش آماده شد", "info");
      console.log("preview", d);
    });
    socket.on("admin_auth_result", onAdminAuthResult);
    socket.on("voice_preview", (d) => {
      if (d?.audio) AudioSys.playNarrator(d.text || "", d.audio);
      else if (d?.text) AudioSys.speak(d.text);
    });
    socket.on("admin_whisper", (d) => {
      toast(`پیام ادمین: ${d.text}`, "warn");
      AudioSys.sfx("toast");
    });
  }

  function tryRejoin() {
    // QR / ?room= invite: stay on home — user must type a unique name and press Join
    if (invitePending) return;

    const room = sessionStorage.getItem("mafi_room");
    const token = localStorage.getItem("mafi_token");
    if (token) {
      socket.emit("rejoin", telegramPayload({ token, code: room || "" }));
      return;
    }
    const name = localStorage.getItem("mafi_name");
    if (!room || !name) return;
    if (state && state.code === room && state.me) return;
    socket.emit("join_room", telegramPayload({
      name,
      code: room,
      spectator: false,
      token: playerToken(),
      avatar: selectedAvatar(),
    }));
  }

  // ---------- UI Bind ----------
  function bindUI() {
    const unlock = () => AudioSys.unlock();
    document.body.addEventListener("pointerdown", unlock, { once: true });

    $("#btn-create").onclick = async () => {
      await AudioSys.unlock();
      AudioSys.sfx("click");
      if (invitePending) {
        return toast("برای این دعوت فقط «ورود» را بزنید", "warn");
      }
      const name = $("#player-name").value.trim().replace(/\s+/g, " ");
      if (!name) return toast("نام خود را وارد کنید", "warn");
      if (name.length < 2) return toast("نام حداقل ۲ حرف باشد", "warn");
      localStorage.setItem("mafi_name", name);
      socket.emit("create_room", telegramPayload({
        name,
        token: playerToken(),
        avatar: selectedAvatar(),
      }));
    };

    $("#btn-join").onclick = async () => {
      await AudioSys.unlock();
      AudioSys.sfx("click");
      const name = $("#player-name").value.trim().replace(/\s+/g, " ");
      const code = $("#room-code").value.trim().toUpperCase();
      if (!name) {
        $("#player-name")?.focus();
        return toast("نام خود را وارد کنید", "warn");
      }
      if (name.length < 2) return toast("نام حداقل ۲ حرف باشد", "warn");
      if (!code) return toast("کد اتاق را وارد کنید", "warn");
      localStorage.setItem("mafi_name", name);
      sessionStorage.setItem("mafi_room", code);
      // keep invitePending until game_state confirms join (so failed dup name stays on home invite UI)
      socket.emit("join_room", telegramPayload({
        name,
        code,
        spectator: $("#as-spectator").checked,
        token: playerToken(),
        password: $("#room-password")?.value || "",
        avatar: selectedAvatar(),
      }));
    };

    const saved = localStorage.getItem("mafi_name");
    if (saved && !invitePending) $("#player-name").value = saved;

    // Enter key on name → join when invite, else create if no code
    $("#player-name")?.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (invitePending || $("#room-code")?.value.trim()) $("#btn-join")?.click();
      else $("#btn-create")?.click();
    });
    $("#room-code")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        $("#btn-join")?.click();
      }
    });

    $("#btn-start").onclick = () => {
      AudioSys.sfx("deal");
      socket.emit("start_game");
    };

    $("#btn-claim-host").onclick = () => {
      AudioSys.sfx("click");
      socket.emit("claim_host");
    };

    $("#btn-copy-code").onclick = () => {
      const code = state?.code;
      if (!code) return toast("کد اتاق آماده نیست", "warn");
      copyText(code).then(
        () => toast(`کد اتاق کپی شد: ${code}`, "success"),
        () => toast(code, "info")
      );
      AudioSys.sfx("click");
    };

    $("#btn-copy-link").onclick = () => {
      const code = state?.code;
      if (!code) return toast("کد اتاق آماده نیست", "warn");
      const url =
        telegramDeepLink(code) ||
        telegramWebAppInviteUrl(code) ||
        `${location.origin}?room=${code}&tg=1`;
      copyText(url).then(
        () => toast("لینک دعوت کپی شد", "success"),
        () => toast(url, "info")
      );
      AudioSys.sfx("click");
    };

    const inviteUrlNow = () => {
      const url = $("#invite-lan-url")?.dataset?.url || $("#invite-lan-url")?.textContent;
      if (!url || url.includes("...") || url === "—") return "";
      return url;
    };
    const copyLan = () => {
      const url = inviteUrlNow();
      if (!url) return toast("لینک شبکه هنوز آماده نیست", "warn");
      copyText(url).then(
        () => toast("لینک شبکه کپی شد", "success"),
        () => toast(url, "info")
      );
      AudioSys.sfx("click");
    };
    const shareLan = () => {
      const url = inviteUrlNow();
      if (!url) return toast("لینک شبکه هنوز آماده نیست", "warn");
      const text = "بیا مافیا بازی کنیم\n" + url;
      AudioSys.sfx("click");
      if (window.MafiNative && typeof window.MafiNative.share === "function") {
        window.MafiNative.share(text);
        return;
      }
      if (navigator.share) {
        navigator.share({ title: "مافیا", text, url }).catch(() => copyLan());
        return;
      }
      copyLan();
    };
    if ($("#btn-copy-lan")) $("#btn-copy-lan").onclick = copyLan;
    if ($("#btn-copy-lan-text")) $("#btn-copy-lan-text").onclick = copyLan;
    if ($("#btn-share-lan")) $("#btn-share-lan").onclick = shareLan;
    if ($("#btn-refresh-qr")) {
      $("#btn-refresh-qr").onclick = () => {
        AudioSys.sfx("click");
        refreshInviteQr(true);
      };
    }
    if ($("#btn-share-telegram")) {
      $("#btn-share-telegram").onclick = () => {
        AudioSys.sfx("click");
        shareTelegramInvite(state?.code);
      };
    }

    $("#lobby-code").onclick = () => {
      $("#btn-copy-code").click();
    };
    $("#lobby-code").style.cursor = "pointer";
    $("#lobby-code").title = "کلیک برای کپی کد";

    $("#btn-rules-home").onclick = () => showModal("modal-rules");
    $("#btn-rules").onclick = () => showModal("modal-rules");
    $("#btn-settings-home").onclick = () => showModal("modal-settings");
    if ($("#btn-lb-home")) {
      $("#btn-lb-home").onclick = () => {
        showModal("modal-leaderboard");
        socket.emit("get_leaderboard");
      };
    }
    bindThemeUI();
    bindVoicePreview();
    bindPwaInstall();

    $$("[data-close]").forEach(
      (b) =>
        (b.onclick = () =>
          b.closest(".modal").classList.remove("show"))
    );
    $$(".modal").forEach((m) => {
      m.addEventListener("click", (e) => {
        if (e.target === m) m.classList.remove("show");
      });
    });

    const muteBtns = ["#btn-mute", "#btn-mute-g"];
    muteBtns.forEach((sel) => {
      const el = $(sel);
      if (el)
        el.onclick = () => {
          const m = AudioSys.toggleMute();
          muteBtns.forEach((s) => {
            const b = $(s);
            if (b) b.textContent = m ? "🔇" : "🔊";
          });
        };
    });

    $("#btn-fullscreen").onclick = () => {
      if (!document.fullscreenElement) document.documentElement.requestFullscreen?.();
      else document.exitFullscreen?.();
    };

    $("#btn-skip").onclick = () => socket.emit("skip_phase");
    $("#btn-skip-action").onclick = () => {
      socket.emit("night_action", { action: "skip" });
    };

    $("#btn-rematch").onclick = () => {
      $("#end-overlay").classList.remove("show");
      socket.emit("rematch");
    };

    let leavePending = false;
    doLeaveGame = function doLeaveGameFn() {
      if (leavePending) return;
      const ok = confirm("از بازی خارج می‌شوید و به صفحه اصلی برمی‌گردید؟");
      if (!ok) return;
      leavePending = true;
      AudioSys.sfx("click");
      if (socket && socket.connected) {
        socket.emit("leave_game");
      } else {
        resetToHomeAfterLeave();
        return;
      }
      setTimeout(() => {
        if (leavePending) resetToHomeAfterLeave();
      }, 800);
    };

    function resetToHomeAfterLeave() {
      leavePending = false;
      try {
        sessionStorage.removeItem("mafi_room");
      } catch (_) {}
      state = null;
      if (typeof VoiceChat !== "undefined" && VoiceChat.shutdown) {
        try {
          VoiceChat.shutdown();
        } catch (_) {}
      }
      $("#end-overlay")?.classList.remove("show");
      $("#role-overlay")?.classList.remove("show");
      document.body.classList.remove("chat-open");
      try {
        history.replaceState({}, "", location.pathname);
      } catch (_) {}
      clearInviteMode();
      showScreen("home");
      updateTelegramChrome();
      toast("از بازی خارج شدید — می‌توانید دوباره شروع کنید", "info");
    }
    window.__mafiResetToHome = resetToHomeAfterLeave;

    if ($("#btn-leave-lobby")) $("#btn-leave-lobby").onclick = doLeaveGame;
    if ($("#btn-leave-game")) $("#btn-leave-game").onclick = doLeaveGame;
    if ($("#btn-leave-fab")) $("#btn-leave-fab").onclick = doLeaveGame;

    $("#my-role-chip").onclick = () => {
      if (state?.me?.role) showRoleCard(state.me, false);
    };

    // Settings ranges
    bindSetting("set-mafia", "set-mafia-val", "mafia_count");
    bindSetting("set-night", "set-night-val", "night_time");
    bindSetting("set-discuss", "set-discuss-val", "discuss_time");
    bindSetting("set-vote", "set-vote-val", "vote_time");
    bindSetting("set-speak", "set-speak-val", "speak_time");
    const specDelay = $("#set-spectator-delay");
    if (specDelay) {
      specDelay.oninput = () => {
        const v = $("#set-spectator-delay-val");
        if (v) v.textContent = toFa(specDelay.value);
        emitSettings();
      };
    }

    ["set-doctor", "set-detective", "set-sniper", "set-godfather", "set-mayor", "set-bodyguard", "set-silencer", "set-psych", "set-killer", "set-sacrifice", "set-reporter", "set-natasha", "set-joker", "set-vigilante", "set-auto-roles", "set-tournament", "set-ranked", "set-bot-diff"].forEach((id) => {
      const el = $(`#${id}`);
      if (el) el.onchange = emitSettings;
    });
    ["set-mode", "set-narrator-rate", "set-narrator-voice", "set-password", "set-spectator-delay"].forEach((id) => {
      const el = $(`#${id}`);
      if (el) el.onchange = emitSettings;
    });

    const addBots = $("#btn-add-bots");
    if (addBots) addBots.onclick = () => socket.emit("add_bots", { count: 2 });
    const remBots = $("#btn-remove-bots");
    if (remBots) remBots.onclick = () => socket.emit("remove_bots");
    const prev = $("#btn-host-preview");
    if (prev) prev.onclick = () => socket.emit("host_preview");
    const veto = $("#btn-mayor-veto");
    // created dynamically in renderGame if needed

    if ($("#btn-profile-home")) {
      $("#btn-profile-home").onclick = () => {
        showModal("modal-profile");
        socket.emit("get_profile", { token: playerToken() });
        socket.emit("get_leaderboard");
        socket.emit("get_matches", { token: playerToken() });
      };
    }

    buildAvatarPicker();

    $$("#lobby-tabs .lobby-tab").forEach((btn) => {
      btn.onclick = () => {
        AudioSys.sfx("click");
        setLobbyTab(btn.dataset.lobbyTab);
      };
    });

    function syncDockChatState() {
      const open = document.body.classList.contains("chat-open");
      $("#dock-chat")?.classList.toggle("active", open);
    }

    const chatFab = $("#btn-chat-toggle");
    if (chatFab) {
      chatFab.onclick = () => {
        document.body.classList.toggle("chat-open");
        syncDockChatState();
      };
    }
    const dockChat = $("#dock-chat");
    if (dockChat) {
      dockChat.onclick = () => {
        AudioSys.sfx("click");
        document.body.classList.toggle("chat-open");
        syncDockChatState();
      };
    }
    const dockRole = $("#dock-role");
    if (dockRole) {
      dockRole.onclick = () => {
        AudioSys.sfx("click");
        if (state?.me?.role) showRoleCard(state.me, false);
        else toast("هنوز نقشی ندارید", "info");
      };
    }
    const micFab = $("#btn-mic-fab");
    if (micFab) {
      micFab.onclick = () => $("#btn-mic")?.click();
    }
    const dockMic = $("#dock-mic");
    if (dockMic) {
      dockMic.onclick = () => {
        AudioSys.sfx("click");
        $("#btn-mic")?.click();
      };
    }
    if ($("#dock-leave")) $("#dock-leave").onclick = doLeaveGame;

    bindAdminUI();

    $("#btn-mic").onclick = async () => {
      await AudioSys.unlock();
      if (!VoiceChat.isEnabled()) {
        const ok = await VoiceChat.enable();
        if (!ok) toast("دسترسی به میکروفون داده نشد", "error");
        else toast("مایک فعال شد", "success");
      } else {
        VoiceChat.toggleMute();
      }
    };

    $("#btn-skip-speak").onclick = () => {
      socket.emit("skip_speak");
    };

    // Challenge UI
    let challengeSec = 10;
    let challengePos = "after";
    let decideSec = 10;
    let decidePos = "after";

    $("#btn-challenge").onclick = () => {
      if (state?.phase !== "day_discuss") return;
      $("#challenge-sheet").style.display = "block";
      const left = state.my_challenges_left ?? 2;
      $("#challenge-left-hint").textContent = `${toFa(left)} چالش باقی‌مانده امروز`;
    };
    $("#btn-challenge-cancel").onclick = () => {
      $("#challenge-sheet").style.display = "none";
    };
    $$("#challenge-sheet [data-sec]").forEach((b) => {
      b.onclick = () => {
        $$("#challenge-sheet [data-sec]").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        challengeSec = +b.dataset.sec;
      };
    });
    $$("#challenge-sheet [data-pos]").forEach((b) => {
      b.onclick = () => {
        $$("#challenge-sheet [data-pos]").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        challengePos = b.dataset.pos;
      };
    });
    $("#btn-challenge-send").onclick = () => {
      socket.emit("challenge_request", {
        seconds: challengeSec,
        position: challengePos,
      });
      $("#challenge-sheet").style.display = "none";
      AudioSys.sfx("phase");
    };

    $$("#cd-adjust [data-sec]").forEach((b) => {
      b.onclick = () => {
        $$("#cd-adjust [data-sec]").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        window.__mafiDecideSec = +b.dataset.sec;
      };
    });
    $$("#cd-adjust [data-pos]").forEach((b) => {
      b.onclick = () => {
        $$("#cd-adjust [data-pos]").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        window.__mafiDecidePos = b.dataset.pos;
      };
    });
    $("#btn-challenge-accept").onclick = () => {
      socket.emit("challenge_respond", {
        accept: true,
        seconds: window.__mafiDecideSec || 10,
        position: window.__mafiDecidePos || "after",
      });
      hideChallengeDecide();
    };
    $("#btn-challenge-reject").onclick = () => {
      socket.emit("challenge_respond", { accept: false });
      hideChallengeDecide();
    };

    $("#lobby-chat-form").onsubmit = (e) => {
      e.preventDefault();
      sendChat("#lobby-chat-input", false);
    };
    $("#game-chat-form").onsubmit = (e) => {
      e.preventDefault();
      sendChat("#game-chat-input", chatTab === "mafia");
    };

    $$(".chat-tabs .tab").forEach((tab) => {
      tab.onclick = () => {
        $$(".chat-tabs .tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        chatTab = tab.dataset.tab;
        $("#game-chat").style.display = chatTab === "public" ? "flex" : "none";
        $("#mafia-chat").style.display = chatTab === "mafia" ? "flex" : "none";
      };
    });

    $("#role-card").onclick = flipCard;

    $("#vol-music").oninput = (e) =>
      AudioSys.setVol("music", e.target.value / 100);
    $("#vol-sfx").oninput = (e) =>
      AudioSys.setVol("sfx", e.target.value / 100);
    $("#vol-voice").oninput = (e) =>
      AudioSys.setVol("voice", e.target.value / 100);

    $("#gfx-quality").value = Scene3D.getQuality();
    $("#gfx-quality").onchange = (e) => {
      Scene3D.setQuality(e.target.value);
      toast("کیفیت گرافیک تغییر کرد", "info");
    };

    // 3D card tilt
    const card = $("#role-card");
    card.addEventListener("pointermove", (e) => {
      if (card.classList.contains("flipped")) return;
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      card.style.transform = `rotateY(${x * 20}deg) rotateX(${-y * 15}deg)`;
    });
    card.addEventListener("pointerleave", () => {
      if (!card.classList.contains("flipped"))
        card.style.transform = "";
    });
  }

  function bindSetting(inputId, valId, key) {
    const input = $(`#${inputId}`);
    const val = $(`#${valId}`);
    input.oninput = () => {
      val.textContent = toFa(input.value);
      emitSettings();
    };
  }

  function emitSettings() {
    if (!isHost || settingsLocked) return;
    socket.emit("update_settings", {
      mafia_count: +$("#set-mafia").value,
      doctor: $("#set-doctor").checked,
      detective: $("#set-detective").checked,
      sniper: $("#set-sniper").checked,
      godfather: $("#set-godfather")?.checked,
      mayor: $("#set-mayor")?.checked,
      bodyguard: $("#set-bodyguard")?.checked,
      silencer: $("#set-silencer")?.checked,
      psychiatrist: $("#set-psych")?.checked,
      serial_killer: $("#set-killer")?.checked,
      sacrifice: $("#set-sacrifice")?.checked,
      reporter: $("#set-reporter")?.checked,
      natasha: $("#set-natasha")?.checked,
      joker: $("#set-joker")?.checked,
      vigilante: $("#set-vigilante")?.checked,
      auto_roles: $("#set-auto-roles")?.checked,
      bot_difficulty: $("#set-bot-diff")?.value || "normal",
      night_time: +$("#set-night").value,
      discuss_time: +$("#set-discuss").value,
      vote_time: +$("#set-vote").value,
      speak_time: +$("#set-speak").value,
      narrator_rate: $("#set-narrator-rate")?.value || "normal",
      narrator_voice: $("#set-narrator-voice")?.value || "farid",
      game_mode: $("#set-mode")?.value || "classic",
      tournament: $("#set-tournament")?.checked,
      ranked: $("#set-ranked")?.checked,
      room_password: $("#set-password")?.value || "",
      spectator_delay: +($("#set-spectator-delay")?.value || 30),
    });
  }

  function sendChat(inputSel, mafia) {
    const input = $(inputSel);
    const text = input.value.trim();
    if (!text) return;
    socket.emit("chat_message", { text, mafia });
    input.value = "";
  }

  // ---------- State ----------
  function onState(s) {
    state = s;
    window.__mafiRoomCode = s.code || window.__mafiRoomCode;
    mySid = s.me?.sid || mySid;
    isHost = s.host_sid === mySid || s.me?.is_host;

    VoiceChat.setIdentity(mySid);
    VoiceChat.setPlayerFlags({
      alive: s.me?.alive !== false,
      mafia: ["mafia", "godfather", "silencer", "natasha"].includes(s.me?.role),
      spectator: !!s.me?.is_spectator,
      silenced: !!s.am_silenced || s.silenced_sid === (s.me?.sid || mySid),
    });

    if (s.phase === "lobby") {
      clearInviteMode();
      showScreen("lobby");
      renderLobby();
      $("#speak-bar").style.display = "none";
      if ($("#btn-admin-entry")) $("#btn-admin-entry").style.display = "none";
    } else if (s.phase === "game_over") {
      showScreen("game");
      renderGame();
      showEnd();
      if (adminUnlocked && adminPasswordCache)
        socket.emit("admin_auth", { password: adminPasswordCache });
    } else {
      showScreen("game");
      renderGame();
      $("#end-overlay").classList.remove("show");
      if (adminUnlocked && adminPasswordCache)
        socket.emit("admin_auth", { password: adminPasswordCache });
    }

    if (s.phase_ends_at) startTimer(s.phase_ends_at);

    if (s.phase === "day_vote" && AudioSys.getMood() !== "vote") {
      AudioSys.playMusic("vote");
    }

    if (s.phase === "day_discuss" && s.current_speaker) {
      showSpeakBar(s);
    } else if (s.phase !== "day_discuss") {
      $("#speak-bar").style.display = "none";
      $("#challenge-sheet").style.display = "none";
      hideChallengeDecide();
    }

    if (s.challenge_pending) {
      onChallengePending(s.challenge_pending);
    } else {
      hideChallengeDecide();
    }

    if (s.detective_result) {
      showDetectiveResult(s.detective_result);
    }

    $("#btn-skip").style.display = isHost && s.phase !== "lobby" ? "block" : "none";
    updateTelegramChrome();
  }

  function setLobbyTab(tab) {
    if (!["players", "settings", "chat"].includes(tab)) return;
    lobbyTab = tab;
    const root = $("#screen-lobby");
    if (!root) return;
    root.dataset.lobbyTab = tab;
    $$(".lobby-tab", root).forEach((b) => {
      b.classList.toggle("active", b.dataset.lobbyTab === tab);
    });
  }

  let hotspotPrompted = false;

  function isPhoneHost() {
    return new URLSearchParams(location.search).get("source") === "android-host";
  }

  async function showPhoneHostAddress() {
    if (!isPhoneHost()) return;
    document.body.classList.add("phone-host");
    const box = $("#phone-host-banner");
    const line = $("#phone-host-address");
    const hint = document.querySelector(".invite-hint.invite-host-only");
    if (hint) {
      hint.textContent = "مهمان اپ لازم ندارد. روی همین وای‌فای لینک را در مرورگر باز کند یا QR را اسکن کند.";
    }
    if (!box || !line) return;
    box.hidden = false;
    try {
      const res = await fetch("/api/network", { cache: "no-store" });
      const net = await res.json();
      const lan = (net.lan && net.lan[0]) || "";
      if (lan) {
        line.textContent = "بقیه روی همین وای‌فای، با مرورگر وارد می‌شوند. آدرس این گوشی: " + lan;
        return;
      }
      line.textContent = "وای‌فای یا هات‌اسپات روشن نیست. تنظیمات باز می‌شود؛ بعد به بازی برگرد.";
      if (!hotspotPrompted && window.MafiNative && typeof window.MafiNative.openHotspot === "function") {
        hotspotPrompted = true;
        window.MafiNative.openHotspot();
      }
    } catch (_) {
      line.textContent = "اتاق را بساز. لینک و QR برای همین وای‌فای ساخته می‌شود.";
    }
  }

  function syncInvitePanelMode() {
    const panel = $("#invite-panel");
    if (!panel || panel.tagName !== "DETAILS") return;
    const narrow =
      window.matchMedia("(max-width: 860px)").matches ||
      window.matchMedia("(max-height: 500px) and (orientation: landscape)").matches;
    const androidHost = new URLSearchParams(location.search).get("source") === "android-host";
    if (isHost && (androidHost || !narrow)) panel.setAttribute("open", "");
    else panel.removeAttribute("open");
  }

  function showScreen(name) {
    $$(".screen").forEach((sc) => sc.classList.remove("active"));
    // keep loading hidden
    if (name === "lobby") {
      $("#screen-lobby").classList.add("active");
      setLobbyTab(lobbyTab);
      syncInvitePanelMode();
    }
    if (name === "game") $("#screen-game").classList.add("active");
    if (name === "home") {
      $("#screen-home").classList.add("active");
      document.body.classList.remove("lobby-is-host");
    }
    updateTelegramChrome();
  }

  let inviteNetCache = null;
  let inviteQrBusy = false;

  async function refreshInviteQr(force) {
    const code = state?.code;
    const img = $("#invite-qr");
    const urlEl = $("#invite-lan-url");
    const onlineEl = $("#invite-online");
    const guestCode = $("#invite-guest-code");
    if (!code || !urlEl) return;
    if (guestCode) guestCode.textContent = code;
    if (inviteQrBusy) return;
    inviteQrBusy = true;
    try {
      if (force || !inviteNetCache) {
        const res = await fetch("/api/network", { cache: "no-store" });
        if (!res.ok) throw new Error("network");
        inviteNetCache = await res.json();
      }
      const net = inviteNetCache || {};
      const params = new URLSearchParams(location.search);
      const isAndroidHost = params.get("source") === "android-host";
      const isCloudPlay = params.get("source") === "cloud";
      const isLoopback =
        location.hostname === "127.0.0.1" || location.hostname === "localhost";
      const cloudRaw =
        (net.online && String(net.online).trim()) ||
        (net.public_url && String(net.public_url).trim()) ||
        "";
      const cloudBad =
        !cloudRaw ||
        /your-service|your-cloud|your-domain|example\.com|placeholder|changeme/i.test(
          cloudRaw
        );
      const cloud = cloudBad ? "" : cloudRaw;
      // Phone host → always LAN QR (guests on same Wi‑Fi).
      // PC/cloud → prefer public HTTPS (Render/ngrok) so guests need no LAN.
      let base = "";
      if (isCloudPlay) {
        base = location.origin;
      } else if (!isAndroidHost && cloud) {
        base = cloud;
      } else {
        const host = location.hostname;
        if (host && !isLoopback) {
          base = location.origin;
        } else {
          base = (net.lan && net.lan[0]) || "";
        }
        if (!base && cloud) base = cloud;
        if (!base) base = net.local || location.origin;
      }
      const tgInvite = telegramWebAppInviteUrl(code);
      const tgDeep = telegramDeepLink(code);
      const roomPath = `${String(base).replace(/\/$/, "")}/?room=${encodeURIComponent(code)}`;
      let inviteUrl = roomPath;
      if (telegramMode && tgInvite) inviteUrl = tgInvite;
      else if (telegramConfig?.enabled && tgDeep) inviteUrl = tgDeep;
      urlEl.textContent = inviteUrl;
      urlEl.dataset.url = inviteUrl;
      if (img && isHost) {
        img.onerror = () => {
          urlEl.textContent = inviteUrl + "  (QR خطا — لینک را کپی کنید)";
        };
        img.src = `/api/qr?data=${encodeURIComponent(inviteUrl)}&t=${Date.now()}`;
        img.alt = `QR ${inviteUrl}`;
      } else if (img) {
        img.removeAttribute("src");
      }
      if (onlineEl) {
        const lanHint = (net.lan && net.lan[0]) || "";
        if (cloud && !String(inviteUrl).startsWith(cloud)) {
          const onlineInvite = `${String(cloud).replace(/\/$/, "")}/?room=${encodeURIComponent(code)}`;
          onlineEl.hidden = false;
          onlineEl.textContent = `ابری: ${onlineInvite}`;
          onlineEl.dataset.url = onlineInvite;
        } else if (isAndroidHost && lanHint) {
          onlineEl.hidden = false;
          onlineEl.textContent = "مهمان‌ها باید روی همان وای‌فای باشند و لینک/QR را اسکن کنند";
          delete onlineEl.dataset.url;
        } else if (tgInvite) {
          onlineEl.hidden = false;
          onlineEl.textContent = `تلگرام: ${tgInvite}`;
          onlineEl.dataset.url = tgInvite;
        } else {
          onlineEl.hidden = true;
          onlineEl.textContent = "";
          delete onlineEl.dataset.url;
        }
      }
    } catch (_) {
      const fallback = `${location.origin}/?room=${encodeURIComponent(code)}`;
      urlEl.textContent = fallback;
      urlEl.dataset.url = fallback;
      if (img && isHost) {
        img.src = `/api/qr?data=${encodeURIComponent(fallback)}&t=${Date.now()}`;
      } else if (img) {
        img.removeAttribute("src");
      }
      if (onlineEl) onlineEl.hidden = true;
      if (force) toast("IP شبکه خوانده نشد — از لینک فعلی استفاده شد", "warn");
    } finally {
      inviteQrBusy = false;
    }
  }

  function renderLobby() {
    $("#lobby-code").textContent = state.code;
    sessionStorage.setItem("mafi_room", state.code);
    document.body.classList.toggle("lobby-is-host", isHost);
    refreshInviteQr(false);
    syncInvitePanelMode();

    const pwdNotice = $("#invite-password-notice");
    if (pwdNotice) pwdNotice.hidden = !state.settings?.has_password;

    const tgHint = document.querySelector("#screen-lobby .invite-hint.invite-host-only");
    if (tgHint && (telegramMode || telegramConfig?.enabled)) {
      tgHint.textContent = "دعوت تلگرام — دوستان Mini App را باز می‌کنند";
    }

    const players = state.players.filter((p) => !p.is_spectator);
    const connected = players.filter((p) => p.connected !== false);
    $("#player-count").textContent = toFa(connected.length);

    const host = players.find((p) => p.is_host) || players.find((p) => p.sid === state.host_sid);
    $("#host-label").textContent = host ? `سازنده: ${host.name}` : "سازنده: —";
    $("#ready-label").textContent = `${toFa(connected.length)}/۶ آماده`;

    const list = $("#players-list");
    list.innerHTML = players
      .map((p) => {
        const tags = [];
        if (p.is_host) tags.push("سازنده");
        if (p.sid === mySid || p.sid === state.me?.sid) tags.push("شما");
        if (p.connected === false) tags.push("قطع");
        return `<div class="player-row ${p.is_host ? "host" : ""} ${
          p.sid === state.me?.sid ? "me" : ""
        } ${p.connected === false ? "offline" : ""}">
          <div class="player-avatar">${p.avatar}</div>
          <div class="player-info">
            <div class="name">${esc(p.name)}</div>
            <div class="tag">${tags.join(" · ") || "آماده"}</div>
          </div>
          ${isHost && p.sid !== mySid && !p.is_host ? `<button type="button" class="btn btn-ghost btn-sm kick-btn" data-kick="${p.sid}">اخراج</button>` : ""}
          ${p.sid !== mySid ? `<button type="button" class="btn btn-ghost btn-sm report-btn" data-report-sid="${p.sid}">گزارش</button>` : ""}
        </div>`;
      })
      .join("");
    list.querySelectorAll(".kick-btn").forEach((b) => {
      b.onclick = () => socket.emit("kick_player", { target_sid: b.dataset.kick });
    });
    list.querySelectorAll(".report-btn").forEach((b) => {
      b.onclick = () => {
        const reason = prompt("دلیل گزارش (اختیاری):", "") || "";
        socket.emit("report_player", { target_sid: b.dataset.reportSid, reason });
      };
    });

    // settings
    settingsLocked = true;
    const st = state.settings;
    $("#set-mafia").value = st.mafia_count;
    $("#set-mafia-val").textContent = toFa(st.mafia_count);
    $("#set-doctor").checked = st.doctor;
    $("#set-detective").checked = st.detective;
    $("#set-sniper").checked = st.sniper;
    if ($("#set-godfather")) $("#set-godfather").checked = !!st.godfather;
    if ($("#set-mayor")) $("#set-mayor").checked = !!st.mayor;
    if ($("#set-bodyguard")) $("#set-bodyguard").checked = !!st.bodyguard;
    if ($("#set-silencer")) $("#set-silencer").checked = !!st.silencer;
    if ($("#set-psych")) $("#set-psych").checked = !!st.psychiatrist;
    if ($("#set-killer")) $("#set-killer").checked = !!st.serial_killer;
    if ($("#set-sacrifice")) $("#set-sacrifice").checked = !!st.sacrifice;
    if ($("#set-reporter")) $("#set-reporter").checked = !!st.reporter;
    if ($("#set-natasha")) $("#set-natasha").checked = !!st.natasha;
    if ($("#set-joker")) $("#set-joker").checked = !!st.joker;
    if ($("#set-vigilante")) $("#set-vigilante").checked = !!st.vigilante;
    if ($("#set-bot-diff")) $("#set-bot-diff").value = st.bot_difficulty || "normal";
    if ($("#set-auto-roles")) $("#set-auto-roles").checked = st.auto_roles !== false;
    if ($("#set-mode")) $("#set-mode").value = st.game_mode || "classic";
    if ($("#set-narrator-rate")) $("#set-narrator-rate").value = st.narrator_rate || "normal";
    if ($("#set-narrator-voice")) {
      $("#set-narrator-voice").value = st.narrator_voice || "farid";
      if ($("#preview-voice")) $("#preview-voice").value = st.narrator_voice || "farid";
    }
    if ($("#set-tournament")) $("#set-tournament").checked = !!st.tournament;
    if ($("#set-ranked")) $("#set-ranked").checked = !!st.ranked;
    if ($("#set-spectator-delay")) $("#set-spectator-delay").value = st.spectator_delay ?? 30;
    $("#set-night").value = st.night_time;
    $("#set-night-val").textContent = toFa(st.night_time);
    $("#set-discuss").value = st.discuss_time;
    $("#set-discuss-val").textContent = toFa(st.discuss_time);
    $("#set-vote").value = st.vote_time;
    $("#set-vote-val").textContent = toFa(st.vote_time);
    if ($("#set-speak")) {
      $("#set-speak").value = st.speak_time || 30;
      $("#set-speak-val").textContent = toFa(st.speak_time || 30);
    }
    settingsLocked = false;

    const canEdit = isHost;
    $$("#settings-panel input, #settings-panel select").forEach((el) => (el.disabled = !canEdit));
    const settingsPanel = $("#settings-panel");
    if (settingsPanel) settingsPanel.classList.toggle("settings-readonly", !canEdit);
    const pwdInput = $("#set-password");
    if (pwdInput) {
      pwdInput.disabled = !canEdit;
      pwdInput.placeholder = canEdit
        ? state.settings?.has_password
          ? "رمز فعال — برای تغییر بنویسید"
          : "خالی = عمومی"
        : state.settings?.has_password
          ? "اتاق رمزدار — فقط میزبان می‌تواند تغییر دهد"
          : "عمومی";
    }
    if ($("#host-tools")) $("#host-tools").style.display = isHost ? "flex" : "none";
    if ($("#suspicion-box")) {
      const logs = state.suspicion_log || [];
      $("#suspicion-box").style.display = isHost && logs.length ? "block" : "none";
      if ($("#suspicion-list")) {
        $("#suspicion-list").innerHTML = logs
          .slice()
          .reverse()
          .map((l) => `<li><b>${esc(l.name)}</b>: ${esc(l.kind)} — ${esc(l.detail || "")}</li>`)
          .join("");
      }
    }

    // نقش‌های بازشده
    const unlockBox = $("#unlocked-roles");
    if (unlockBox && state.unlocked_roles) {
      unlockBox.innerHTML = state.unlocked_roles
        .map(
          (r) =>
            `<span class="role-chip ${r.unlocked ? "on" : "off"}" title="${esc(
              r.desc
            )}">${r.icon} ${esc(r.name)}${
              r.unlocked ? "" : ` · ${toFa(r.min_players)}+`
            }</span>`
        )
        .join("");
    }

    const canStart = connected.length >= 6 && !state.me?.is_spectator;
    $("#btn-start").disabled = !canStart;
    if (connected.length < 6) {
      $("#start-hint").textContent = `حداقل ۶ بازیکن وصل لازم است (${toFa(
        connected.length
      )}/۶)`;
    } else {
      $("#start-hint").textContent = "هر کسی می‌تواند شروع کند — بزنید!";
    }

    // sync lobby chat from state
    if (state.chat) {
      const log = $("#lobby-chat");
      if (log.children.length === 0) {
        state.chat.forEach((m) => appendChat("#lobby-chat", m, false));
      }
    }
  }

  function renderGame() {
    const phase = state.phase;
    const badge = $("#phase-badge");
    badge.textContent = PHASE_LABEL[phase] || phase;
    badge.className = "phase-badge";
    window.dispatchEvent(new CustomEvent("mafi:phase", { detail: badge.textContent }));
    if (phase.startsWith("night") || phase === "dealing")
      badge.classList.add("night");
    else if (phase === "day_vote") badge.classList.add("vote");
    else badge.classList.add("day");

    // my role chip
    if (state.me?.role && !state.me.is_spectator) {
      $("#my-role-chip").style.display = "flex";
      $("#my-role-icon").textContent = state.me.role_icon;
      $("#my-role-name").textContent = state.me.role_name;
      $("#my-role-chip").style.borderColor = state.me.role_color || "";
    }

    const isMafiaRole = ["mafia", "godfather", "silencer", "natasha"].includes(
      state.me?.role
    );
    $("#tab-mafia").style.display =
      isMafiaRole && state.me?.alive ? "block" : "none";

    if ($("#btn-chat-toggle")) $("#btn-chat-toggle").style.display = "";
    if ($("#btn-mic-fab")) $("#btn-mic-fab").style.display = "";

    const dockMic = $("#dock-mic");
    if (dockMic) dockMic.hidden = !!state.text_only;

    // دکمه پشت‌صحنه — مخفی، از dealing به بعد
    const adminBtn = $("#btn-admin-entry");
    if (adminBtn) {
      const showAdmin = state.phase && state.phase !== "lobby";
      adminBtn.style.display = showAdmin ? "flex" : "none";
    }

    renderGamePlayers();
    renderActionPanel();

    // وتوی شهردار
    let vetoBtn = $("#btn-mayor-veto");
    if (state.me?.role === "mayor" && state.me?.alive && !state.me?.mayor_veto_used) {
      if (!vetoBtn) {
        vetoBtn = document.createElement("button");
        vetoBtn.id = "btn-mayor-veto";
        vetoBtn.className = "btn btn-gold btn-sm";
        vetoBtn.textContent = "وتوی شهردار";
        vetoBtn.onclick = () => socket.emit("mayor_veto");
        $("#action-panel")?.prepend(vetoBtn);
      }
      vetoBtn.style.display =
        phase === "day_vote" || phase === "day_defense" ? "inline-block" : "none";
    } else if (vetoBtn) {
      vetoBtn.style.display = "none";
    }
  }

  function renderGamePlayers() {
    const box = $("#game-players");
    const phase = state.phase;
    const canSelect =
      ((phase === "day_vote" || phase === "day_trust") && state.me?.alive) ||
      needsNightAction();

    box.innerHTML = state.players
      .filter((p) => !p.is_spectator)
      .map((p) => {
        const cls = [
          "game-player",
          p.alive ? "" : "dead",
          p.known_mafia ? "known-mafia" : "",
          p.sid === mySid ? "me" : "",
          state.current_speaker === p.sid ? "speaking" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `<div class="${cls}" data-sid="${p.sid}">
          <div class="av">${p.avatar}</div>
          <div class="nm">${esc(p.name)}</div>
        </div>`;
      })
      .join("");

    if (canSelect) {
      $$(".game-player:not(.dead)", box).forEach((el) => {
        el.onclick = () => selectTarget(el.dataset.sid);
      });
    }
  }

  function needsNightAction() {
    const p = state.phase;
    const me = state.me;
    if (!me?.alive || me.is_spectator) return false;
    if (p === "night_mafia" && ["mafia", "godfather", "silencer", "natasha"].includes(me.role))
      return true;
    if (p === "night_silencer" && me.role === "silencer") return true;
    if (p === "night_natasha" && me.role === "natasha") return true;
    if (p === "night_doctor" && me.role === "doctor") return true;
    if (p === "night_bodyguard" && me.role === "bodyguard") return true;
    if (p === "night_detective" && me.role === "detective") return true;
    if (p === "night_psych" && me.role === "psychiatrist" && !me.psych_used) return true;
    if (p === "night_killer" && me.role === "serial_killer") return true;
    if (p === "night_sniper" && (me.role === "sniper" || me.role === "vigilante")) return true;
    return false;
  }

  function renderActionPanel() {
    const panel = $("#action-panel");
    if (
      !needsNightAction() &&
      state.phase !== "day_vote" &&
      state.phase !== "day_trust"
    ) {
      panel.style.display = "none";
      return;
    }

    panel.style.display = "block";
    let title = "انتخاب کنید";
    if (state.phase === "night_mafia") title = "قربانی را انتخاب کنید";
    if (state.phase === "night_silencer") title = "چه کسی را ساکت می‌کنید؟";
    if (state.phase === "night_natasha") title = "چه کسی را مجذوب می‌کنید؟";
    if (state.phase === "night_doctor") title = "چه کسی را نجات می‌دهید؟";
    if (state.phase === "night_bodyguard") title = "از چه کسی محافظت می‌کنید؟";
    if (state.phase === "night_detective") title = "از چه کسی استعلام می‌گیرید؟";
    if (state.phase === "night_psych") title = "نقش چه کسی را بلاک می‌کنید؟";
    if (state.phase === "night_killer") title = "جانی: قربانی؟";
    if (state.phase === "night_sniper") title = "هدف شلیک را انتخاب کنید";
    if (state.phase === "day_vote") title = "به چه کسی رأی می‌دهید؟";
    if (state.phase === "day_trust") title = "رأی اعتماد: چه کسی مشکوک است؟";
    $("#action-title").textContent = title;

    const targets = state.players.filter(
      (p) =>
        !p.is_spectator &&
        p.alive &&
        (state.phase === "day_vote" ? p.sid !== mySid : true)
    );

    $("#action-targets").innerHTML = targets
      .map(
        (p) =>
          `<button class="target-btn" data-sid="${p.sid}">${p.avatar} ${esc(
            p.name
          )}</button>`
      )
      .join("");

    $$(".target-btn").forEach((btn) => {
      btn.onclick = () => selectTarget(btn.dataset.sid);
    });

    $("#btn-skip-action").style.display =
      state.phase === "night_sniper" ? "inline-block" : "none";

    if (state.phase === "day_vote") {
      const skip = document.createElement("button");
      skip.className = "target-btn";
      skip.textContent = "⊘ رأی ممتنع";
      skip.onclick = () => {
        AudioSys.sfx("vote");
        socket.emit("cast_vote", { target: "skip" });
        toast("رأی ممتنع ثبت شد", "info");
      };
      $("#action-targets").appendChild(skip);
    }
  }

  function selectTarget(sid) {
    AudioSys.sfx("click");
    $$(".game-player").forEach((el) =>
      el.classList.toggle("selected", el.dataset.sid === sid)
    );
    const target = state.players.find((p) => p.sid === sid);

    if (state.phase === "day_vote" || state.phase === "day_trust") {
      socket.emit("cast_vote", { target: sid });
      toast("رأی ثبت شد", "success");
      playVoteCinematic(target?.name || "");
      const el = document.querySelector(`.game-player[data-sid="${CSS.escape(sid)}"]`);
      el?.classList.add("vote-pop");
      setTimeout(() => el?.classList.remove("vote-pop"), 600);
    } else if (needsNightAction()) {
      socket.emit("night_action", { target: sid });
    }
  }

  // ---------- Narrator ----------
  function onNarrator({ text, mood, audio }) {
    const box = $("#narrator");
    const el = $("#narrator-text");
    box.className = "narrator" + (mood ? ` mood-${mood}` : "");
    typewriter(el, text);
    // اول صدا، بعد افکت کوتاه — تا روی گوینده نرود
    AudioSys.playNarrator(text, audio);
    setTimeout(() => AudioSys.sfx("phase"), 120);
  }

  function onSpeakTurn(data) {
    if (!data) return;
    showSpeakBar({
      current_speaker: data.sid,
      speaker_name: data.name,
      speaker_avatar: data.avatar,
      speak_index: data.index - 1,
      speak_total: data.total,
      phase_ends_at: data.ends_at,
      me: state?.me,
      host_sid: state?.host_sid,
      is_challenge_turn: !!data.challenge,
    });
    if (data.ends_at) startTimer(data.ends_at, data.seconds);
    VoiceChat.applyMicPolicy();
  }

  function onChallengePending(pending) {
    if (!pending || !state) return;
    const amSpeaker =
      state.current_speaker === mySid || state.me?.sid === state.current_speaker;
    if (!amSpeaker && state.host_sid !== mySid) {
      // دیگران فقط toast می‌بینند
      return;
    }
    // صاحب نوبت پنل تصمیم را می‌بیند
    if (state.current_speaker === (state.me?.sid || mySid) || state.host_sid === mySid) {
      showChallengeDecide(pending);
    }
  }

  function showChallengeDecide(pending) {
    const box = $("#challenge-decide");
    box.style.display = "block";
    $("#cd-avatar").textContent = pending.from_avatar || "⚡";
    $("#cd-name").textContent = pending.from_name || "بازیکن";
    const when =
      pending.position === "before" ? "قبل از ادامه نوبت شما" : "بعد از نوبت شما";
    $("#cd-detail").textContent = `${toFa(pending.seconds)} ثانیه · ${when}`;
    window.__mafiDecideSec = +pending.seconds >= 20 ? 20 : 10;
    window.__mafiDecidePos = pending.position === "before" ? "before" : "after";
    $$("#cd-adjust [data-sec]").forEach((b) =>
      b.classList.toggle("active", +b.dataset.sec === window.__mafiDecideSec)
    );
    $$("#cd-adjust [data-pos]").forEach((b) =>
      b.classList.toggle("active", b.dataset.pos === window.__mafiDecidePos)
    );
    const bar = $("#cd-auto-bar");
    bar.style.animation = "none";
    void bar.offsetWidth;
    bar.style.animation = "autoShrink 8s linear forwards";
  }

  function hideChallengeDecide() {
    const box = $("#challenge-decide");
    if (box) box.style.display = "none";
  }

  function showSpeakBar(s) {
    const bar = $("#speak-bar");
    bar.style.display = "flex";
    bar.classList.toggle("challenge-mode", !!s.is_challenge_turn);
    $("#speak-av").textContent = s.speaker_avatar || "👤";
    $("#speak-name").textContent =
      (s.speaker_name || "—") + (s.is_challenge_turn ? " · چالش" : "");
    const idx = (s.speak_index ?? 0) + 1;
    const total = s.speak_total || 1;
    $("#speak-progress").textContent = `${toFa(idx)} از ${toFa(total)}`;
    const meSid = s.me?.sid || mySid;
    const canSkip = s.current_speaker === meSid || s.host_sid === mySid;
    $("#btn-skip-speak").style.display = canSkip ? "inline-block" : "none";

    const canChallenge =
      s.phase !== false &&
      state?.phase === "day_discuss" &&
      s.current_speaker !== meSid &&
      state?.me?.alive !== false &&
      !state?.me?.is_spectator &&
      !s.is_challenge_turn &&
      !state?.challenge_pending &&
      (state?.my_challenges_left ?? 2) > 0;
    $("#btn-challenge").style.display =
      state?.phase === "day_discuss" ? "inline-block" : "none";
    $("#btn-challenge").disabled = !canChallenge;

    if (s.phase_ends_at) {
      const totalSec =
        s.is_challenge_turn
          ? Math.max(1, Math.ceil(s.phase_ends_at - Date.now() / 1000))
          : state?.settings?.speak_time ||
            Math.max(1, Math.ceil(s.phase_ends_at - Date.now() / 1000));
      updateSpeakFill(s.phase_ends_at, totalSec);
    }
  }

  let speakFillInterval = null;
  function updateSpeakFill(endsAt, totalSec) {
    clearInterval(speakFillInterval);
    const tick = () => {
      const left = Math.max(0, endsAt - Date.now() / 1000);
      const pct = totalSec ? (left / totalSec) * 100 : 0;
      $("#speak-timer-fill").style.width = pct + "%";
      $("#speak-timer-num").textContent = toFa(Math.ceil(left));
      if (left <= 0) clearInterval(speakFillInterval);
    };
    tick();
    speakFillInterval = setInterval(tick, 200);
  }

  function typewriter(el, text) {
    el.textContent = "";
    let i = 0;
    const id = setInterval(() => {
      el.textContent = text.slice(0, ++i);
      if (i >= text.length) clearInterval(id);
    }, 28);
  }

  // ---------- Role Card ----------
  function onRoleReveal(player) {
    tgHaptic("heavy");
    showRoleCard(player, true);
  }

  function showRoleCard(player, animate) {
    cardFlipped = false;
    const card = $("#role-card");
    card.classList.remove("flipped");
    card.style.transform = "";
    $("#card-icon").textContent = player.role_icon || "🎭";
    $("#card-role-name").textContent = player.role_name || "";
    $("#card-role-desc").textContent = player.role_desc || "";
    $("#card-front").style.borderColor = player.role_color || "";
    $("#card-front").classList.toggle("mafia", player.role === "mafia");
    $("#card-role-name").style.color = player.role_color || "";

    $("#role-overlay").classList.add("show");
    if (animate) {
      card.classList.add("deal-in");
      AudioSys.sfx("deal");
      setTimeout(() => card.classList.remove("deal-in"), 1300);
    }
  }

  function flipCard() {
    if (cardFlipped) {
      $("#role-overlay").classList.remove("show");
      return;
    }
    cardFlipped = true;
    const card = $("#role-card");
    card.style.transform = "";
    card.classList.add("flipped");
    AudioSys.sfx("flip");
    Scene3D.shake(0.25);
    setTimeout(() => {
      $(".card-hint").textContent = "برای بستن لمس کنید";
    }, 800);
  }

  // ---------- Atmosphere ----------
  function onAtmosphere({ mode, winner }) {
    Scene3D.setMode(mode === "end" ? "end" : mode);
    if (mode === "night") AudioSys.playMusic("night");
    else if (mode === "day") AudioSys.playMusic("day");
    else if (mode === "lobby") AudioSys.playMusic("lobby");
    else if (mode === "end") {
      AudioSys.playMusic("end");
      AudioSys.sfx(winner === "town" ? "win" : "lose");
    }

    if (state?.phase === "day_vote") AudioSys.playMusic("vote");
  }

  function onDeath({ name, cinematic }) {
    AudioSys.sfx("death");
    Scene3D.shake(0.7);
    document.body.classList.add("shake");
    const flash = $("#death-flash");
    if (flash) {
      flash.classList.add("show");
      if (cinematic) flash.classList.add("cinematic");
    }
    // کارت بازیکن مرده
    document.querySelectorAll(".game-player").forEach((el) => {
      const p = state?.players?.find((x) => x.sid === el.dataset.sid);
      if (p && p.name === name) {
        el.classList.add("dead", "vote-pop");
        el.style.transition = "transform 0.6s ease, filter 0.6s ease";
        el.style.filter = "grayscale(1)";
        el.style.transform = "rotateY(180deg) scale(0.92)";
      }
    });
    setTimeout(() => {
      document.body.classList.remove("shake");
      flash?.classList.remove("show", "cinematic");
    }, 1400);
    toast(`${name} کشته شد`, "error");
  }

  function showEnd() {
    const overlay = $("#end-overlay");
    overlay.classList.add("show");
    const w = state.winner;
    $("#end-title").textContent =
      w === "town" ? "پیروزی شهروندان" : w === "killer" ? "پیروزی جانی" : "پیروزی مافیا";
    $("#end-sub").textContent =
      w === "town"
        ? "عدالت برقرار شد. شهر نفس کشید."
        : w === "killer"
        ? "جانی تنها بازمانده تاریکی است."
        : "تاریکی پیروز شد. شهر سقوط کرد.";

    $("#end-cards").innerHTML = state.players
      .filter((p) => !p.is_spectator)
      .map(
        (p) => `<div class="end-card ${p.alive ? "" : "dead-end cracked"}">
          <div class="ic">${p.role_icon || p.avatar}</div>
          <div class="rn">${esc(p.role_name || "?")}</div>
          <div class="pn">${esc(p.name)}</div>
        </div>`
      )
      .join("");

    const replay = $("#replay-list");
    if (replay) {
      const tl = state.timeline || [];
      replay.innerHTML = tl.length
        ? tl
            .map(
              (e) =>
                `<li><span class="tl-kind">${esc(e.kind)}</span> ${esc(e.text || "")}</li>`
            )
            .join("")
        : "<li>رویدادی ثبت نشد</li>";
    }

    $("#btn-rematch").style.display = isHost ? "inline-block" : "none";
  }

  function buildAvatarPicker() {
    const box = $("#avatar-picker");
    if (!box) return;
    const cur = selectedAvatar();
    box.innerHTML = AVATARS_FALLBACK.map(
      (a) =>
        `<button type="button" class="av-pick ${a === cur ? "on" : ""}" data-av="${a}">${a}</button>`
    ).join("");
    box.onclick = (e) => {
      const btn = e.target.closest(".av-pick");
      if (!btn) return;
      localStorage.setItem("mafi_avatar", btn.dataset.av);
      $$(".av-pick").forEach((b) => b.classList.toggle("on", b === btn));
      if (socket?.connected) socket.emit("set_avatar", { avatar: btn.dataset.av });
    };
  }

  function renderProfile(p) {
    const el = $("#profile-body");
    if (!el) return;
    if (!p || !p.token) {
      el.innerHTML = "<p>هنوز پروفایلی نیست — یک بازی بازی کن.</p>";
      return;
    }
    el.innerHTML = `
      <p style="font-size:2rem">${esc(p.avatar || "🎭")}</p>
      <p><strong>${esc(p.name || "")}</strong></p>
      <p>برد: ${toFa(p.wins || 0)} · باخت: ${toFa(p.losses || 0)}</p>
      <p>MMR: ${toFa(p.mmr || 1000)} · امتیاز رتبه: ${toFa(p.ranked_points || 0)} · فصل ${esc(p.season || "")}</p>
      <p>میزبانی: ${toFa(p.games_hosted || 0)} بازی</p>
      <p>نشان‌ها: ${(p.badges || []).map((b) => esc(b)).join("، ") || "—"}</p>
      <p>کازمتیک: ${(p.cosmetics || []).map((c) => esc(c)).join("، ") || "—"}</p>`;
  }

  function renderLeaderboard(d) {
    const ol = $("#leaderboard-list");
    if (!ol) return;
    const rows = d?.rows || [];
    ol.innerHTML = rows.length
      ? rows
          .map(
            (r, i) =>
              `<li>${toFa(i + 1)}. ${r.avatar || ""} ${esc(r.name || "?")} — MMR ${toFa(
                r.mmr || r.ranked_points || 0
              )}</li>`
          )
          .join("")
      : "<li>هنوز رتبه‌ای نیست</li>";
  }

  // ---------- Admin cheat panel ----------
  let adminUnlocked = false;
  let adminMinimized = false;
  let adminPasswordCache = "";
  let adminRefreshTimer = null;

  function startAdminRefresh() {
    stopAdminRefresh();
    adminRefreshTimer = setInterval(() => {
      if (
        adminUnlocked &&
        adminPasswordCache &&
        $("#admin-panel")?.style.display !== "none" &&
        !adminMinimized
      ) {
        socket.emit("admin_auth", { password: adminPasswordCache });
      }
    }, 3500);
  }

  function stopAdminRefresh() {
    if (adminRefreshTimer) {
      clearInterval(adminRefreshTimer);
      adminRefreshTimer = null;
    }
  }

  function bindAdminUI() {
    const entry = $("#btn-admin-entry");
    if (!entry) return;
    entry.onclick = () => {
      if (adminUnlocked && adminMinimized) {
        adminMinimized = false;
        $("#admin-panel")?.classList.remove("minimized");
        $("#admin-min-chip").style.display = "none";
        showAdminPanel(true);
        return;
      }
      if (adminUnlocked) {
        showAdminPanel(true);
        return;
      }
      $("#admin-auth-modal").style.display = "flex";
      $("#admin-pass").value = "";
      $("#admin-err").textContent = "";
      setTimeout(() => $("#admin-pass")?.focus(), 50);
    };
    $("#admin-min-chip")?.addEventListener("click", () => {
      adminMinimized = false;
      $("#admin-panel")?.classList.remove("minimized");
      $("#admin-min-chip").style.display = "none";
      showAdminPanel(true);
    });
    $("#btn-admin-cancel").onclick = () => {
      $("#admin-auth-modal").style.display = "none";
    };
    $("#btn-admin-login").onclick = () => {
      const pw = $("#admin-pass").value;
      socket.emit("admin_auth", { password: pw });
    };
    $("#admin-pass")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("#btn-admin-login").click();
    });
    $("#btn-admin-close").onclick = () => {
      showAdminPanel(false);
      adminUnlocked = false;
      adminMinimized = false;
      adminPasswordCache = "";
      lastAdminData = null;
      stopAdminRefresh();
      $("#admin-min-chip").style.display = "none";
    };
    $("#btn-admin-min").onclick = () => {
      adminMinimized = true;
      $("#admin-panel")?.classList.add("minimized");
      $("#admin-min-chip").style.display = "block";
    };
    $("#btn-admin-refresh").onclick = () => {
      if (adminPasswordCache)
        socket.emit("admin_auth", { password: adminPasswordCache });
    };
    $("#btn-admin-copy")?.addEventListener("click", copyAdminRoles);
    $("#admin-only-mafia")?.addEventListener("change", () => {
      if (lastAdminData) renderAdminPanel(lastAdminData);
    });
    $("#btn-admin-whisper")?.addEventListener("click", () => {
      const target = $("#admin-whisper-target")?.value;
      const text = $("#admin-whisper-text")?.value?.trim();
      if (!target || !text) return toast("هدف و متن لازم است", "warn");
      socket.emit("admin_whisper", {
        password: adminPasswordCache,
        target,
        text,
      });
      $("#admin-whisper-text").value = "";
    });
    $$(".admin-tab").forEach((tab) => {
      tab.onclick = () => {
        $$(".admin-tab").forEach((t) => t.classList.remove("on"));
        tab.classList.add("on");
        const id = tab.dataset.atab;
        $("#admin-roles").style.display = id === "roles" ? "grid" : "none";
        $("#admin-timeline").style.display = id === "timeline" ? "block" : "none";
        $("#admin-suspect").style.display = id === "suspect" ? "block" : "none";
        if ($("#admin-whisper"))
          $("#admin-whisper").style.display = id === "whisper" ? "flex" : "none";
        if ($("#admin-filter-wrap") || $("#admin-only-mafia")) {
          const filter = $(".admin-filter");
          if (filter) filter.style.display = id === "roles" ? "flex" : "none";
        }
      };
    });
  }

  let lastAdminData = null;

  function copyAdminRoles() {
    if (!lastAdminData?.players?.length) return;
    const lines = lastAdminData.players.map(
      (p) =>
        `${p.name}: ${p.role_name || "?"} (${p.team || "?"})${p.alive ? "" : " [مرده]"}`
    );
    const text = lines.join("\n");
    navigator.clipboard?.writeText(text).then(
      () => toast("لیست نقش‌ها کپی شد", "success"),
      () => toast(text, "info")
    );
  }

  function showAdminPanel(on) {
    const p = $("#admin-panel");
    if (!p) return;
    p.style.display = on ? "flex" : "none";
    p.setAttribute("aria-hidden", on ? "false" : "true");
    if (on) {
      adminMinimized = false;
      p.classList.remove("minimized");
      $("#admin-min-chip").style.display = "none";
      startAdminRefresh();
    } else {
      stopAdminRefresh();
    }
  }

  function onAdminAuthResult(d) {
    if (!d?.ok) {
      $("#admin-err").textContent = d?.message || "خطا";
      AudioSys.sfx("lose");
      return;
    }
    adminUnlocked = true;
    adminPasswordCache = $("#admin-pass")?.value || adminPasswordCache;
    window.__mafiAdminPass = adminPasswordCache;
    $("#admin-auth-modal").style.display = "none";
    showAdminPanel(true);
    renderAdminPanel(d);
    if (window.__mafiOnAdminAuth) window.__mafiOnAdminAuth(d);
    AudioSys.sfx("click");
  }

  function renderAdminPanel(d) {
    lastAdminData = d;
    $("#admin-meta").textContent = `${d.code || ""} · ${
      PHASE_LABEL[d.phase] || d.phase || ""
    } · روز ${toFa(d.day || 0)} · شب ${toFa(d.night || 0)}`;

    const live = d.live || {};
    const liveEl = $("#admin-live");
    if (liveEl) {
      liveEl.innerHTML = [
        `<span><b>صدا:</b> ${esc(live.voice_mode || "—")}</span>`,
        `<span><b>نوبت:</b> ${esc(live.current_speaker || "—")}</span>`,
        `<span><b>زنده:</b> ${toFa(live.alive ?? "—")}</span>`,
        `<span><b>رأی:</b> ${toFa(live.votes ?? 0)}</span>`,
        live.silenced ? `<span><b>ساکت:</b> ${esc(live.silenced)}</span>` : "",
        live.challenge ? `<span><b>چالش:</b> ${esc(live.challenge)}</span>` : "",
        live.winner ? `<span><b>برنده:</b> ${esc(live.winner)}</span>` : "",
      ]
        .filter(Boolean)
        .join("");
    }

    const onlyMafia = $("#admin-only-mafia")?.checked;
    const box = $("#admin-roles");
    box.innerHTML = (d.players || [])
      .map((p) => {
        const isMafia = p.team === "mafia";
        const dead = p.alive ? "" : "dead";
        const glow = isMafia ? "mafia-glow" : "";
        const dim = onlyMafia && !isMafia ? "dimmed" : "";
        return `<div class="admin-role-card ${dead} ${glow} ${dim}" style="--rc:${esc(
          p.role_color || "#888"
        )}">
          <div class="arc-top">
            <span class="arc-av">${p.avatar || "👤"}</span>
            <span class="arc-icon">${p.role_icon || "?"}</span>
          </div>
          <div class="arc-name">${esc(p.name)}</div>
          <div class="arc-role">${esc(p.role_name || "—")}</div>
          <div class="arc-tags">
            <span class="arc-team">${esc(p.team || "")}</span>
            ${p.is_host ? "<span>میزبان</span>" : ""}
            ${p.is_bot ? "<span>بات</span>" : ""}
            ${p.alive ? "" : "<span class='bad'>مرده</span>"}
            ${p.connected ? "" : "<span class='bad'>قطع</span>"}
          </div>
        </div>`;
      })
      .join("");

    const sel = $("#admin-whisper-target");
    if (sel) {
      sel.innerHTML = (d.players || [])
        .filter((p) => !p.is_bot)
        .map((p) => `<option value="${esc(p.sid)}">${esc(p.name)}</option>`)
        .join("");
    }

    $("#admin-timeline").innerHTML = (d.timeline || [])
      .slice()
      .reverse()
      .map((e) => `<div class="atl"><b>${esc(e.kind)}</b> ${esc(e.text || "")}</div>`)
      .join("") || "<div class='atl'>خالی</div>";

    $("#admin-suspect").innerHTML = (d.suspicion || [])
      .slice()
      .reverse()
      .map(
        (e) =>
          `<div class="atl"><b>${esc(e.name)}</b> · ${esc(e.kind)} — ${esc(
            e.detail || ""
          )}</div>`
      )
      .join("") || "<div class='atl'>خالی</div>";
  }

  function bindThemeUI() {
    const saved = localStorage.getItem("mafi_theme") || "classic";
    applyTheme(saved);
    $$(".theme-chip").forEach((chip) => {
      chip.classList.toggle("on", chip.dataset.theme === saved);
      chip.onclick = () => {
        applyTheme(chip.dataset.theme);
        $$(".theme-chip").forEach((c) =>
          c.classList.toggle("on", c === chip)
        );
        AudioSys.sfx("click");
      };
    });
  }

  function applyTheme(name) {
    const t = ["classic", "blood", "neon"].includes(name) ? name : "classic";
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("mafi_theme", t);
  }

  function bindVoicePreview() {
    const btn = $("#btn-preview-voice");
    if (!btn) return;
    btn.onclick = async () => {
      await AudioSys.unlock();
      const voice = $("#preview-voice")?.value || "farid";
      const rate = $("#set-narrator-rate")?.value || "normal";
      btn.disabled = true;
      btn.textContent = "در حال ساخت صدا...";
      socket.emit("preview_voice", { voice, rate });
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = "پخش نمونه";
      }, 4000);
    };
  }

  let deferredPrompt = null;
  function bindPwaInstall() {
    const btn = $("#btn-install-pwa");
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      if (btn) btn.style.display = "block";
    });
    btn?.addEventListener("click", async () => {
      if (!deferredPrompt) {
        toast("از منوی مرورگر «Add to Home Screen» را بزن", "info");
        return;
      }
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      btn.style.display = "none";
    });
  }

  function renderLeaderboardHome(d) {
    const ol = $("#leaderboard-list-home");
    if (!ol) return;
    if (d?.season) {
      const s = $("#lb-season");
      if (s) s.textContent = `فصل ${d.season}`;
    }
    const rows = d?.rows || [];
    ol.innerHTML = rows.length
      ? rows
          .map(
            (r, i) =>
              `<li><span>${toFa(i + 1)}</span><span>${r.avatar || "🎭"}</span><strong>${esc(
                r.name || "?"
              )}</strong><span style="margin-right:auto;color:var(--gold)">${toFa(
                r.ranked_points || 0
              )}</span></li>`
          )
          .join("")
      : "<li>هنوز رتبه‌ای ثبت نشده — بازی رتبه‌دار بازی کنید</li>";
  }

  function playVoteCinematic(name) {
    const el = $("#vote-cinematic");
    if (!el) return;
    el.innerHTML = `<div class="vc-chip">رأی · ${esc(name || "")}</div>`;
    el.classList.add("show");
    AudioSys.sfx("vote");
    setTimeout(() => el.classList.remove("show"), 900);
  }

  function showDetectiveResult(res) {
    const existing = $(".detective-banner");
    if (existing) existing.remove();
    const div = document.createElement("div");
    div.className = "detective-banner";
    div.innerHTML = `<strong>نتیجه استعلام</strong><br/>${esc(res.message)}`;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 5000);
  }

  // ---------- Timer ----------
  function startTimer(endsAt, totalOverride) {
    clearInterval(timerInterval);
    const remaining = () => Math.max(0, Math.ceil(endsAt - Date.now() / 1000));
    timerTotal = totalOverride || remaining() || 30;

    function tick() {
      const left = remaining();
      $("#timer-text").textContent = toFa(left);
      const pct = timerTotal ? (left / timerTotal) * 100 : 0;
      $("#timer-fg").setAttribute("stroke-dasharray", `${pct}, 100`);
      if (left <= 5) $("#timer-fg").style.stroke = "#ef4444";
      else $("#timer-fg").style.stroke = "";
      if (left <= 0) clearInterval(timerInterval);
    }
    tick();
    timerInterval = setInterval(tick, 250);
  }

  // ---------- Helpers ----------
  function toast(msg, type = "info") {
    window.__mafiToast = toast;
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    AudioSys.sfx("toast");
    setTimeout(() => el.remove(), 3200);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        ok ? resolve() : reject(new Error("copy failed"));
      } catch (e) {
        reject(e);
      }
    });
  }

  function showModal(id) {
    $(`#${id}`).classList.add("show");
  }

  function appendChat(sel, msg, mafia) {
    const log = $(sel);
    if (!log) return;
    const div = document.createElement("div");
    div.className = "chat-msg";
    div.innerHTML = `<span class="who">${esc(msg.name)}</span>${esc(msg.text)}`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
