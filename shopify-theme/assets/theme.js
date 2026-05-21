/**
 * VAULT 34 — Core Theme JavaScript
 * Architecture: vanilla ES6+ modules, no build step required
 * All heavy lifting lives in separate component files loaded lazily
 */

'use strict';

/* ---------------------------------------------------------------------------
   HEADER — scroll detection & transparent-to-opaque transition
   --------------------------------------------------------------------------- */
class SiteHeader {
  constructor() {
    this.el = document.querySelector('.site-header');
    if (!this.el) return;

    this.scrollThreshold = 80;
    this.ticking = false;
    this._init();
  }

  _init() {
    window.addEventListener('scroll', () => this._onScroll(), { passive: true });
    this._onScroll();
  }

  _onScroll() {
    if (this.ticking) return;
    this.ticking = true;
    requestAnimationFrame(() => {
      const scrolled = window.scrollY > this.scrollThreshold;
      this.el.classList.toggle('site-header--scrolled', scrolled);
      this.el.classList.toggle('site-header--transparent', !scrolled);
      this.ticking = false;
    });
  }
}

/* ---------------------------------------------------------------------------
   MEGA MENU — desktop dropdown with accessibility
   --------------------------------------------------------------------------- */
class MegaMenu {
  constructor() {
    this.items = document.querySelectorAll('.nav-item[data-has-dropdown]');
    this.openItem = null;
    this.closeTimer = null;
    this._init();
  }

  _init() {
    this.items.forEach(item => {
      item.addEventListener('mouseenter', () => this._open(item));
      item.addEventListener('mouseleave', () => this._scheduleClose(item));

      const menu = item.querySelector('.mega-menu');
      if (menu) {
        menu.addEventListener('mouseenter', () => clearTimeout(this.closeTimer));
        menu.addEventListener('mouseleave', () => this._scheduleClose(item));
      }

      // Keyboard
      item.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          item.classList.contains('is-open') ? this._close(item) : this._open(item);
        }
        if (e.key === 'Escape') this._close(item);
      });
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.nav-item')) {
        this.items.forEach(i => this._close(i));
      }
    });
  }

  _open(item) {
    clearTimeout(this.closeTimer);
    if (this.openItem && this.openItem !== item) {
      this._close(this.openItem);
    }
    item.classList.add('is-open');
    const link = item.querySelector('.nav-link');
    if (link) link.setAttribute('aria-expanded', 'true');
    this.openItem = item;
  }

  _scheduleClose(item) {
    this.closeTimer = setTimeout(() => this._close(item), 120);
  }

  _close(item) {
    item.classList.remove('is-open');
    const link = item.querySelector('.nav-link');
    if (link) link.setAttribute('aria-expanded', 'false');
    if (this.openItem === item) this.openItem = null;
  }
}

/* ---------------------------------------------------------------------------
   MOBILE MENU
   --------------------------------------------------------------------------- */
class MobileMenu {
  constructor() {
    this.menu = document.querySelector('.mobile-menu');
    this.backdrop = document.querySelector('.mobile-menu__backdrop');
    this.openBtn = document.querySelector('[data-mobile-menu-open]');
    this.closeBtn = document.querySelector('[data-mobile-menu-close]');
    if (!this.menu) return;
    this._init();
  }

  _init() {
    this.openBtn?.addEventListener('click', () => this.open());
    this.closeBtn?.addEventListener('click', () => this.close());
    this.backdrop?.addEventListener('click', () => this.close());

    // Accordion sub-menus
    this.menu.querySelectorAll('.mobile-nav-link[data-has-sub]').forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const item = link.closest('.mobile-nav-item');
        const sub = item?.querySelector('.mobile-nav-submenu');
        if (!sub) return;
        const isOpen = sub.classList.contains('is-open');
        this.menu.querySelectorAll('.mobile-nav-submenu.is-open').forEach(s => s.classList.remove('is-open'));
        if (!isOpen) sub.classList.add('is-open');
      });
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });
  }

  open() {
    this.menu.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    document.querySelector('[data-mobile-menu-open]')?.setAttribute('aria-expanded', 'true');
  }

  close() {
    this.menu.classList.remove('is-open');
    document.body.style.overflow = '';
    document.querySelector('[data-mobile-menu-open]')?.setAttribute('aria-expanded', 'false');
  }
}

