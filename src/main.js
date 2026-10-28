// ── Light/dark toggle ────────────────────────────────────────
// Defaults to the OS preference; an explicit choice is stored in
// localStorage and set as data-theme on <html> (see main.css).
(function () {
  const KEY = 'haileyjay-theme';
  const root = document.documentElement;

  function systemDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function effective() {
    const s = root.getAttribute('data-theme');
    return s ? s : (systemDark() ? 'dark' : 'light');
  }

  const changeListeners = [];
  window.haileyjayTheme = {
    effective: effective,
    onChange: function (cb) { changeListeners.push(cb); }
  };

  function notifyChange() {
    syncThemeColor();
    changeListeners.forEach(function (cb) { cb(effective()); });
  }

  // Both theme-color tags (one per OS scheme) take the current paper, so a
  // hand-picked theme wins over the OS's.
  function syncThemeColor() {
    const paper = getComputedStyle(root).getPropertyValue('--paper').trim();
    document.querySelectorAll('meta[name="theme-color"]').forEach(function (m) {
      m.setAttribute('content', paper);
    });
  }

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (!root.getAttribute('data-theme')) { updateBtn(); notifyChange(); }
    });
  }

  function updateBtn() {
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    const dark = effective() === 'dark';
    const knob = btn.querySelector('.knob');
    if (knob) knob.textContent = dark ? '☀' : '☾';
    btn.classList.toggle('is-dark', dark);
    btn.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  }

  document.addEventListener('DOMContentLoaded', function () {
    updateBtn();
    syncThemeColor();
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      const next = effective() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      updateBtn();
      notifyChange();
    });
  });
})();

// ── Mobile sidebar drawer ────────────────────────────────────
(function () {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  const btn = document.getElementById('mobile-menu-btn');
  if (!sidebar || !backdrop || !btn) return;

  function openSidebar() {
    sidebar.classList.add('mobile-open');
    backdrop.classList.add('active');
    btn.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar.classList.remove('mobile-open');
    backdrop.classList.remove('active');
    btn.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  btn.addEventListener('click', function () {
    sidebar.classList.contains('mobile-open') ? closeSidebar() : openSidebar();
  });

  backdrop.addEventListener('click', closeSidebar);

  sidebar.addEventListener('click', function (e) {
    if (e.target.closest('a')) closeSidebar();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !sidebar.classList.contains('mobile-open')) return;
    closeSidebar();
    btn.focus();
  });
})();

// ── Section registry ─────────────────────────────────────────
// Filtered against the DOM so unpublished sections drop out cleanly.
const sections = ['about', 'cv', 'papers', 'teaching', 'comics', 'blog', 'colophon']
  .filter(function (s) { return document.getElementById(s); });

const subAnchors = {
  '1431': 'teaching',
  '1431f25': 'teaching'
};

// ── Navigation ───────────────────────────────────────────────
// Fires `accentchange` on document when the accent colour changes; see navigate.
let currentSection = null;
let accentKey = null;

