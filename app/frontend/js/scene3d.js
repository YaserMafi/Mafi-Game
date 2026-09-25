/* Three.js — صحنه اتمسفری بهینه‌شده برای موبایل */
const Scene3D = (() => {
  let renderer, scene, camera, clock;
  let stars, moon, sun, clouds = [];
  let particles;
  let animId = null;
  let quality = "medium";
  let mode = "lobby"; // lobby | night | day | end
  let targetBg = { r: 0.03, g: 0.03, b: 0.06 };
  let currentBg = { ...targetBg };
  let camShake = 0;
  let reduced = false;

  const QUALITY = {
    low: { stars: 400, particles: 40, pixelRatio: 1, antialias: false },
    medium: { stars: 900, particles: 80, pixelRatio: 1.5, antialias: false },
    high: { stars: 1800, particles: 160, pixelRatio: 2, antialias: true },
  };

  function detectQuality() {
    const mobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    const cores = navigator.hardwareConcurrency || 4;
    const mem = navigator.deviceMemory || 4;
    if (mobile || cores <= 4 || mem <= 4) return "low";
    if (cores <= 6 || mem <= 6) return "medium";
    return "high";
  }

  function init(canvas) {
    quality = localStorage.getItem("mafi_gfx") || detectQuality();
    const q = QUALITY[quality] || QUALITY.medium;
    reduced = quality === "low";

    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: q.antialias,
      alpha: true,
      powerPreference: quality === "high" ? "high-performance" : "default",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, q.pixelRatio));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x07070c, 1);

    scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x07070c, 0.012);

    camera = new THREE.PerspectiveCamera(
      55,
      window.innerWidth / window.innerHeight,
      0.1,
      500
    );
    camera.position.set(0, 2, 18);

    clock = new THREE.Clock();

    const amb = new THREE.AmbientLight(0x334466, 0.4);
    scene.add(amb);
    const dir = new THREE.DirectionalLight(0xc9a84c, 0.3);
    dir.position.set(5, 10, 5);
    scene.add(dir);

    createStars(q.stars);
    createMoon();
    createSun();
    createClouds();
    createParticles(q.particles);

    bindViewport();
    animate();
    setMode("lobby");
  }

  function createStars(count) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const r = 80 + Math.random() * 120;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.cos(phi) * 0.5 + 20;
      pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
      sizes[i] = Math.random();
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({
      color: 0xfff5d6,
      size: 0.35,
      transparent: true,
      opacity: 0.85,
      sizeAttenuation: true,
      depthWrite: false,
    });
    stars = new THREE.Points(geo, mat);
    scene.add(stars);
  }

  function createMoon() {
    const geo = new THREE.SphereGeometry(reduced ? 2.2 : 3, reduced ? 16 : 32, reduced ? 16 : 32);
    const mat = new THREE.MeshStandardMaterial({
      color: 0xf5e6c8,
      emissive: 0xc9a84c,
      emissiveIntensity: 0.35,
      roughness: 0.8,
      metalness: 0.1,
    });
    moon = new THREE.Mesh(geo, mat);
    moon.position.set(-12, 14, -40);
    scene.add(moon);

    const glowGeo = new THREE.SphereGeometry(reduced ? 3.5 : 5, 16, 16);
    const glowMat = new THREE.MeshBasicMaterial({
      color: 0xc9a84c,
      transparent: true,
      opacity: 0.08,
      depthWrite: false,
    });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    moon.add(glow);
  }

  function createSun() {
    const geo = new THREE.SphereGeometry(reduced ? 2.5 : 3.5, reduced ? 12 : 24, reduced ? 12 : 24);
    const mat = new THREE.MeshBasicMaterial({ color: 0xffd27a });
    sun = new THREE.Mesh(geo, mat);
    sun.position.set(14, -30, -50);
    sun.visible = false;
    scene.add(sun);
  }

  function createClouds() {
    const n = reduced ? 3 : 6;
    for (let i = 0; i < n; i++) {
      const g = new THREE.Group();
      const mat = new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.08,
        depthWrite: false,
      });
      for (let j = 0; j < (reduced ? 2 : 3); j++) {
        const s = new THREE.Mesh(
          new THREE.SphereGeometry(1.5 + Math.random(), 8, 8),
          mat
        );
        s.position.set(j * 1.5 - 1, Math.random() * 0.5, Math.random());
        g.add(s);
      }
      g.position.set(
        (Math.random() - 0.5) * 40,
        6 + Math.random() * 8,
        -20 - Math.random() * 20
      );
      g.userData.speed = 0.3 + Math.random() * 0.4;
      g.visible = false;
      scene.add(g);
      clouds.push(g);
    }
  }

  function createParticles(count) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 40;
      pos[i * 3 + 1] = Math.random() * 20;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 30;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({
      color: 0xc9a84c,
      size: 0.15,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
    });
    particles = new THREE.Points(geo, mat);
    scene.add(particles);
  }

  function setMode(m) {
    mode = m;
    document.body.classList.toggle("night", m === "night");

    if (m === "night") {
      targetBg = { r: 0.02, g: 0.02, b: 0.08 };
      if (moon) moon.visible = true;
      if (sun) sun.visible = false;
      clouds.forEach((c) => (c.visible = false));
      if (stars) stars.material.opacity = 0.9;
      if (scene.fog) scene.fog.color.setRGB(0.02, 0.02, 0.08);
    } else if (m === "day") {
      targetBg = { r: 0.15, g: 0.22, b: 0.35 };
      if (moon) moon.visible = false;
      if (sun) {
        sun.visible = true;
        sun.position.set(10, 12, -45);
      }
      clouds.forEach((c) => (c.visible = true));
      if (stars) stars.material.opacity = 0.05;
      if (scene.fog) scene.fog.color.setRGB(0.15, 0.22, 0.35);
    } else if (m === "end") {
      targetBg = { r: 0.08, g: 0.04, b: 0.02 };
      if (stars) stars.material.opacity = 0.5;
    } else {
      targetBg = { r: 0.04, g: 0.03, b: 0.05 };
      if (moon) {
        moon.visible = true;
        moon.position.set(-8, 10, -35);
      }
      if (sun) sun.visible = false;
      clouds.forEach((c) => (c.visible = false));
      if (stars) stars.material.opacity = 0.7;
    }
  }

  function shake(intensity = 0.4) {
    camShake = intensity;
  }

  function setQuality(q) {
    quality = q;
    localStorage.setItem("mafi_gfx", q);
    // ری‌استارت سبک
    if (stars) {
      scene.remove(stars);
      stars.geometry.dispose();
      stars.material.dispose();
    }
    if (particles) {
      scene.remove(particles);
      particles.geometry.dispose();
      particles.material.dispose();
    }
    const cfg = QUALITY[q] || QUALITY.medium;
    reduced = q === "low";
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, cfg.pixelRatio));
    createStars(cfg.stars);
    createParticles(cfg.particles);
  }

  function onResize() {
    if (!camera || !renderer) return;
    const vv = window.visualViewport;
    const w = Math.round(vv?.width || window.innerWidth);
    const h = Math.round(vv?.height || window.innerHeight);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    document.documentElement.style.setProperty("--app-height", h + "px");
  }

  function bindViewport() {
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", () => setTimeout(onResize, 120));
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", onResize);
    }
    onResize();
  }

  function animate() {
    animId = requestAnimationFrame(animate);
    if (!renderer || !scene) return;
    const t = clock.getElapsedTime();
    const dt = clock.getDelta();

    currentBg.r += (targetBg.r - currentBg.r) * 0.02;
    currentBg.g += (targetBg.g - currentBg.g) * 0.02;
    currentBg.b += (targetBg.b - currentBg.b) * 0.02;
    renderer.setClearColor(
      new THREE.Color(currentBg.r, currentBg.g, currentBg.b),
      1
    );

    if (stars) {
      stars.rotation.y = t * 0.01;
      stars.rotation.x = Math.sin(t * 0.05) * 0.02;
    }

    if (moon && moon.visible) {
      moon.position.x = -12 + Math.sin(t * 0.1) * 1.5;
      moon.position.y = 14 + Math.cos(t * 0.08) * 0.8;
    }

    if (sun && sun.visible) {
      sun.position.y = 12 + Math.sin(t * 0.15) * 0.5;
    }

    clouds.forEach((c) => {
      if (!c.visible) return;
      c.position.x += c.userData.speed * dt;
      if (c.position.x > 25) c.position.x = -25;
    });

    if (particles) {
      particles.rotation.y = t * 0.05;
      const pos = particles.geometry.attributes.position.array;
      for (let i = 1; i < pos.length; i += 3) {
        pos[i] += 0.01;
        if (pos[i] > 20) pos[i] = 0;
      }
      particles.geometry.attributes.position.needsUpdate = true;
      if (mode === "night") {
        particles.material.color.setHex(0x8899cc);
        particles.material.opacity = 0.25;
      } else if (mode === "day") {
        particles.material.color.setHex(0xffe8a0);
        particles.material.opacity = 0.15;
      } else {
        particles.material.color.setHex(0xc9a84c);
        particles.material.opacity = 0.3;
      }
    }

    // پارالاکس دوربین
    const baseY = 2 + Math.sin(t * 0.3) * 0.3;
    const baseX = Math.sin(t * 0.2) * 0.5;
    let sx = 0,
      sy = 0;
    if (camShake > 0.01) {
      sx = (Math.random() - 0.5) * camShake;
      sy = (Math.random() - 0.5) * camShake;
      camShake *= 0.9;
    }
    camera.position.x = baseX + sx;
    camera.position.y = baseY + sy;
    camera.lookAt(0, 2, 0);

    renderer.render(scene, camera);
  }

  function destroy() {
    if (animId) cancelAnimationFrame(animId);
  }

  return { init, setMode, shake, setQuality, getQuality: () => quality, destroy };
})();

window.Scene3D = Scene3D;