/* ---------------------------------------------------------------------------
   SEARCH MODAL
   --------------------------------------------------------------------------- */
class SearchModal {
  constructor() {
    this.modal = document.querySelector('.search-modal');
    this.input = this.modal?.querySelector('.search-modal__input');
    this.results = this.modal?.querySelector('.search-modal__results');
    this.openBtns = document.querySelectorAll('[data-search-open]');
    this.closeBtn = this.modal?.querySelector('[data-search-close]');
    this.backdrop = this.modal?.querySelector('.search-modal__backdrop');
    this.debounceTimer = null;
    if (!this.modal) return;
    this._init();
  }

  _init() {
    this.openBtns.forEach(btn => btn.addEventListener('click', () => this.open()));
    this.closeBtn?.addEventListener('click', () => this.close());
    this.backdrop?.addEventListener('click', () => this.close());

    document.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        this.modal.classList.contains('is-open') ? this.close() : this.open();
      }
      if (e.key === 'Escape') this.close();
    });

    this.input?.addEventListener('input', () => {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this._search(this.input.value.trim()), 280);
    });
  }

  open() {
    this.modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    setTimeout(() => this.input?.focus(), 50);
  }

  close() {
    this.modal.classList.remove('is-open');
    document.body.style.overflow = '';
    if (this.input) this.input.value = '';
    if (this.results) this.results.innerHTML = '';
  }

  async _search(query) {
    if (!query || query.length < 2) {
      if (this.results) this.results.innerHTML = '';
      return;
    }

    if (this.results) {
      this.results.innerHTML = `
        <div style="padding:1rem;display:flex;gap:.75rem;flex-direction:column">
          ${Array(3).fill('<div class="skeleton skeleton-text" style="height:56px;border-radius:var(--radius-lg)"></div>').join('')}
        </div>
      `;
    }

    try {
      const res = await fetch(`/search/suggest.json?q=${encodeURIComponent(query)}&resources[type]=product&resources[limit]=6`);
      const data = await res.json();
      this._renderResults(data.resources?.results?.products || []);
    } catch {
      if (this.results) this.results.innerHTML = '<p style="padding:1rem;color:var(--text-subtle)">Search unavailable</p>';
    }
  }

  _renderResults(products) {
    if (!this.results) return;
    if (!products.length) {
      this.results.innerHTML = '<p style="padding:1rem 1.25rem;color:var(--text-subtle);font-size:var(--text-sm)">No results found</p>';
      return;
    }

    this.results.innerHTML = products.map(p => `
      <a href="${p.url}" class="search-result-item">
        <img class="search-result-item__image"
             src="${p.featured_image?.url || ''}"
             alt="${p.title}"
             loading="lazy"
             width="56" height="56">
        <div>
          <div class="search-result-item__title">${p.title}</div>
          <div class="search-result-item__meta">${this._formatMoney(p.price)}</div>
        </div>
        <svg width="14" height="14" fill="none" style="margin-left:auto;color:var(--text-subtle);flex-shrink:0">
          <path d="M5 3l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </a>
    `).join('');
  }

  _formatMoney(cents) {
    if (!cents) return '';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: window.Shopify?.currency?.active || 'USD' })
      .format(cents / 100);
  }
}

/* ---------------------------------------------------------------------------
   CART DRAWER
   --------------------------------------------------------------------------- */
class CartDrawer {
  constructor() {
    this.drawer = document.querySelector('.cart-drawer');
    this.overlay = document.querySelector('.cart-drawer__overlay');
    this.itemsEl = document.querySelector('.cart-drawer__items');
    this.countEls = document.querySelectorAll('[data-cart-count]');
    this.openBtns = document.querySelectorAll('[data-cart-open]');
    this.closeBtn = document.querySelector('[data-cart-close]');
    if (!this.drawer) return;
    this._init();
  }

