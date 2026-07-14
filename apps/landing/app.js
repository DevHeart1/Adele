const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function bootThreeBackground() {
  const canvas = document.getElementById("neural-canvas");
  if (!canvas || !window.THREE || prefersReduced) return;

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000);
  camera.position.z = 92;

  const group = new THREE.Group();
  scene.add(group);

  const count = 760;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 180;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 105;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 110;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({
    color: 0xa6ff00,
    size: 0.34,
    transparent: true,
    opacity: 0.55,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  group.add(new THREE.Points(geometry, material));

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener("resize", resize);

  let mouseX = 0;
  let mouseY = 0;
  window.addEventListener("pointermove", (event) => {
    mouseX = (event.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (event.clientY / window.innerHeight - 0.5) * 2;
  });

  function animate(time) {
    group.rotation.y = time * 0.000035 + mouseX * 0.04;
    group.rotation.x = mouseY * 0.035;
    material.opacity = 0.36 + Math.sin(time * 0.001) * 0.08;
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
}

function bootGsap() {
  if (!window.gsap || prefersReduced) return;
  gsap.registerPlugin(ScrollTrigger);

  gsap.from(".site-header", { y: -80, opacity: 0, duration: 0.9, ease: "power3.out" });
  gsap.from(".hero-copy > *", {
    y: 34,
    opacity: 0,
    duration: 0.9,
    stagger: 0.08,
    ease: "power3.out",
  });
  gsap.from(".hero-product", {
    x: 90,
    y: 40,
    rotation: -7,
    opacity: 0,
    duration: 1.25,
    ease: "power3.out",
    delay: 0.2,
  });
  gsap.to(".hero-product", {
    y: -30,
    rotation: 2,
    scrollTrigger: {
      trigger: ".hero",
      start: "top top",
      end: "bottom top",
      scrub: 0.7,
    },
  });
  gsap.to(".hero-bg", {
    scale: 1.1,
    y: 90,
    scrollTrigger: {
      trigger: ".hero",
      start: "top top",
      end: "bottom top",
      scrub: true,
    },
  });

  gsap.utils.toArray(".section-head").forEach((head) => {
    gsap.from(head.children, {
      y: 36,
      opacity: 0,
      duration: 0.75,
      stagger: 0.07,
      ease: "power2.out",
      scrollTrigger: { trigger: head, start: "top 78%" },
    });
  });

  gsap.utils.toArray(".feature-card, .use-grid article, .pricing-grid article").forEach((card, index) => {
    gsap.from(card, {
      y: 48,
      opacity: 0,
      rotateX: 7,
      duration: 0.75,
      delay: (index % 4) * 0.035,
      ease: "power2.out",
      scrollTrigger: { trigger: card, start: "top 86%" },
    });

    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      gsap.to(card, { rotateY: x * 5, rotateX: -y * 5, duration: 0.28, ease: "power2.out" });
    });
    card.addEventListener("pointerleave", () => {
      gsap.to(card, { rotateY: 0, rotateX: 0, duration: 0.45, ease: "power2.out" });
    });
  });

  gsap.to(".side-intel img", {
    y: -16,
    rotation: 8,
    duration: 2.4,
    repeat: -1,
    yoyo: true,
    ease: "sine.inOut",
  });

  ScrollTrigger.create({
    trigger: ".features",
    start: "top bottom",
    end: "bottom top",
    scrub: true,
    onUpdate: (self) => {
      document.documentElement.style.setProperty("--scroll-glow", self.progress.toFixed(3));
    },
  });
}

function wireDownloads() {
  document.querySelectorAll('a[download]').forEach((link) => {
    link.addEventListener("click", () => {
      link.classList.add("is-downloading");
      window.setTimeout(() => link.classList.remove("is-downloading"), 1400);
    });
  });
}

bootThreeBackground();
bootGsap();
wireDownloads();
