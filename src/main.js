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
    if (e.key === 'Escape') closeSidebar();
  });
})();

// ── Section registry ─────────────────────────────────────────
// Filtered against the DOM so unpublished sections drop out cleanly.
const sections = ['about', 'cv', 'teaching', 'printlab', 'comics', 'blog', 'links']
  .filter(function (s) { return document.getElementById(s); });

const subAnchors = {
  '1431': 'teaching',
  '1431f25': 'teaching',
  'lab-status': 'printlab',
  'lab-request': 'printlab',
  'lab-gallery': 'printlab',
  'lab-filament': 'printlab'
};

// ── Navigation ───────────────────────────────────────────────
function showSection(id) {
  let parentId = subAnchors[id] || id;
  if (!sections.includes(parentId)) parentId = 'about';
  sections.forEach(function (s) {
    document.getElementById(s).classList.toggle('active', s === parentId);
  });
}

function navigate(hash, push) {
  var bare = !hash;
  if (!hash) hash = 'about';
  showSection(hash);
  if (!bare) {
    if (push && location.hash.slice(1) !== hash) {
      history.pushState(null, '', '#' + hash);
    } else {
      history.replaceState(null, '', '#' + hash);
    }
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
    // Scoped to the nearest gallery so unrelated posts/sections
    // don't leak into the same prev/next sequence.
    const scope = (fromEl && fromEl.closest('.gallery-grid')) || document;
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

// ── Sidebar wireframe animation ─────────────────────────────
// Shape list mirrors SHAPES in scripts/gen_wireframes.py.
const wireframeShapes = [
  'tetrahedron', 'cube', 'octahedron', 'dodecahedron', 'icosahedron',
  'sphere', 'torus', 'mobius', 'klein_bottle'
];

document.addEventListener('DOMContentLoaded', function () {
  const video = document.getElementById('wireframe-video');
  if (!video) return;
  const pick = wireframeShapes[Math.floor(Math.random() * wireframeShapes.length)];
  video.src = 'images/wireframes/' + pick + '.mp4';
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

    const img = document.createElement('img');
    img.src = entry.src;
    img.alt = entry.alt;
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