  _init() {
    this.openBtns.forEach(btn => btn.addEventListener('click', () => this.open()));
    this.closeBtn?.addEventListener('click', () => this.close());
    this.overlay?.addEventListener('click', () => this.close());

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });

    // Listen for add-to-cart events
    document.addEventListener('cart:add', (e) => this._onAdd(e.detail));
    document.addEventListener('cart:update', () => this._refresh());
  }

  async open() {
    await this._refresh();
    this.drawer.classList.add('is-open');
    this.overlay.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  close() {
    this.drawer.classList.remove('is-open');
    this.overlay.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  async _onAdd(detail) {
    await this._refresh();
    this.open();
  }

  async _refresh() {
    try {
      const res = await fetch('/cart.js');
      const cart = await res.json();
      this._updateCount(cart.item_count);
      this._renderItems(cart);
    } catch (err) {
      console.warn('Cart refresh failed', err);
    }
  }

  _updateCount(count) {
    this.countEls.forEach(el => {
      el.textContent = count;
      el.closest('.header-action-btn')?.classList.toggle('has-items', count > 0);
    });
  }

  _renderItems(cart) {
    if (!this.itemsEl) return;

    const totalEl = document.querySelector('[data-cart-total]');
    if (totalEl) totalEl.textContent = this._money(cart.total_price);

    const countEl = document.querySelector('.cart-drawer__count');
    if (countEl) countEl.textContent = cart.item_count;

    if (!cart.items.length) {
      this.itemsEl.innerHTML = `
        <div style="text-align:center;padding:var(--space-16) var(--space-8);color:var(--text-subtle)">
          <svg width="48" height="48" fill="none" style="margin:0 auto var(--space-4)" opacity=".4">
            <path d="M6 6h4l2.6 13H36M16 34a2 2 0 100 4 2 2 0 000-4zm18 0a2 2 0 100 4 2 2 0 000-4z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <p style="font-size:var(--text-sm);margin-bottom:var(--space-3)">Your cart is empty</p>
          <a href="/collections/all" class="btn btn-secondary btn-sm" onclick="window.vault34.cartDrawer.close()">Shop Products</a>
        </div>
      `;
      return;
    }

    this.itemsEl.innerHTML = cart.items.map(item => `
      <div class="cart-item" data-key="${item.key}">
        <img class="cart-item__image"
             src="${item.image}"
             alt="${item.product_title}"
             width="80" height="80"
             loading="lazy">
        <div>
          <div class="cart-item__brand">${item.vendor || ''}</div>
          <div class="cart-item__title">${item.product_title}</div>
          ${item.variant_title ? `<div class="cart-item__variant">${item.variant_title}</div>` : ''}
          <div class="cart-item__qty">
            <button class="cart-item__qty-btn" data-qty-change="-1" aria-label="Decrease">
              <svg width="12" height="12" fill="none"><path d="M2 6h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
            <span class="cart-item__qty-val">${item.quantity}</span>
            <button class="cart-item__qty-btn" data-qty-change="1" aria-label="Increase">
              <svg width="12" height="12" fill="none"><path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>
        <div class="cart-item__price">
          <span class="cart-item__price-value">${this._money(item.line_price)}</span>
          <button class="btn btn-ghost" style="font-size:var(--text-xs);padding:.25rem .5rem;color:var(--text-subtle)" data-remove-key="${item.key}" aria-label="Remove">Remove</button>
        </div>
      </div>
    `).join('');

    // Bind qty/remove events
    this.itemsEl.querySelectorAll('[data-qty-change]').forEach(btn => {
      btn.addEventListener('click', () => {
        const item = btn.closest('.cart-item');
        const key = item.dataset.key;
        const qtyEl = item.querySelector('.cart-item__qty-val');
        const currentQty = parseInt(qtyEl.textContent);
        const delta = parseInt(btn.dataset.qtyChange);
        this._updateQty(key, Math.max(0, currentQty + delta));
      });
    });

    this.itemsEl.querySelectorAll('[data-remove-key]').forEach(btn => {
      btn.addEventListener('click', () => this._updateQty(btn.dataset.removeKey, 0));
    });
  }

  async _updateQty(key, quantity) {
    try {
      const res = await fetch('/cart/change.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: key, quantity }),
      });
      const cart = await res.json();
      this._updateCount(cart.item_count);
      this._renderItems(cart);
      document.dispatchEvent(new CustomEvent('cart:changed', { detail: cart }));
    } catch (err) {
      console.warn('Cart update failed', err);
    }
  }

  _money(cents) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: window.Shopify?.currency?.active || 'USD',
    }).format(cents / 100);
  }
}