function showSection(id) {
  let parentId = subAnchors[id] || id;
  if (!sections.includes(parentId)) parentId = 'about';
  currentSection = parentId;
  sections.forEach(function (s) {
    document.getElementById(s).classList.toggle('active', s === parentId);
  });
  // Mark the current section in the main nav (see .mainnav in main.css).
  document.querySelectorAll('.mainnav a').forEach(function (a) {
    if (a.getAttribute('href') === '#' + parentId) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

function navigate(hash, push) {
  var bare = !hash;
  if (!hash) hash = 'about';
  // A hash this router does not own (#main-content, say) reached us
  // via history, not a click. Leave the active section as it is.
  if (!bare && !sections.includes(hash) && !subAnchors[hash]) return;
  showSection(hash);
  if (!bare) {
    if (push && location.hash.slice(1) !== hash) {
      history.pushState(null, '', '#' + hash);
    } else {
      history.replaceState(null, '', '#' + hash);
    }
  }

  // A post's own colour (--post, set inline by the build) tints the whole
  // Blog section while it is open; see #blog in main.css.
  const post = subAnchors[hash] === 'blog' && document.getElementById(hash);
  const postColour = post ? post.style.getPropertyValue('--post') : '';
  if (postColour) document.documentElement.style.setProperty('--post', postColour);
  else document.documentElement.style.removeProperty('--post');

  // Fires `accentchange` when the page's accent colour changes: a new section,
  // or a post with a colour of its own. `first` marks the initial navigation.
  const key = currentSection + postColour;
  if (key !== accentKey) {
    const first = accentKey === null;
    accentKey = key;
    document.dispatchEvent(new CustomEvent('accentchange', { detail: { first: first } }));
  }

  if (subAnchors[hash] === 'blog') {
    document.getElementById('blog-index').style.display = 'none';
    document.querySelectorAll('.blog-post').forEach(function (el) {
      el.style.display = el.id === hash ? '' : 'none';
    });
    window.scrollTo({ top: 0 });
  } else if (hash === 'blog') {
    document.getElementById('blog-index').style.display = '';
    document.querySelectorAll('.blog-post').forEach(function (el) {
      el.style.display = 'none';
    });
    window.scrollTo({ top: 0 });
  } else if (subAnchors[hash]) {
    const target = document.getElementById(hash);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    window.scrollTo({ top: 0 });
  }
}

document.addEventListener('click', function (e) {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const url = new URL(a.href, location.href);
  if (url.pathname !== location.pathname) return;
  const hash = url.hash.slice(1);
  if (!hash) return;
  // Only claim anchors this router actually owns. Anything else --
  // the skip link's #main-content above all -- must keep its native
  // behaviour, or it silently falls through to the About section
  // (see showSection) and never moves focus.
  if (!sections.includes(hash) && !subAnchors[hash]) return;
  e.preventDefault();
  navigate(hash, true);
});

window.addEventListener('popstate', function () {
  navigate(location.hash.slice(1));
});

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-blog-entry]').forEach(function (el) {
    subAnchors[el.id] = 'blog';
  });
  // Initialise blog visibility before first navigate
  var blogIndex = document.getElementById('blog-index');
  if (blogIndex) blogIndex.style.display = '';
  document.querySelectorAll('.blog-post').forEach(function (el) {
    el.style.display = 'none';
  });
  navigate(location.hash.slice(1));
});

