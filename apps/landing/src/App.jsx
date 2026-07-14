import { useEffect, useMemo, useState } from "react";
const mark = "/assets/adele-mark.png";
const windowsDownload = "/downloads/ADELE-Setup-1.0.0.exe";

function Header() {
  return (
    <header className="site-header">
      <a className="brand" href="#top" aria-label="ADELE home">
        <img src={mark} alt="" />
        <span>ADELE</span>
      </a>
      <nav aria-label="Primary navigation">
        <a href="#features">Features</a>
        <a href="#use-cases">Use Cases</a>
        <a href="#pricing">Pricing</a>
      </nav>
      <a className="nav-download" href={windowsDownload} download>
        <span className="download-icon" aria-hidden="true" />
        Download
      </a>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero section-frame">
      <div className="hero-bg" aria-hidden="true" />
      <div className="hero-copy">
        <p className="green-line">The AI desktop agent that actually does stuff</p>
        <h1>
          <span>Stop clicking.</span>
          <span>Start</span>
          <span className="lime slash">commanding.</span>
        </h1>
        <p className="hero-lede">
          ADELE is the real-time desktop copilot for people who are done babysitting tabs, forms, and repetitive work.
          It <strong> sees, thinks, and gets things moving.</strong>
        </p>
        <div className="signal-pill">
          <img src={mark} alt="" />
          <span>Your computer finally locked in.</span>
        </div>
        <div className="download-row" aria-label="Download options">
          <a className="download-primary" href={windowsDownload} download data-download-windows>
            <span className="windows-logo" aria-hidden="true" />
            Download for Windows
          </a>
          <button className="download-secondary" type="button" disabled>
            <span className="apple-logo" aria-hidden="true" />
            Download for Mac
            <small>Coming Soon</small>
          </button>
        </div>
        <p className="download-note">For Windows users who are tired of doing everything the hard way.</p>
        <div className="hero-badges">
          <span><b>Voice + Vision</b><small>Speak it. See it. Ship it.</small></span>
          <span><b>Automates</b><small>Desktop workflows</small></span>
          <span><b>BYO API key</b><small>You stay in control</small></span>
        </div>
      </div>

      <div className="hero-visual" data-parallax>
        <img className="hero-product" src="/assets/hero-product.png" alt="ADELE onboarding and voice setup interface" />
        <div className="side-intel">
          <img src={mark} alt="" />
          <ul>
            <li>Real-time intelligence</li>
            <li>Sees your screen</li>
            <li>Executes with precision</li>
          </ul>
          <pre>{"> ADELE online\n> Analyzing screen...\n> Planning actions...\n> Executing...\n> Done"}</pre>
          <p>Chaos, automated.</p>
        </div>
      </div>
    </section>
  );
}