/* ---------------------------------------------------------------------------
   ADD TO CART — handles form submission
   --------------------------------------------------------------------------- */
class AddToCart {
  constructor() {
    this._init();
  }

  _init() {
    document.querySelectorAll('[data-atc-form]').forEach(form => {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        this._submit(form);
      });
    });

    // Quick-add buttons on cards
    document.querySelectorAll('[data-quick-add]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const variantId = btn.dataset.quickAdd;
        if (!variantId) return;
        btn.classList.add('is-loading');
        try {
          await this._addToCart(variantId, 1);
          showToast('Added to cart');
        } catch {
          showToast('Could not add to cart', 'error');
        } finally {
          btn.classList.remove('is-loading');
        }
      });
    });
  }

  async _submit(form) {
    const btn = form.querySelector('[data-atc-btn]');
    if (btn) {
      btn.classList.add('is-loading');
      btn.disabled = true;
    }

    const formData = new FormData(form);

    try {
      const res = await fetch('/cart/add.js', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Add to cart failed');
      const item = await res.json();

      document.dispatchEvent(new CustomEvent('cart:add', { detail: item }));

      if (btn) {
        btn.textContent = 'Added!';
        setTimeout(() => {
          btn.textContent = btn.dataset.defaultText || 'Add to Cart';
          btn.disabled = false;
          btn.classList.remove('is-loading');
        }, 1800);
      }
    } catch (err) {
      console.error(err);
      if (btn) {
        btn.textContent = 'Error — Try Again';
        btn.disabled = false;
        btn.classList.remove('is-loading');
        setTimeout(() => {
          btn.textContent = btn.dataset.defaultText || 'Add to Cart';
        }, 2500);
      }
    }
  }

  async _addToCart(variantId, qty = 1) {
    const res = await fetch('/cart/add.js', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: variantId, quantity: qty }),
    });
    if (!res.ok) throw new Error('Add failed');
    const item = await res.json();
    document.dispatchEvent(new CustomEvent('cart:add', { detail: item }));
    return item;
  }
}

/* ---------------------------------------------------------------------------
   STICKY ATC — shows after scrolling past the main ATC
   --------------------------------------------------------------------------- */
class StickyAtc {
  constructor() {
    this.bar = document.querySelector('.sticky-atc');
    this.trigger = document.querySelector('[data-sticky-atc-trigger]');
    if (!this.bar || !this.trigger) return;
    this._init();
  }

  _init() {
    const observer = new IntersectionObserver(
      ([entry]) => this.bar.classList.toggle('is-visible', !entry.isIntersecting),
      { rootMargin: '-80px 0px 0px 0px' }
    );
    observer.observe(this.trigger);
  }
}

/* ---------------------------------------------------------------------------
   SCROLL REVEAL — IntersectionObserver for .reveal elements
   --------------------------------------------------------------------------- */
class ScrollReveal {
  constructor() {
    const targets = document.querySelectorAll('.reveal, .reveal-left, .reveal-right');
    if (!targets.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -48px 0px' }
    );

    targets.forEach(el => observer.observe(el));
  }
}

/* ---------------------------------------------------------------------------
   FITMENT SELECTOR
   --------------------------------------------------------------------------- */
