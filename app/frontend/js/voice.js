/* WebRTC Voice Chat — STUN/TURN + Opus preferred */
const VoiceChat = (() => {
  let socket = null;
  let localStream = null;
  let mySid = null;
  let peers = new Map();
  let enabled = false;
  let micMuted = true;
  let wantTransmit = false;
  let policy = { mode: "all", speaker: null, phase: "lobby" };
  let meAlive = true;
  let meMafia = false;
  let meSpectator = false;
  let meSilenced = false;

  let ICE = {
    iceServers: [
      { urls: "stun:stun.l.google.com:19302" },
      { urls: "stun:stun1.l.google.com:19302" },
    ],
  };

  function setIceServers(servers) {
    if (Array.isArray(servers) && servers.length) {
      ICE = { iceServers: servers };
    }
  }

  async function preferOpus(pc) {
    try {
      const transceivers = pc.getTransceivers?.() || [];
      for (const tr of transceivers) {
        if (tr.receiver?.track?.kind !== "audio") continue;
        const caps = RTCRtpSender.getCapabilities?.("audio");
        if (!caps?.codecs) continue;
        const opus = caps.codecs.filter(
          (c) => c.mimeType?.toLowerCase() === "audio/opus"
        );
        if (opus.length && tr.setCodecPreferences) {
          tr.setCodecPreferences(opus.concat(caps.codecs.filter((c) => !opus.includes(c))));
        }
      }
    } catch (_) {}
  }

  function init(sock) {
    socket = sock;
    socket.on("voice_peers", ({ peers: list }) => {
      (list || []).forEach((sid) => connectTo(sid, true));
    });
    socket.on("voice_peer_joined", ({ sid }) => {
      if (!sid || sid === mySid) return;
      if (mySid && mySid < sid) connectTo(sid, true);
    });
    socket.on("voice_peer_left", ({ sid }) => closePeer(sid));
    socket.on("webrtc_offer", async ({ from, sdp }) => {
      await handleOffer(from, sdp);
    });
    socket.on("webrtc_answer", async ({ from, sdp }) => {
      const p = peers.get(from);
      if (p?.pc && sdp) {
        try {
          await p.pc.setRemoteDescription(sdp);
        } catch (_) {}
      }
    });
    socket.on("webrtc_ice", async ({ from, candidate }) => {
      const p = peers.get(from);
      if (p?.pc && candidate) {
        try {
          await p.pc.addIceCandidate(candidate);
        } catch (_) {}
      }
    });
    socket.on("voice_policy", (p) => {
      policy = p || policy;
      applyMicPolicy();
      updateUI();
    });
  }

  function setIdentity(sid) {
    mySid = sid;
  }

  function setPlayerFlags({
    alive = true,
    mafia = false,
    spectator = false,
    silenced = false,
  } = {}) {
    meAlive = alive;
    meMafia = mafia;
    meSpectator = spectator;
    meSilenced = silenced;
    applyMicPolicy();
  }

  async function enable() {
    if (enabled) return true;
    try {
      localStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 48000,
        },
        video: false,
      });
      enabled = true;
      micMuted = false;
      localStream.getAudioTracks().forEach((t) => {
        t.enabled = false;
      });
      socket.emit("voice_ready");
      applyMicPolicy();
      updateUI();
      return true;
    } catch (e) {
      console.warn("mic error", e);
      updateUI();
      return false;
    }
  }

  function toggleMute() {
    micMuted = !micMuted;
    applyMicPolicy();
    updateUI();
    return micMuted;
  }

  function canTransmit() {
    if (!enabled || micMuted || meSpectator) return false;
    if (!meAlive && policy.phase !== "lobby") return false;
    if (meSilenced && policy.phase === "day_discuss") return false;
    const mode = policy.mode || "all";
    if (mode === "mute") return false;
    if (mode === "all") return true;
    if (mode === "speaker") return policy.speaker === mySid;
    if (mode === "mafia") return meMafia;
    return false;
  }

  function applyMicPolicy() {
    wantTransmit = canTransmit();
    if (localStream) {
      localStream.getAudioTracks().forEach((t) => {
        t.enabled = wantTransmit;
      });
    }
    updateUI();
  }

  async function connectTo(remoteSid, asOfferer) {
    if (!enabled || !localStream || remoteSid === mySid) return;
    if (peers.has(remoteSid)) return;

    const pc = new RTCPeerConnection(ICE);
    const entry = { pc, audio: null };
    peers.set(remoteSid, entry);

    localStream.getTracks().forEach((track) => {
      pc.addTrack(track, localStream);
    });

    pc.onicecandidate = (ev) => {
      if (ev.candidate) {
        socket.emit("webrtc_ice", { to: remoteSid, candidate: ev.candidate });
      }
    };

    pc.ontrack = (ev) => {
      let audio = entry.audio;
      if (!audio) {
        audio = document.createElement("audio");
        audio.autoplay = true;
        audio.playsInline = true;
        audio.dataset.peer = remoteSid;
        audio.style.display = "none";
        document.body.appendChild(audio);
        entry.audio = audio;
      }
      audio.srcObject = ev.streams[0];
      audio.play().catch(() => {});
    };

    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) {
        if (pc.connectionState === "failed" && asOfferer) {
          closePeer(remoteSid);
          setTimeout(() => connectTo(remoteSid, true), 1500);
        }
      }
    };

    if (asOfferer) {
      try {
        const offer = await pc.createOffer({
          offerToReceiveAudio: true,
          offerToReceiveVideo: false,
        });
        await preferOpus(pc);
        await pc.setLocalDescription(offer);
        socket.emit("webrtc_offer", { to: remoteSid, sdp: pc.localDescription });
      } catch (_) {
        closePeer(remoteSid);
      }
    }
  }

  async function handleOffer(from, sdp) {
    if (!enabled || !localStream) return;
    let entry = peers.get(from);
    if (!entry) {
      await connectTo(from, false);
      entry = peers.get(from);
    }
    if (!entry) return;
    try {
      await entry.pc.setRemoteDescription(sdp);
      const answer = await entry.pc.createAnswer();
      await preferOpus(entry.pc);
      await entry.pc.setLocalDescription(answer);
      socket.emit("webrtc_answer", { to: from, sdp: entry.pc.localDescription });
    } catch (_) {}
  }

  function closePeer(sid) {
    const entry = peers.get(sid);
    if (!entry) return;
    try {
      entry.pc.close();
    } catch (_) {}
    if (entry.audio) {
      entry.audio.srcObject = null;
      entry.audio.remove();
    }
    peers.delete(sid);
  }

  function shutdown() {
    [...peers.keys()].forEach(closePeer);
    if (localStream) {
      localStream.getTracks().forEach((t) => t.stop());
      localStream = null;
    }
    enabled = false;
    updateUI();
  }

  function updateUI() {
    const btn = document.getElementById("btn-mic");
    const status = document.getElementById("mic-status");
    const live = document.getElementById("mic-live-dot");
    if (!btn) return;

    if (!enabled) {
      btn.className = "mic-btn off";
      btn.innerHTML = "<span>🎙</span><small>فعال‌سازی مایک</small>";
      if (status) status.textContent = "مایک خاموش";
      if (live) live.classList.remove("on");
      return;
    }

    if (wantTransmit) {
      btn.className = "mic-btn live";
      btn.innerHTML = "<span>🎙</span><small>در حال صحبت</small>";
      if (status) status.textContent = "شما صحبت می‌کنید";
      if (live) live.classList.add("on");
    } else if (micMuted) {
      btn.className = "mic-btn muted";
      btn.innerHTML = "<span>🔇</span><small>قطع دستی</small>";
      if (status) status.textContent = "مایک قطع است";
      if (live) live.classList.remove("on");
    } else {
      btn.className = "mic-btn wait";
      btn.innerHTML = "<span>🎙</span><small>منتظر نوبت</small>";
      const mode = policy.mode;
      if (status) {
        if (mode === "speaker") status.textContent = "نوبت شخص دیگری است";
        else if (mode === "mafia") status.textContent = "فقط مافیا صحبت می‌کنند";
        else if (mode === "mute") status.textContent = "صحبت مجاز نیست";
        else status.textContent = "آماده";
      }
      if (live) live.classList.remove("on");
    }
  }

  let pttMode = false;

  function setPttMode(on) {
    pttMode = !!on;
    if (pttMode && enabled) {
      micMuted = true;
      wantTransmit = false;
      applyMicPolicy();
      updateUI();
    }
    bindPttControls();
  }

  function bindPttControls() {
    const btn = document.getElementById("btn-mic");
    if (!btn || btn.dataset.pttBound) return;
    btn.dataset.pttBound = "1";
    const down = () => {
      if (!pttMode || !enabled) return;
      micMuted = false;
      wantTransmit = true;
      applyMicPolicy();
      updateUI();
    };
    const up = () => {
      if (!pttMode || !enabled) return;
      micMuted = true;
      wantTransmit = false;
      applyMicPolicy();
      updateUI();
    };
    btn.addEventListener("pointerdown", down);
    btn.addEventListener("pointerup", up);
    btn.addEventListener("pointerleave", up);
  }

  return {
    init,
    setIdentity,
    setPlayerFlags,
    enable,
    toggleMute,
    applyMicPolicy,
    shutdown,
    isEnabled: () => enabled,
    isTransmitting: () => wantTransmit,
    setPttMode,
    bindPttControls,
    setIceServers,
  };
})();

window.VoiceChat = VoiceChat;