function Features() {
  const features = [
    ["waveform", "Voice-first", "Say \"Hey ADELE\" or press Ctrl+Shift+Space on Windows or Cmd+Shift+Space on Mac, speak naturally, watch it act.", "/assets/feature-voice.png", "Talk. Command. Done."],
    ["terminal", "SPAV agent", "Sense, Plan, Act, Verify loop with milestone-based execution.", "/assets/feature-loop.png", "Thinks. Acts. Verifies. Repeats."],
    ["gridmark", "Multi-modal responses", "Cards, tables, rich text, timelines, image viewer, and progress states.", null, "Information, beautifully delivered."],
    ["globe", "Browser automation", "Chrome extension bridges web actions: search, fill forms, click, read, and extract.", "/assets/feature-browser.png", "The web is your playground.", "wide"],
    ["lock", "Local-first", "Python backend and data stay on your machine under ADELE_DATA_DIR. Configure providers as needed.", "/assets/feature-local.png", "Your data. Your machine. Your rules.", "wide"]
  ];

  return (
    <section className="features" id="features">
      <div className="section-head">
        <p className="section-tag"><img src={mark} alt="" /> Features</p>
        <h2>ADELE isn't an app. She's your <span>operating layer.</span></h2>
        <p>Built different. Works different. <strong>Gets sh*t done.</strong></p>
      </div>
      <div className="feature-grid">
        {features.map(([icon, title, text, image, tag, wide]) => (
          <article className={`feature-card ${wide || ""}`} key={title}>
            <div className={`card-icon ${icon}`} />
            <h3>{title}</h3>
            <p>{text}</p>
            {image ? <img src={image} alt={`${title} preview`} /> : <div className="mini-dashboard" aria-hidden="true"><span /><span /><span /><div /></div>}
            <span>{tag}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function UseCases() {
  const cases = [
    ["Research anything", "Deep web research, summarize articles, compare sources, extract the good stuff.", "/assets/use-research.png", "Know more. Faster."],
    ["Fill forms & apply", "Auto-detect fields, fill forms, upload docs, and submit. No copy-paste hell.", "/assets/use-forms.png", "Apply smart. Land more."],
    ["Extract & organize data", "Pull data from web pages, PDFs, images, and organize it how you need.", "/assets/use-data.png", "Turn chaos into structure."],
    ["Emails & outreach", "Draft, personalize, and send emails that sound like you on your behalf.", "/assets/use-email.png", "Your wingman for outreach."],
    ["Schedule & remind", "Book meetings, set reminders, track timelines. ADELE keeps your day on rails.", "/assets/use-schedule.png", "Never miss. Never stress."],
    ["File & system ops", "Rename, move, organize, search across files and folders. Your locker, sorted.", "/assets/use-files.png", "Clean files. Clear mind."],
    ["Dev & automation", "Run scripts, automate workflows, test, deploy. ADELE speaks developer fluently.", "/assets/use-dev.png", "Code less. Automate more."],
    ["Learn & upskill", "Explain anything, create study plans, quizzes, and learning notes.", "/assets/use-learn.png", "Your 24/7 genius tutor."]
  ];

  return (
    <section className="use-cases" id="use-cases">
      <div className="section-head">
        <p className="section-tag"><img src={mark} alt="" /> Use Cases</p>
        <h2>One agent. Endless moves. <span>You dream it. ADELE runs it.</span></h2>
        <p>Here's what ADELE can handle while <strong>you</strong> focus on what matters.</p>
      </div>
      <div className="use-grid">
        {cases.map(([title, text, image, tag]) => (
          <article key={title}>
            <h3>{title}</h3>
            <p>{text}</p>
            <img src={image} alt={`${title} preview`} />
            <span>{tag}</span>
          </article>
        ))}
      </div>
      <p className="use-footer"><img src={mark} alt="" /> From boring tasks to big goals, ADELE handles it so you can live it.</p>
    </section>
  );
}

function Pricing() {
  return (
    <section className="pricing" id="pricing">
      <div className="section-head">
        <p className="section-tag"><img src={mark} alt="" /> Pricing</p>
        <h2>Zero subs. Zero nonsense. <span>Just bring your API.</span></h2>
      </div>
      <div className="pricing-stage">
        <div className="pricing-copy">
          <p>ADELE is completely free to use. You plug in your own API keys for LLM and TTS providers, so you only pay your providers directly if you decide to use them.</p>
          <div className="pricing-actions">
            <a className="download-primary" href={windowsDownload} download><span className="windows-logo" aria-hidden="true" />Download for Windows</a>
            <a className="docs-button" href="https://github.com/mylife-as-miles/adele" target="_blank" rel="noreferrer"><span className="docs-icon" aria-hidden="true" />Read setup docs</a>
          </div>
          <p className="pricing-note">No lock-in. No platform tax. Your machine, your keys, <strong>your rules.</strong></p>
        </div>
        <article className="price-console">
          <div className="price-main">
            <h3>Free Forever</h3>
            <p className="price">$0 <small>/month</small></p>
            <p className="byo">BYO API</p>
            <span>Seriously. $0.</span>
          </div>
          <ul>
            <li>ADELE app access - free</li>
            <li>Bring your own LLM API keys</li>
            <li>Bring your own TTS provider keys</li>
            <li>Local-first setup</li>
            <li>Pay providers directly only when you use them</li>
          </ul>
          <div className="nonsense-stamp" aria-hidden="true">No<br />subscription<br />nonsense</div>
        </article>
      </div>
    </section>
  );
}

function Footer({ onLegal }) {
  return (
    <footer className="site-footer">
      <div className="footer-brand">
        <div className="footer-brand-head"><img src={mark} alt="" /><strong>ADELE</strong></div>
        <p>Control Intelligence Assistant for <span>Real-time Automation</span></p>
        <p>Voice-first desktop agent for people who want their computer to actually do the work.</p>
        <div className="social-row" aria-label="Social links">
          <a href="mailto:hello@adele.local" aria-label="Email ADELE" />
          <a href="https://github.com/mylife-as-miles/adele" target="_blank" rel="noreferrer" aria-label="GitHub" />
          <a href="#features" aria-label="Documentation" />
          <a href="#top" aria-label="Back to top" />
        </div>
      </div>
      <nav className="footer-nav" aria-label="Footer navigation">
        <div><h3>Product</h3><a href="#features">Features</a><a href="#use-cases">Use Cases</a><a href="#pricing">Pricing</a><a href="#pricing">Roadmap</a></div>
        <div><h3>Download</h3><a href={windowsDownload} download>Windows</a><span>Mac (Coming Soon)</span><a href="#features">Setup Docs</a><a href="#top">Changelog</a></div>
        <div><h3>Resources</h3><a href="https://github.com/mylife-as-miles/adele" target="_blank" rel="noreferrer">GitHub</a><a href="#features">Documentation</a><a href="#pricing">API Setup</a><a href="mailto:hello@adele.local">Community</a></div>
        <div><h3>Legal</h3><button type="button" onClick={() => onLegal("privacy")}>Privacy</button><button type="button" onClick={() => onLegal("terms")}>Terms</button><a href="#top">License</a></div>
      </nav>
      <img className="footer-core" src="/assets/footer-core.png" alt="ADELE local automation core" />
      <div className="footer-bottom"><span>© 2026 ADELE</span><span>Built for people <strong>tired of clicking.</strong></span></div>
    </footer>
  );
}

function Legal({ type, onBack }) {
  const isPrivacy = type === "privacy";
  return (
    <main className="legal-shell">
      <a className="brand" href="#top" onClick={onBack}><img src={mark} alt="" /><span>ADELE</span></a>
      <h1>{isPrivacy ? "Privacy" : "Terms"}</h1>
      <p>{isPrivacy ? "ADELE is designed as a local-first desktop assistant. App data and provider keys stay on your machine unless you choose to connect external API providers." : "ADELE is provided as a desktop automation tool. You are responsible for the API keys, providers, data, and actions you configure it to use."}</p>
      <p>{isPrivacy ? "When you use third-party LLM or voice services, your requests are handled by the providers you configure. Review each provider's policy before adding keys." : "Use ADELE only on systems and accounts you are authorized to control. Provider charges, limits, and availability are governed by the providers you connect."}</p>
      <button className="download-primary" type="button" onClick={onBack}>Back to ADELE</button>
    </main>
  );
}

function useLandingMotion(enabled) {
  useEffect(() => {
    if (!enabled) return undefined;
    let mounted = true;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const canvas = document.getElementById("neural-canvas");
    let renderer;
    let frame = 0;
    let cleanup = () => {};

    async function boot() {
      if (prefersReduced || !mounted) return;
      const [THREE, { gsap }, { ScrollTrigger }] = await Promise.all([
        import("three"),
        import("gsap"),
        import("gsap/ScrollTrigger")
      ]);
      if (!mounted) return;
      gsap.registerPlugin(ScrollTrigger);

      if (canvas) {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000);
      camera.position.z = 92;
      const group = new THREE.Group();
      scene.add(group);
      const count = 760;
      const positions = new Float32Array(count * 3);
      for (let i = 0; i < count; i += 1) {
        positions[i * 3] = (Math.random() - 0.5) * 180;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 105;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 110;
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      const material = new THREE.PointsMaterial({ color: 0xa6ff00, size: 0.34, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false });
      group.add(new THREE.Points(geometry, material));
      let mouseX = 0;
      let mouseY = 0;
      const resize = () => {
        const w = window.innerWidth;
        const h = window.innerHeight;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      };
      const move = (event) => {
        mouseX = (event.clientX / window.innerWidth - 0.5) * 2;
        mouseY = (event.clientY / window.innerHeight - 0.5) * 2;
      };
      const animate = (time) => {
        group.rotation.y = time * 0.000035 + mouseX * 0.04;
        group.rotation.x = mouseY * 0.035;
        material.opacity = 0.36 + Math.sin(time * 0.001) * 0.08;
        renderer.render(scene, camera);
        frame = requestAnimationFrame(animate);
      };
      resize();
      window.addEventListener("resize", resize);
      window.addEventListener("pointermove", move);
      frame = requestAnimationFrame(animate);
      cleanup = () => {
        cancelAnimationFrame(frame);
        window.removeEventListener("resize", resize);
        window.removeEventListener("pointermove", move);
        geometry.dispose();
        material.dispose();
        renderer.dispose();
      };
      }

      const ctx = gsap.context(() => {
        gsap.from(".site-header", { y: -80, opacity: 0, duration: 0.9, ease: "power3.out" });
        gsap.from(".hero-copy > *", { y: 34, opacity: 0, duration: 0.9, stagger: 0.08, ease: "power3.out" });
        gsap.from(".hero-product", { x: 90, y: 40, rotation: -7, opacity: 0, duration: 1.25, ease: "power3.out", delay: 0.2 });
        gsap.to(".hero-product", { y: -30, rotation: 2, scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: 0.7 } });
        gsap.to(".hero-bg", { scale: 1.1, y: 90, scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });
        gsap.utils.toArray(".section-head").forEach((head) => gsap.from(head.children, { y: 36, opacity: 0, duration: 0.75, stagger: 0.07, ease: "power2.out", scrollTrigger: { trigger: head, start: "top 78%" } }));
        gsap.utils.toArray(".feature-card, .use-grid article, .price-console").forEach((card, index) => {
          gsap.from(card, { y: 48, opacity: 0, rotateX: 7, duration: 0.75, delay: (index % 4) * 0.035, ease: "power2.out", scrollTrigger: { trigger: card, start: "top 86%" } });
          card.addEventListener("pointermove", (event) => {
            const rect = card.getBoundingClientRect();
            const x = (event.clientX - rect.left) / rect.width - 0.5;
            const y = (event.clientY - rect.top) / rect.height - 0.5;
            gsap.to(card, { rotateY: x * 5, rotateX: -y * 5, duration: 0.28, ease: "power2.out" });
          });
          card.addEventListener("pointerleave", () => gsap.to(card, { rotateY: 0, rotateX: 0, duration: 0.45, ease: "power2.out" }));
        });
        gsap.to(".side-intel img", { y: -16, rotation: 8, duration: 2.4, repeat: -1, yoyo: true, ease: "sine.inOut" });
      });
      return () => {
        ctx.revert();
        ScrollTrigger.getAll().forEach((trigger) => trigger.kill());
        cleanup();
      };
    }
    const booted = boot();
    return () => {
      mounted = false;
      Promise.resolve(booted).then((motionCleanup) => {
        if (typeof motionCleanup === "function") motionCleanup();
      });
      cleanup();
    };
  }, [enabled]);
}

export default function App() {
  const [legal, setLegal] = useState("");
  const isLegal = Boolean(legal);
  useLandingMotion(!isLegal);

  const page = useMemo(() => {
    if (isLegal) return <Legal type={legal} onBack={() => setLegal("")} />;
    return (
      <>
        <Header />
        <main id="top">
          <Hero />
          <Features />
          <UseCases />
          <Pricing />
          <Footer onLegal={setLegal} />
        </main>
      </>
    );
  }, [isLegal, legal]);

  return (
    <>
      <canvas id="neural-canvas" aria-hidden="true" />
      <div className="scanline" aria-hidden="true" />
      {page}
    </>
  );
}