class FitmentSelector {
  constructor() {
    this.bar = document.querySelector('[data-fitment-bar]');
    if (!this.bar) return;

    this.makeEl   = this.bar.querySelector('[data-fitment-make]');
    this.modelEl  = this.bar.querySelector('[data-fitment-model]');
    this.yearEl   = this.bar.querySelector('[data-fitment-year]');
    this.submitEl = this.bar.querySelector('[data-fitment-submit]');

    this._fitmentData = window.vault34FitmentData || {};
    this._init();
  }

  _init() {
    this._populateMakes();
    this.makeEl?.addEventListener('change', () => this._onMakeChange());
    this.modelEl?.addEventListener('change', () => this._onModelChange());
    this.submitEl?.addEventListener('click', () => this._onSubmit());
  }

  _populateMakes() {
    if (!this.makeEl) return;
    const makes = Object.keys(this._fitmentData).sort();
    makes.forEach(make => {
      const opt = document.createElement('option');
      opt.value = make;
      opt.textContent = make;
      this.makeEl.appendChild(opt);
    });
  }

  _onMakeChange() {
    const make = this.makeEl?.value;
    if (!this.modelEl) return;

    this.modelEl.innerHTML = '<option value="">Select Model</option>';
    this.yearEl && (this.yearEl.innerHTML = '<option value="">Select Year</option>');
    this.modelEl.disabled = !make;
    this.yearEl && (this.yearEl.disabled = true);

    if (!make || !this._fitmentData[make]) return;
    Object.keys(this._fitmentData[make]).sort().forEach(model => {
      const opt = document.createElement('option');
      opt.value = model;
      opt.textContent = model;
      this.modelEl.appendChild(opt);
    });
    this.modelEl.disabled = false;
  }

  _onModelChange() {
    const make  = this.makeEl?.value;
    const model = this.modelEl?.value;
    if (!this.yearEl) return;

    this.yearEl.innerHTML = '<option value="">Select Year</option>';
    this.yearEl.disabled = !model;

    if (!make || !model || !this._fitmentData[make]?.[model]) return;
    [...this._fitmentData[make][model]].sort((a, b) => b - a).forEach(year => {
      const opt = document.createElement('option');
      opt.value = year;
      opt.textContent = year;
      this.yearEl.appendChild(opt);
    });
    this.yearEl.disabled = false;
  }

  _onSubmit() {
    const make  = this.makeEl?.value;
    const model = this.modelEl?.value;
    const year  = this.yearEl?.value;
    if (!make || !model || !year) return;

    const tag = `${make}_${model}_${year}`.toLowerCase().replace(/\s+/g, '_');
    window.location.href = `/collections/all?filter.p.tag=${encodeURIComponent(tag)}`;
  }
}

/* ---------------------------------------------------------------------------
   PRODUCT GALLERY — lightbox + thumb switching
   --------------------------------------------------------------------------- */
class ProductGallery {
  constructor() {
    this.gallery = document.querySelector('[data-product-gallery]');
    if (!this.gallery) return;

    this.mainImg = this.gallery.querySelector('[data-gallery-main]');
    this.thumbs  = this.gallery.querySelectorAll('[data-gallery-thumb]');
    this._init();
  }

