/* Web Audio — موسیقی و افکت‌های رویه‌ای مافیا */
const AudioSys = (() => {
  let ctx = null;
  let master = null;
  let musicGain = null;
  let sfxGain = null;
  let voiceGain = null;
  let musicNodes = [];
  let ambientNodes = [];
  let currentMood = "lobby";
  let muted = false;
  let started = false;

  const vols = { music: 0.4, sfx: 0.6, voice: 0.8 };

  function ensure() {
    if (ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 1;
    master.connect(ctx.destination);

    musicGain = ctx.createGain();
    musicGain.gain.value = vols.music;
    musicGain.connect(master);

    sfxGain = ctx.createGain();
    sfxGain.gain.value = vols.sfx;
    sfxGain.connect(master);

    voiceGain = ctx.createGain();
    voiceGain.gain.value = vols.voice;
    voiceGain.connect(master);
  }

  async function unlock() {
    ensure();
    if (ctx.state === "suspended") await ctx.resume();
    if (!started) {
      started = true;
      playMusic("lobby");
    }
  }

  function stopMusic() {
    musicNodes.forEach((n) => {
      try {
        n.stop();
      } catch (_) {}
      try {
        n.disconnect();
      } catch (_) {}
    });
    musicNodes = [];
    ambientNodes.forEach((n) => {
      try {
        n.stop();
      } catch (_) {}
      try {
        n.disconnect();
      } catch (_) {}
    });
    ambientNodes = [];
  }

  function drone(freq, type, gainVal, dest) {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    g.gain.value = gainVal;
    osc.connect(g);
    g.connect(dest);
    osc.start();
    return { osc, g };
  }

  function softPad(freq, gainVal, filterFreq) {
    const now = ctx.currentTime;
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = filterFreq;
    filter.Q.value = 0.7;
    filter.connect(musicGain);

    // دو اسیلاتور کمی دتیون برای حس گرم‌تر
    [0, 0.15, -0.12].forEach((detune, i) => {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = i === 0 ? "sine" : "triangle";
      osc.frequency.value = freq;
      osc.detune.value = detune * 100;
      g.gain.value = 0;
      g.gain.setValueAtTime(0, now);
      g.gain.linearRampToValueAtTime(gainVal / (i + 1), now + 2 + i * 0.4);
      osc.connect(g);
      g.connect(filter);
      osc.start();

      const lfo = ctx.createOscillator();
      const lg = ctx.createGain();
      lfo.type = "sine";
      lfo.frequency.value = 0.05 + i * 0.02;
      lg.gain.value = 2 + i;
      lfo.connect(lg);
      lg.connect(osc.frequency);
      lfo.start();
      musicNodes.push(osc, g, lfo, lg);
    });
    musicNodes.push(filter);
  }

  function playMusic(mood) {
    if (!ctx || muted) {
      currentMood = mood;
      return;
    }
    ensure();
    stopMusic();
    currentMood = mood;
    // Always use rich procedural beds (reliable offline + mobile); optional files can layer later
    _playProcedural(mood);
  }

  function _playProcedural(mood) {
    // Crossfade-style attack already in softPad (2s ramp)
    const beds = {
      lobby: [
        [48, 0.05, 420],
        [72, 0.03, 560],
        [96, 0.02, 700],
        [144, 0.014, 900],
        [192, 0.008, 1200],
      ],
      night: [
        [36, 0.06, 260],
        [54, 0.035, 340],
        [72, 0.022, 460],
        [108, 0.014, 580],
        [27, 0.04, 220],
      ],
      day: [
        [55, 0.045, 720],
        [82.5, 0.028, 920],
        [110, 0.018, 1120],
        [165, 0.012, 1400],
      ],
      vote: [
        [42, 0.052, 320],
        [63, 0.032, 430],
        [84, 0.02, 540],
        [126, 0.014, 700],
      ],
      end: [
        [60, 0.055, 650],
        [90, 0.032, 850],
        [120, 0.02, 1000],
        [180, 0.012, 1300],
      ],
    };

    (beds[mood] || beds.lobby).forEach(([f, g, ff]) => softPad(f, g, ff));

    // نویز نرم محیطی
    try {
      const bufferSize = 2 * ctx.sampleRate;
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * 0.015;
      const noise = ctx.createBufferSource();
      noise.buffer = noiseBuffer;
      noise.loop = true;
      const ng = ctx.createGain();
      const nf = ctx.createBiquadFilter();
      nf.type = "lowpass";
      nf.frequency.value = mood === "night" ? 400 : 800;
      ng.gain.value = mood === "night" ? 0.35 : 0.18;
      noise.connect(nf);
      nf.connect(ng);
      ng.connect(musicGain);
      noise.start();
      musicNodes.push(noise, ng, nf);
    } catch (_) {}

    if (mood === "night") {
      const interval = setInterval(() => {
        if (currentMood !== "night" || muted || !ctx) {
          clearInterval(interval);
          return;
        }
        chirp();
      }, 3200 + Math.random() * 2400);
      ambientNodes.push({ stop: () => clearInterval(interval), disconnect() {} });
    }
  }

  function chirp() {
    if (!ctx || muted) return;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    const f = ctx.createBiquadFilter();
    f.type = "bandpass";
    f.frequency.value = 2800;
    f.Q.value = 8;
    osc.type = "sine";
    const now = ctx.currentTime;
    osc.frequency.setValueAtTime(2600, now);
    osc.frequency.exponentialRampToValueAtTime(2100, now + 0.07);
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.02 * vols.sfx, now + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, now + 0.09);
    osc.connect(f);
    f.connect(g);
    g.connect(sfxGain);
    osc.start(now);
    osc.stop(now + 0.1);
  }

  function beep(freq, dur, type = "sine", vol = 0.15) {
    if (!ctx || muted) return;
    ensure();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    const f = ctx.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.value = Math.min(4000, freq * 3);
    osc.type = type === "sawtooth" || type === "square" ? "triangle" : type;
    osc.frequency.value = freq;
    const now = ctx.currentTime;
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(vol * vols.sfx * 0.85, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, now + dur);
    osc.connect(f);
    f.connect(g);
    g.connect(sfxGain);
    osc.start(now);
    osc.stop(now + dur + 0.05);
  }

  function sfx(name) {
    if (!ctx || muted) return;
    ensure();
    switch (name) {
      case "click":
        beep(800, 0.06, "sine", 0.08);
        break;
      case "deal":
        beep(220, 0.2, "triangle", 0.12);
        setTimeout(() => beep(330, 0.25, "triangle", 0.1), 150);
        setTimeout(() => beep(440, 0.3, "sine", 0.12), 350);
        break;
      case "flip":
        beep(180, 0.15, "sawtooth", 0.06);
        setTimeout(() => beep(400, 0.2, "sine", 0.1), 200);
        break;
      case "death":
        beep(120, 0.4, "sawtooth", 0.18);
        setTimeout(() => beep(80, 0.6, "sine", 0.15), 200);
        setTimeout(() => beep(50, 0.8, "triangle", 0.12), 500);
        break;
      case "vote":
        beep(500, 0.1, "square", 0.06);
        break;
      case "win":
        [523, 659, 784, 1046].forEach((f, i) =>
          setTimeout(() => beep(f, 0.35, "sine", 0.12), i * 180)
        );
        break;
      case "lose":
        [400, 350, 280, 200].forEach((f, i) =>
          setTimeout(() => beep(f, 0.4, "triangle", 0.12), i * 220)
        );
        break;
      case "toast":
        beep(660, 0.08, "sine", 0.06);
        break;
      case "phase":
        beep(300, 0.25, "sine", 0.1);
        setTimeout(() => beep(450, 0.3, "triangle", 0.08), 200);
        break;
      default:
        break;
    }
  }

  let narratorAudio = null;

  function duckMusic(on) {
    if (!musicGain || muted) return;
    const target = on ? vols.music * 0.08 : vols.music;
    try {
      musicGain.gain.cancelScheduledValues(ctx.currentTime);
      musicGain.gain.linearRampToValueAtTime(target, ctx.currentTime + 0.45);
    } catch (_) {
      musicGain.gain.value = target;
    }
  }

  function stopNarrator() {
    if (narratorAudio) {
      try {
        if (typeof narratorAudio.stop === "function") narratorAudio.stop();
        if (typeof narratorAudio.pause === "function") narratorAudio.pause();
        if ("src" in narratorAudio) narratorAudio.src = "";
      } catch (_) {}
      narratorAudio = null;
    }
    try {
      speechSynthesis.cancel();
    } catch (_) {}
    duckMusic(false);
  }

  /** گوینده Farid Neural — واضح، طبیعی، بدون خراب کردن تلفظ */
  async function playNarrator(text, audioUrl) {
    if (muted) return;
    ensure();
    if (ctx.state === "suspended") {
      try {
        await ctx.resume();
      } catch (_) {}
    }
    stopNarrator();
    duckMusic(true);

    if (audioUrl) {
      try {
        const url =
          audioUrl + (audioUrl.includes("?") ? "&" : "?") + "v=7";
        const res = await fetch(url, { cache: "force-cache" });
        if (!res.ok) throw new Error("tts http " + res.status);
        const buf = await res.arrayBuffer();
        const audioBuf = await ctx.decodeAudioData(buf.slice(0));
        const src = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.playbackRate.value = 1.0;

        // EQ خیلی ملایم — فقط کمی گرما، بدون خش و اکو
        const warm = ctx.createBiquadFilter();
        warm.type = "lowshelf";
        warm.frequency.value = 180;
        warm.gain.value = 2.2;

        const clarity = ctx.createBiquadFilter();
        clarity.type = "peaking";
        clarity.frequency.value = 2800;
        clarity.Q.value = 0.9;
        clarity.gain.value = 1.8;

        const air = ctx.createBiquadFilter();
        air.type = "highshelf";
        air.frequency.value = 5500;
        air.gain.value = 1.2;

        const comp = ctx.createDynamicsCompressor();
        comp.threshold.value = -18;
        comp.knee.value = 12;
        comp.ratio.value = 2.2;
        comp.attack.value = 0.01;
        comp.release.value = 0.2;

        const g = ctx.createGain();
        const now = ctx.currentTime;
        const target = Math.min(1.25, vols.voice * 1.15);
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(target, now + 0.08);

        src.connect(warm);
        warm.connect(clarity);
        clarity.connect(air);
        air.connect(comp);
        comp.connect(g);
        g.connect(voiceGain);

        narratorAudio = {
          stop: () => {
            try {
              src.stop();
            } catch (_) {}
          },
        };
        src.onended = () => duckMusic(false);
        src.start(0);
        return;
      } catch (err) {
        console.warn("[narrator] decode failed, fallback Audio()", err);
        try {
          const a = new Audio(
            audioUrl + (audioUrl.includes("?") ? "&" : "?") + "v=7"
          );
          a.playbackRate = 1.0;
          a.volume = Math.min(1, vols.voice);
          narratorAudio = a;
          a.onended = () => duckMusic(false);
          a.onerror = () => {
            duckMusic(false);
            speak(text);
          };
          await a.play();
          return;
        } catch (_) {}
      }
    }

    speak(text);
    const ms = Math.min(16000, 2000 + (text || "").length * 70);
    setTimeout(() => duckMusic(false), ms);
  }

  function speak(text) {
    if (!window.speechSynthesis || muted) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "fa-IR";
      u.rate = 0.92;
      u.pitch = 0.9;
      u.volume = Math.min(1, vols.voice);
      const voices = speechSynthesis.getVoices();
      const score = (v) => {
        const n = (v.name || "").toLowerCase();
        let s = 0;
        if (/farid/.test(n)) s += 100;
        if (/fa-ir|persian|farsi/.test(n + " " + (v.lang || "").toLowerCase()))
          s += 50;
        if ((v.lang || "").toLowerCase().startsWith("fa")) s += 40;
        if (/male|مرد/.test(n)) s += 10;
        return s;
      };
      const sorted = [...voices].sort((a, b) => score(b) - score(a));
      if (sorted.length && score(sorted[0]) > 0) u.voice = sorted[0];
      speechSynthesis.speak(u);
    } catch (_) {}
  }

  function setVol(type, v) {
    const n = Math.max(0, Math.min(1, v));
    vols[type] = n;
    if (!ctx) return;
    if (type === "music" && musicGain) musicGain.gain.value = muted ? 0 : n;
    if (type === "sfx" && sfxGain) sfxGain.gain.value = n;
    if (type === "voice") {
      vols.voice = n;
      if (narratorAudio) narratorAudio.volume = n;
    }
  }

  function toggleMute() {
    muted = !muted;
    if (musicGain) musicGain.gain.value = muted ? 0 : vols.music;
    if (muted) {
      stopNarrator();
      stopMusic();
    } else if (started) {
      playMusic(currentMood);
    }
    return muted;
  }

  function setMuted(m) {
    if (muted !== m) toggleMute();
  }

  return {
    unlock,
    playMusic,
    sfx,
    speak,
    playNarrator,
    stopNarrator,
    setVol,
    toggleMute,
    setMuted,
    isMuted: () => muted,
    getMood: () => currentMood,
  };
})();

window.AudioSys = AudioSys;