// ── Lightbox ─────────────────────────────────────────────────
// One factory serving every thumbnail gallery. Items are collected
// on open, so galleries added or re-rendered later still work.
function makeLightbox(opts) {
  const overlay = document.createElement('div');
  overlay.className = 'lb-overlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', opts.label);
  overlay.innerHTML = `
    <div class="lb-dialog" tabindex="-1">
      <span class="lb-counter" aria-live="polite"></span>
      <button class="lb-close" aria-label="Close">&times;</button>
      <div class="lb-img-wrap">
        <button class="lb-prev" aria-label="${opts.prevLabel}">&#8592;</button>
        <img src="" alt="">
        <button class="lb-next" aria-label="${opts.nextLabel}">&#8594;</button>
      </div>
      <p class="lb-caption"></p>
    </div>`;
  document.body.appendChild(overlay);

  const dialog = overlay.querySelector('.lb-dialog');
  const img = overlay.querySelector('img');
  const caption = overlay.querySelector('.lb-caption');
  const counter = overlay.querySelector('.lb-counter');
  const btnClose = overlay.querySelector('.lb-close');
  const btnPrev = overlay.querySelector('.lb-prev');
  const btnNext = overlay.querySelector('.lb-next');

  let items = [];
  let current = 0;

  function collectItems(fromEl) {
    // Scoped to the containing post so a post's grid and its inline
    // [image ...] figures share one prev/next sequence, while other
    // posts/sections stay out of it. Comics have no post wrapper and
    // fall back to their grid.
    const scope = (fromEl && (fromEl.closest('.blog-post') || fromEl.closest('.gallery-grid'))) || document;
    items = Array.from(scope.querySelectorAll(opts.selector));
  }

  function show(index) {
    const btn = items[index];
    img.src = btn.dataset.src;
    img.alt = btn.dataset.alt;
    caption.textContent = btn.dataset.caption;
    counter.textContent = (index + 1) + ' / ' + items.length;
    btnPrev.style.visibility = index === 0 ? 'hidden' : '';
    btnNext.style.visibility = index === items.length - 1 ? 'hidden' : '';
    current = index;
  }

  function open(index) {
    show(index);
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
    dialog.focus();
  }

  function close() {
    overlay.classList.remove('open');
    document.body.style.overflow = '';
    if (items[current]) items[current].focus();
  }

  document.addEventListener('click', function (e) {
    const thumb = e.target.closest(opts.selector);
    if (!thumb) return;
    collectItems(thumb);
    open(items.indexOf(thumb));
  });

  btnClose.addEventListener('click', close);
  btnPrev.addEventListener('click', function () { if (current > 0) show(current - 1); });
  btnNext.addEventListener('click', function () { if (current < items.length - 1) show(current + 1); });

  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) close();
  });

  overlay.addEventListener('keydown', function (e) {
    if (!overlay.classList.contains('open')) return;
    if (e.key === 'Escape') { close(); return; }
    if (e.key === 'ArrowLeft' && current > 0) { show(current - 1); return; }
    if (e.key === 'ArrowRight' && current < items.length - 1) { show(current + 1); return; }
    if (e.key === 'Tab') {
      const focusable = Array.from(dialog.querySelectorAll('button:not([style*="visibility: hidden"])'));
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
}

makeLightbox({
  selector: '.comic-thumb',
  label: 'Comic viewer',
  prevLabel: 'Previous comic',
  nextLabel: 'Next comic'
});

makeLightbox({
  selector: '.gallery-thumb',
  label: 'Gallery viewer',
  prevLabel: 'Previous image',
  nextLabel: 'Next image'
});


const aboutQuotes = [
  "Try the chocolate chip cookies!", "No mitsakes -- but undo is C-/ just in case.", "Caution: Hearing protection required!", "THE SNAIL!", "How... old is that onion?", "Aaaand that's a nat 1. Sorry.", "The lesser of two weevils!", "Daemonic!", "You have to have some body positivity when you're making graphs.", "Sparkle? You're the whole tub of glitter, baby!", "Bing bong? I don't know.", "Copyleft womanhood!", "Save the pandas!", "Renee Descartes, my mortal enemy!", "Heat from fire, fire from heat!", "Shut up and let me see your jazz hands!", "Coins, evil.", "LOUD INCORRECT BUZZER.", "I'm out of spell slots.", "Jet fuel ice tea, supersonic, lightspeed!!", "Take that kerosene and put it in my coffee!", "Gear up and blast off!", "Hyneri lanla!", "The Lockett monster of Bore Pit B!", "Succumbing to the bone broth madness...", "Lay back and dive!"
];

document.addEventListener('DOMContentLoaded', function () {
  const el = document.getElementById('about-splash');
  if (el) el.textContent = aboutQuotes[Math.floor(Math.random() * aboutQuotes.length)];
});

// ── Wireframe animation (footer) ────────────────────────────
// Shape list mirrors SHAPES in scripts/gen_wireframes.py.
const wireframeShapes = [
  'tetrahedron', 'cube', 'octahedron', 'dodecahedron', 'icosahedron',
  'sphere', 'torus', 'mobius', 'klein_bottle'
];

document.addEventListener('DOMContentLoaded', function () {
  const video = document.getElementById('wireframe-video');
  if (!video) return;
  // The video autoplays and loops with no pause control, so under
  // reduced-motion it is left unloaded entirely (WCAG 2.2.2). This
  // also saves the visitor up to 1.2 MB.
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    video.remove();
    return;
  }
  // The footer rose stands in until now; the video takes its place.
  const rose = video.parentNode.querySelector('img');
  if (rose) rose.remove();
  video.hidden = false;
  const pick = wireframeShapes[Math.floor(Math.random() * wireframeShapes.length)];

  function setVariant(theme) {
    const suffix = theme === 'dark' ? '-dark' : '';
    const time = video.currentTime;
    video.src = 'images/wireframes/' + pick + suffix + '.mp4';
    video.currentTime = time;
  }

  setVariant(window.haileyjayTheme ? window.haileyjayTheme.effective() : 'light');
  if (window.haileyjayTheme) window.haileyjayTheme.onChange(setVariant);
});

// ── Blog image carousel (about page) ────────────────────────
// Image list is baked in at build time; the shuffle and pick
// happen client-side so the selection varies per visit.
document.addEventListener('DOMContentLoaded', function () {
  const dataEl = document.getElementById('blog-carousel-data');
  const container = document.getElementById('blog-carousel');
  if (!dataEl || !container) return;

  const images = JSON.parse(dataEl.textContent);
  for (let i = images.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [images[i], images[j]] = [images[j], images[i]];
  }

  const picks = images.slice(0, 10);
  // Render the picks twice back-to-back so the auto-scroll can wrap
  // from the end of the first copy to the start of the second one
  // without a visible jump.
  const frag = document.createDocumentFragment();
  picks.concat(picks).forEach(function (entry) {
    const a = document.createElement('a');
    a.className = 'blog-carousel-item';
    a.href = '#blog-' + entry.slug;
    if (entry.colour) a.style.setProperty('--post', entry.colour);

    const img = document.createElement('img');
    img.src = entry.thumb;
    img.alt = entry.alt;
    // Only two or three items are on screen at a time, and the second
    // copy is entirely off screen until the scroll wraps.
    img.loading = 'lazy';
    img.decoding = 'async';
    img.width = 220;
    img.height = 150;
    a.appendChild(img);

    const caption = document.createElement('span');
    caption.className = 'blog-carousel-caption';
    caption.textContent = entry.title;
    a.appendChild(caption);

    frag.appendChild(a);
  });
  container.appendChild(frag);

  if (picks.length > 1 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    autoScroll(container);
  }
});

function autoScroll(container) {
  const speed = .35; // px per frame
  let paused = false;
  // scrollLeft rounds to an integer pixel on read, so accumulating
  // sub-pixel steps directly on it stalls at 0. Track the true
  // offset separately and only push the rounded value to the DOM.
  let offset = container.scrollLeft;

  container.addEventListener('mouseenter', function () { paused = true; });
  container.addEventListener('mouseleave', function () { paused = false; });
  container.addEventListener('touchstart', function () { paused = true; }, { passive: true });
  container.addEventListener('touchend', function () { paused = false; });
  container.addEventListener('focusin', function () { paused = true; });
  container.addEventListener('focusout', function () { paused = false; });

  function step() {
    if (!paused) {
      const half = container.scrollWidth / 2;
      offset += speed;
      if (offset >= half) offset -= half;
      container.scrollLeft = offset;
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ── Copy toggles (paper BibTeX, my button's code) ────────────
// The text is in the page already (a hidden <pre>; for papers, built by
// the CV repo). Opening it also copies it, since copying is why anyone
// clicks; the revealed text is the fallback when the clipboard is
// unavailable (http, or a browser that refuses).
document.querySelectorAll('.paper-bibtex, .code-toggle').forEach(function (btn) {
  const bib = document.getElementById(btn.getAttribute('aria-controls'));
  const status = btn.nextElementSibling;
  btn.addEventListener('click', function () {
    const open = btn.getAttribute('aria-expanded') !== 'true';
    btn.setAttribute('aria-expanded', String(open));
    bib.hidden = !open;
    status.textContent = '';
    if (!open || !navigator.clipboard) return;
    navigator.clipboard.writeText(bib.textContent).then(function () {
      status.textContent = 'copied';
    }, function () {});
  });
});

// ── Example carousel (Sagitta landing page) ─────────────────
// The track is a scroll-snapping row that works by swiping or scrolling
// alone; this unhides the tabs, points each at its slide, and marks the tab
// of whichever slide is in view, however it got there.
document.querySelectorAll('[data-carousel]').forEach(function (carousel) {
  const track = carousel.querySelector('.sg-carousel-track');
  const slides = Array.from(track.children);
  const tabs = Array.from(carousel.querySelectorAll('[data-slide]'));
  const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  carousel.querySelector('.sg-carousel-tabs').hidden = false;
  carousel.classList.add('is-enhanced');

  function mark(index) {
    tabs.forEach(function (tab, i) {
      tab.setAttribute('aria-pressed', String(i === index));
    });
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () {
      track.scrollTo({ left: slides[i].offsetLeft - track.offsetLeft,
                       behavior: smooth ? 'smooth' : 'auto' });
      mark(i);
    });
  });

  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) mark(slides.indexOf(entry.target));
    });
  }, { root: track, threshold: 0.6 });
  slides.forEach(function (slide) { observer.observe(slide); });
  mark(0);
});