  _init() {
    this.thumbs.forEach((thumb, i) => {
      thumb.addEventListener('click', () => this._setActive(thumb, i));
      thumb.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this._setActive(thumb, i);
      });
    });

    // Lightbox on main image click
    this.mainImg?.addEventListener('click', () => this._openLightbox());

    // Touch swipe on mobile
    this._initSwipe();
  }

  _initSwipe() {
    const main = this.gallery.querySelector('.product-gallery__main');
    if (!main || !this.thumbs.length) return;
    let startX = 0;
    main.addEventListener('touchstart', (e) => { startX = e.touches[0].clientX; }, { passive: true });
    main.addEventListener('touchend', (e) => {
      const dx = e.changedTouches[0].clientX - startX;
      if (Math.abs(dx) < 40) return;
      const currentIdx = [...this.thumbs].findIndex(t => t.classList.contains('is-active'));
      const nextIdx = dx < 0
        ? Math.min(currentIdx + 1, this.thumbs.length - 1)
        : Math.max(currentIdx - 1, 0);
      if (nextIdx !== currentIdx) this._setActive(this.thumbs[nextIdx], nextIdx);
    }, { passive: true });
  }

  _setActive(thumb, index) {
    this.thumbs.forEach(t => t.classList.remove('is-active'));
    thumb.classList.add('is-active');

    const src     = thumb.dataset.galleryThumb;
    const srcset  = thumb.dataset.galleryThumbSrcset || '';
    const alt     = thumb.dataset.alt || '';

    if (this.mainImg) {
      this.mainImg.classList.add('is-transitioning');
      setTimeout(() => {
        this.mainImg.src    = src;
        if (srcset) this.mainImg.srcset = srcset;
        this.mainImg.alt    = alt;
        this.mainImg.classList.remove('is-transitioning');
      }, 150);
    }
  }

  _openLightbox() {
    const src = this.mainImg?.src;
    if (!src) return;

    const overlay = document.createElement('div');
    overlay.style.cssText = `
      position:fixed;inset:0;z-index:9999;
      background:rgba(0,0,0,0.95);
      display:flex;align-items:center;justify-content:center;
      cursor:zoom-out;
      animation:fadeIn 0.2s ease;
    `;

    const img = document.createElement('img');
    img.src = src.replace('_800x', '_2000x').replace('_400x', '_2000x');
    img.style.cssText = 'max-width:90vw;max-height:90vh;object-fit:contain;border-radius:var(--radius-lg)';

    overlay.appendChild(img);
    overlay.addEventListener('click', () => overlay.remove());
    document.addEventListener('keydown', function handler(e) {
      if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', handler); }
    });
    document.body.appendChild(overlay);
  }
}

/* ---------------------------------------------------------------------------
   SOUND PLAYER — exhaust audio module
   --------------------------------------------------------------------------- */
class SoundPlayer {
  constructor() {
    this.players = document.querySelectorAll('[data-sound-player]');
    this.players.forEach(player => this._initPlayer(player));
  }

  _initPlayer(player) {
    const btn      = player.querySelector('[data-sound-play]');
    const audioSrc = player.dataset.soundSrc;
    const waveform = player.querySelector('.sound-waveform');

    if (!btn || !audioSrc) return;

    let audio = null;
    let playing = false;

    btn.addEventListener('click', () => {
      if (!audio) {
        audio = new Audio(audioSrc);
        audio.addEventListener('ended', () => {
          playing = false;
          waveform?.classList.remove('is-playing');
          this._updatePlayBtn(btn, false);
        });
      }

      if (playing) {
        audio.pause();
        audio.currentTime = 0;
        playing = false;
        waveform?.classList.remove('is-playing');
        this._updatePlayBtn(btn, false);
      } else {
        // Stop any other playing
        document.querySelectorAll('[data-sound-audio]').forEach(a => {
          if (a !== audio) { a.pause(); a.currentTime = 0; }
        });

        audio.play().catch((err) => {
          console.warn('Audio playback failed:', err);
          playing = false;
          waveform?.classList.remove('is-playing');
          this._updatePlayBtn(btn, false);
          const origText = btn.querySelector('[data-icon-play]')?.nextSibling?.textContent;
          btn.lastChild.textContent = ' Unavailable';
          setTimeout(() => { if (btn.lastChild) btn.lastChild.textContent = ' Play Sound'; }, 2500);
        });
        playing = true;
        waveform?.classList.add('is-playing');
        this._updatePlayBtn(btn, true);
      }
    });

    // Sound tabs
    player.querySelectorAll('.sound-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        player.querySelectorAll('.sound-tab').forEach(t => t.classList.remove('is-active'));
        tab.classList.add('is-active');

        const newSrc = tab.dataset.soundSrc;
        if (newSrc && audio) {
          const wasPlaying = playing;
          audio.pause();
          audio.src = newSrc;
          if (wasPlaying) audio.play().catch(() => {});
        }
      });
    });
  }

  _updatePlayBtn(btn, isPlaying) {
    const playIcon  = btn.querySelector('[data-icon-play]');
    const pauseIcon = btn.querySelector('[data-icon-pause]');
    if (playIcon)  playIcon.style.display  = isPlaying ? 'none' : 'block';
    if (pauseIcon) pauseIcon.style.display = isPlaying ? 'block' : 'none';
  }
}

/* ---------------------------------------------------------------------------
   ANNOUNCEMENT BAR — auto-rotating messages
   --------------------------------------------------------------------------- */
class AnnouncementBar {
  constructor() {
    this.bar = document.querySelector('.announcement-bar[data-rotates]');
    if (!this.bar) return;

    this.messages = this.bar.querySelectorAll('[data-announcement-message]');
    if (this.messages.length <= 1) return;

    this.current = 0;
    this._init();
  }

  _init() {
    this.messages.forEach((msg, i) => {
      msg.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      if (i !== 0) {
        msg.style.opacity = '0';
        msg.style.position = 'absolute';
      }
    });

    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setInterval(() => this._next(), 4000);
    }
  }

  _next() {
    const prev = this.messages[this.current];
    this.current = (this.current + 1) % this.messages.length;
    const next = this.messages[this.current];

    prev.style.opacity = '0';
    prev.style.transform = 'translateY(-8px)';
    setTimeout(() => {
      prev.style.position = 'absolute';
      next.style.position = 'relative';
      next.style.transform = 'translateY(8px)';
      next.style.opacity = '0';
      requestAnimationFrame(() => {
        next.style.transform = 'translateY(0)';
        next.style.opacity = '1';
      });
    }, 400);
  }
}

/* ---------------------------------------------------------------------------
   QUANTITY INPUT
   --------------------------------------------------------------------------- */
function initQuantityInputs() {
  document.querySelectorAll('.quantity-input').forEach(wrap => {
    const input = wrap.querySelector('.quantity-field');
    const dec   = wrap.querySelector('[data-qty-dec]');
    const inc   = wrap.querySelector('[data-qty-inc]');
    if (!input) return;

    dec?.addEventListener('click', () => {
      const val = parseInt(input.value) || 1;
      if (val > 1) input.value = val - 1;
      input.dispatchEvent(new Event('change'));
    });

    inc?.addEventListener('click', () => {
      const val = parseInt(input.value) || 1;
      input.value = val + 1;
      input.dispatchEvent(new Event('change'));
    });
  });
}

/* ---------------------------------------------------------------------------
   VARIANT SELECTOR
   --------------------------------------------------------------------------- */
class VariantSelector {
  constructor() {
    document.querySelectorAll('[data-variant-form]').forEach(form => {
      this._initForm(form);
    });
  }

  _initForm(form) {
    const options     = form.querySelectorAll('[data-variant-option]');
    const priceEl     = form.querySelector('[data-variant-price]');
    const compareEl   = form.querySelector('[data-variant-compare]');
    const stockEl     = form.querySelector('[data-variant-stock]');
    const hiddenInput = form.querySelector('input[name="id"]');
    const atcBtn      = form.querySelector('[data-atc-btn]');

    const variantsJson = form.querySelector('[data-variants-json]');
    if (!variantsJson) return;

    let variants;
    try { variants = JSON.parse(variantsJson.textContent); }
    catch { return; }

    options.forEach(opt => {
      opt.addEventListener('click', () => {
        const group = opt.closest('[data-option-group]');
        group?.querySelectorAll('[data-variant-option]').forEach(o => o.classList.remove('is-selected'));
        opt.classList.add('is-selected');
        this._updateSelected(form, variants, hiddenInput, priceEl, compareEl, stockEl, atcBtn);
      });
    });
  }