// ── Backdrop arrangement ─────────────────────────────────────
// Random lines across the window behind the page; each region they cut out
// gets a tint, chosen by hashing which side of every line it is on, plus a
// little grain. The tints come from the page's accent, so they follow the
// section and a blog post's own colour. A new arrangement on every load and,
// fading in, on every change of accent (under reduced motion, only recoloured).
// Redrawn on a theme switch.
// Decoration only: no hover, no clicks.
(function () {
  const first = document.querySelector('canvas.backdrop');
  if (!first) return;
  const LINES = 10, GRAIN = 6;
  // Two stacked canvases: a new arrangement is drawn on the hidden one, which
  // is then moved on top and faded in over the old.
  const second = first.cloneNode();
  second.style.opacity = '0';
  first.after(second);
  let front = first, back = second;

  // Lines are a·x + b·y + c = 0 with (a, b) a unit normal. They pass through
  // random points of the whole screen rather than the window, so resizing the
  // window (or a phone's address bar sliding away) never moves them.
  let lines;
  function roll() {
    const sw = screen.width || 1920, sh = screen.height || 1080;
    lines = [];
    for (let i = 0; i < LINES; i++) {
      const x = Math.random() * sw, y = Math.random() * sh, t = Math.random() * Math.PI;
      const a = Math.sin(t), b = -Math.cos(t);
      lines.push([a, b, -(a * x + b * y)]);
    }
  }

  const rgb = function (s) {
    s = s.trim().replace('#', '');
    return [0, 2, 4].map(function (i) { return parseInt(s.substr(i, 2), 16); });
  };
  const mix = function (p, q, t) { return p.map(function (v, i) { return Math.round(v + (q[i] - v) * t); }); };
  const hex = function (c) { return '#' + c.map(function (v) { return v.toString(16).padStart(2, '0'); }).join(''); };

  // Tints are the paper mixed with the accent (--accent on <html>, which
  // main.css sets per section), the rule, and a little pink. The accents are
  // text colours, dark on light paper, so there they are mixed in more
  // lightly than on dark paper, where they are pale. The line is --arr-line
  // in main.css: muted, 55% of the way from the paper.
  let tints, line;
  function colours() {
    const cs = getComputedStyle(document.documentElement);
    const paper = rgb(cs.getPropertyValue('--paper'));
    const accent = rgb(cs.getPropertyValue('--accent'));
    const pink = rgb(cs.getPropertyValue('--pink'));
    const rule = rgb(cs.getPropertyValue('--rule'));
    const dark = paper[0] + paper[1] + paper[2] < 384;
    const k = dark ? [.12, .26, .42] : [.07, .15, .25];
    tints = [mix(paper, accent, k[0]), mix(paper, accent, k[1]), mix(paper, accent, k[2]),
             mix(paper, rule, .6), mix(paper, pink, .2), mix(paper, accent, k[1])];
    line = hex(mix(paper, rgb(cs.getPropertyValue('--muted')), .55));
  }

  // Region tint from its sign vector. The bits are mixed before the modulus;
  // a bare multiply-and-mod would only see the first few lines.
  const pick = function (k) {
    k = Math.imul(k ^ (k >>> 16), 0x45d9f3b);
    k = Math.imul(k ^ (k >>> 16), 0x45d9f3b);
    return ((k ^ (k >>> 16)) >>> 0) % tints.length;
  };

  // Regions are filled per CSS pixel, then scaled up to the device's pixels;
  // the lines are stroked at full resolution on top, covering the seams.
  // The grain and pixel buffer are kept between paints and remade only when
  // the window changes size.
  let W = 0, H = 0, noise = null, img = null;
  const off = document.createElement('canvas');
  const octx = off.getContext('2d');
  const cuts = new Float64Array(LINES + 2);

  function measure() {
    const w = Math.max(1, Math.round(innerWidth)), h = Math.max(1, Math.round(innerHeight));
    if (w === W && h === H && img) return;
    W = w; H = h;
    off.width = W; off.height = H;
    img = octx.createImageData(W, H);
    noise = new Int8Array(W * H);
    for (let i = 0; i < noise.length; i++) noise[i] = Math.round((Math.random() * 2 - 1) * GRAIN);
  }
  const resized = function () { return Math.round(innerWidth) !== W || Math.round(innerHeight) !== H; };

  // Each row is cut into spans where it crosses the lines; a span lies in
  // one region, so its tint is looked up once rather than per pixel.
  function paint(canvas) {
    const d = img.data;
    for (let y = 0; y < H; y++) {
      let m = 0;
      cuts[m++] = 0;
      for (let i = 0; i < LINES; i++) {
        const l = lines[i];
        if (l[0] === 0) continue;
        const x = Math.ceil(-(l[1] * y + l[2]) / l[0]);
        if (x > 0 && x < W) cuts[m++] = x;
      }
      cuts[m++] = W;
      const s = cuts.subarray(0, m).sort();
      for (let j = 0; j + 1 < m; j++) {
        const x0 = s[j], x1 = s[j + 1];
        if (x1 <= x0) continue;
        const xm = (x0 + x1) / 2;
        let k = 0;
        for (let i = 0; i < LINES; i++) {
          const l = lines[i];
          if (l[0] * xm + l[1] * y + l[2] > 0) k |= 1 << i;
        }
        const c = tints[pick(k)], r = c[0], g = c[1], b = c[2];
        for (let p = y * W + x0, e = y * W + x1, q = p * 4; p < e; p++, q += 4) {
          const n = noise[p];
          d[q] = r + n; d[q + 1] = g + n; d[q + 2] = b + n; d[q + 3] = 255;
        }
      }
    }
    octx.putImageData(img, 0, 0);

    const ctx = canvas.getContext('2d'), dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.strokeStyle = line; ctx.lineWidth = 1;
    lines.forEach(function (l) {
      const a = l[0], b = l[1], c = l[2];
      ctx.beginPath();
      if (Math.abs(b) > Math.abs(a)) { ctx.moveTo(0, -c / b); ctx.lineTo(W, -(a * W + c) / b); }
      else { ctx.moveTo(-c / a, 0); ctx.lineTo(-(b * H + c) / a, H); }
      ctx.stroke();
    });
  }

  roll(); colours(); measure(); paint(front);

  let timer = 0;
  addEventListener('resize', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { if (resized()) { measure(); paint(front); } }, 150);
  });
  if (window.haileyjayTheme) window.haileyjayTheme.onChange(function () { colours(); paint(front); });

  const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  // After the first, a redraw waits until the new section has painted, so a
  // click never waits on the backdrop. Clicks in quick succession share one.
  let queued = false;
  document.addEventListener('accentchange', function (e) {
    if (e.detail.first) { colours(); paint(front); return; }
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { setTimeout(redraw, 0); });
  });

  function redraw() {
    queued = false;
    colours();
    if (still && still.matches) { paint(front); return; }
    roll(); measure();
    // The hidden canvas goes on top at opacity 0, then fades in.
    back.style.transition = 'none';
    back.style.opacity = '0';
    front.after(back);
    paint(back);
    back.getBoundingClientRect();   // commit opacity 0 before the transition
    back.style.transition = '';
    back.style.opacity = '1';
    const t = front; front = back; back = t;
  }
})();