  _updateSelected(form, variants, hiddenInput, priceEl, compareEl, stockEl, atcBtn) {
    const selectedValues = [];
    form.querySelectorAll('[data-option-group]').forEach(group => {
      const selected = group.querySelector('[data-variant-option].is-selected');
      if (selected) selectedValues.push(selected.textContent.trim());
    });

    const match = variants.find(v =>
      v.options.every((opt, i) => opt === selectedValues[i])
    );

    if (!match) return;

    if (hiddenInput) hiddenInput.value = match.id;

    if (priceEl) {
      priceEl.textContent = this._money(match.price);
    }

    if (compareEl) {
      if (match.compare_at_price && match.compare_at_price > match.price) {
        compareEl.textContent = this._money(match.compare_at_price);
        compareEl.style.display = '';
      } else {
        compareEl.style.display = 'none';
      }
    }

    if (stockEl) {
      stockEl.textContent = match.available ? 'In Stock' : 'Out of Stock';
      stockEl.style.color = match.available ? 'var(--color-success)' : 'var(--text-subtle)';
    }

    if (atcBtn) {
      atcBtn.disabled = !match.available;
      atcBtn.textContent = match.available ? (atcBtn.dataset.defaultText || 'Add to Cart') : 'Out of Stock';
    }

    // Sync sticky ATC
    document.dispatchEvent(new CustomEvent('variant:change', { detail: match }));
  }

  _money(cents) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: window.Shopify?.currency?.active || 'USD',
    }).format(cents / 100);
  }
}

/* ---------------------------------------------------------------------------
   TOAST NOTIFICATION
   --------------------------------------------------------------------------- */
function showToast(message, type = 'success') {
  let styleEl = document.getElementById('vault34-toast-styles');
  if (!styleEl) {
    styleEl = document.createElement('style');
    styleEl.id = 'vault34-toast-styles';
    styleEl.textContent = `
      @keyframes toastIn  { from{opacity:0;transform:translateX(-50%) translateY(16px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }
      @keyframes toastOut { from{opacity:1;transform:translateX(-50%) translateY(0)} to{opacity:0;transform:translateX(-50%) translateY(16px)} }
    `;
    document.head.appendChild(styleEl);
  }

  const toast = document.createElement('div');
  const bg = type === 'error' ? '#ef4444' : 'var(--bg-elevated)';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  toast.style.cssText = `
    position:fixed;bottom:1.5rem;left:50%;z-index:9998;
    background:${bg};color:var(--text-primary);
    padding:.625rem 1.25rem;border-radius:9999px;
    font-size:var(--text-sm);font-weight:var(--font-medium);
    border:1px solid var(--border-subtle);box-shadow:0 8px 24px rgba(0,0,0,.4);
    display:flex;align-items:center;gap:.5rem;white-space:nowrap;
    animation:toastIn 0.25s ease forwards;pointer-events:none;
  `;
  const icon = type === 'error'
    ? `<svg width="14" height="14" fill="none"><path d="M12 12L2 2M2 12L12 2" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>`
    : `<svg width="14" height="14" fill="none"><path d="M2 7l3.5 3.5 6.5-6" stroke="var(--purple-300)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  toast.innerHTML = icon + message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.25s ease forwards';
    setTimeout(() => toast.remove(), 260);
  }, 2500);
}

/* ---------------------------------------------------------------------------
   INIT
   --------------------------------------------------------------------------- */
function init() {
  window.vault34 = {
    header:        new SiteHeader(),
    megaMenu:      new MegaMenu(),
    mobileMenu:    new MobileMenu(),
    searchModal:   new SearchModal(),
    cartDrawer:    new CartDrawer(),
    addToCart:     new AddToCart(),
    stickyAtc:     new StickyAtc(),
    scrollReveal:  new ScrollReveal(),
    fitment:       new FitmentSelector(),
    gallery:       new ProductGallery(),
    soundPlayer:   new SoundPlayer(),
    announcement:  new AnnouncementBar(),
    variants:      new VariantSelector(),
  };

  initQuantityInputs();

  // Lazy-load images
  if ('IntersectionObserver' in window) {
    const imgObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            if (img.dataset.src) {
              img.src = img.dataset.src;
              img.removeAttribute('data-src');
            }
            imgObserver.unobserve(img);
          }
        });
      },
      { rootMargin: '200px 0px' }
    );
    document.querySelectorAll('img[data-src]').forEach(img => imgObserver.observe(img));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
