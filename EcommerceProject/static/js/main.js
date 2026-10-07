// Vanilla JS enhancements — no framework needed for a few small UX touches.

document.addEventListener('DOMContentLoaded', function () {
    // Quantity stepper buttons (used on cart page and product detail page)
    document.querySelectorAll('.qty-stepper').forEach(function (stepper) {
        var input = stepper.querySelector('input[type="number"]');
        var minus = stepper.querySelector('.qty-minus');
        var plus = stepper.querySelector('.qty-plus');
        if (!input) return;

        if (minus) {
            minus.addEventListener('click', function () {
                var val = parseInt(input.value || '1', 10);
                if (val > 1) input.value = val - 1;
            });
        }
        if (plus) {
            plus.addEventListener('click', function () {
                var max = parseInt(input.getAttribute('max') || '9999', 10);
                var val = parseInt(input.value || '1', 10);
                if (val < max) input.value = val + 1;
            });
        }
    });

    // Confirm before destructive actions (cancel order, delete address, etc.)
    document.querySelectorAll('.confirm-action').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            var msg = form.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(msg)) {
                e.preventDefault();
            }
        });
    });

    // Django's auto-rendered {{ field }} form fields don't carry Bootstrap
    // classes on their own. Rather than editing every forms.py, apply the
    // right class here — but only to fields we didn't already style by hand
    // in a template (those already have a class attribute, so we skip them).
    document.querySelectorAll('form input, form select, form textarea').forEach(function (el) {
        if (el.className) return; // already styled explicitly in the template
        var type = (el.getAttribute('type') || '').toLowerCase();
        if (type === 'checkbox' || type === 'radio') {
            el.classList.add('form-check-input');
        } else if (el.tagName === 'SELECT') {
            el.classList.add('form-select');
        } else if (type !== 'submit' && type !== 'button' && type !== 'hidden') {
            el.classList.add('form-control');
        }
    });
});

// ===== v2 additions: toasts, AJAX actions, variants, gallery, checkout stepper =====
(function () {
    document.documentElement.classList.add('js');

    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }

    function toast(msg, type) {
        var area = document.getElementById('toast-area');
        if (!area || !window.bootstrap) return;
        var el = document.createElement('div');
        el.className = 'toast align-items-center border-0 text-bg-' + (type || 'success');
        el.setAttribute('role', 'status');
        var wrap = document.createElement('div'); wrap.className = 'd-flex';
        var body = document.createElement('div'); body.className = 'toast-body'; body.textContent = msg;
        var btn = document.createElement('button'); btn.type = 'button';
        btn.className = 'btn-close btn-close-white me-2 m-auto'; btn.setAttribute('data-bs-dismiss', 'toast');
        wrap.appendChild(body); wrap.appendChild(btn); el.appendChild(wrap); area.appendChild(el);
        el.addEventListener('hidden.bs.toast', function () { el.remove(); });
        new bootstrap.Toast(el, { delay: 3000 }).show();
    }
    window.mmToast = toast;

    // Submit an existing Django form via fetch. The server views redirect after
    // POST, so a followed redirect that ends OK means the action succeeded.
    function submitAjax(form) {
        return fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (res) {
            if (!res.ok || res.url.indexOf('/accounts/login') !== -1) throw new Error('Action failed (' + res.status + ')');
            return res;
        });
    }

    function afterSuccess(form) {
        var mode = form.dataset.success;
        if (mode === 'remove-row') {
            var row = form.closest('tr'), tbody = row.parentNode, key = form.dataset.count;
            row.remove();
            if (key) {
                var badge = document.querySelector('span.badge[data-count="' + key + '"]');
                if (badge) badge.textContent = Math.max(0, parseInt(badge.textContent, 10) - 1);
            }
            if (!tbody.querySelector('tr')) {
                var cols = tbody.closest('table').querySelectorAll('thead th').length;
                tbody.innerHTML = '<tr><td colspan="' + cols + '" class="text-center text-muted py-4">All caught up.</td></tr>';
            }
        } else if (mode === 'refresh-stock') {
            // Re-read the page so what we show is what the server actually saved.
            var id = form.dataset.variant, cur = document.querySelector('[data-stock-for="' + id + '"]');
            var before = cur ? cur.textContent.trim() : null;
            fetch(window.location.href, { credentials: 'same-origin' }).then(function (r) { return r.text(); }).then(function (html) {
                var doc = new DOMParser().parseFromString(html, 'text/html');
                var fresh = doc.querySelector('[data-stock-for="' + id + '"]');
                if (fresh && cur) {
                    cur.textContent = fresh.textContent;
                    var fr = fresh.parentNode.children, cr = cur.parentNode.children;
                    if (fr[3] && cr[3]) cr[3].innerHTML = fr[3].innerHTML;
                    if (fresh.textContent.trim() === before) { toast('Stock was not changed. It cannot go below zero.', 'warning'); }
                    else { toast(form.dataset.ok || 'Done'); }
                }
                form.reset();
            });
        }
    }

    function run(form) {
        var btn = form.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        submitAjax(form).then(function () {
            if (form.dataset.success !== 'refresh-stock') toast(form.dataset.ok || 'Done');
            afterSuccess(form);
        }).catch(function (e) { toast(e.message, 'danger'); })
          .finally(function () { if (btn) btn.disabled = false; });
    }

    var modalEl = document.getElementById('confirmModal'), pending = null;
    document.querySelectorAll('form.js-ajax-form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (form.dataset.modal && modalEl && window.bootstrap) {
                pending = form;
                document.getElementById('confirmTitle').textContent = form.dataset.modal;
                document.getElementById('confirmOk').className = 'btn ' + (form.dataset.danger ? 'btn-danger' : 'btn-success');
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            } else { run(form); }
        });
    });
    var ok = document.getElementById('confirmOk');
    if (ok) ok.addEventListener('click', function () {
        bootstrap.Modal.getInstance(modalEl).hide();
        if (pending) { run(pending); pending = null; }
    });

    // Product detail: variant switcher
    var radios = document.querySelectorAll('input[name="variant"][data-stock]');
    if (radios.length) {
        var form = document.getElementById('addToCartForm'),
            price = document.getElementById('variantPrice'), old = document.getElementById('variantOld'),
            badge = document.getElementById('variantStock'), btn = document.getElementById('addToCart'),
            qty = form.querySelector('input[name="quantity"]'), main = document.getElementById('mainImage');
        var apply = function (r) {
            var s = parseInt(r.dataset.stock, 10);
            price.textContent = r.dataset.price; old.textContent = r.dataset.old;
            badge.className = 'badge rounded-pill ' + (s === 0 ? 'badge-oos' : s <= 5 ? 'badge-pending' : 'badge-approved');
            badge.textContent = s === 0 ? 'Out of stock' : s <= 5 ? 'Only ' + s + ' left!' : 'In stock';
            form.action = r.dataset.action; btn.disabled = s === 0;
            var bn = document.getElementById('buyNow'); if (bn) bn.disabled = s === 0;
            qty.max = s; if (parseInt(qty.value, 10) > s) qty.value = Math.max(1, s);
            if (r.dataset.image && main) main.src = r.dataset.image;
        };
        radios.forEach(function (r) { r.addEventListener('change', function () { apply(r); }); if (r.checked) apply(r); });
    }
    document.querySelectorAll('.thumb').forEach(function (t) {
        t.addEventListener('click', function () { var m = document.getElementById('mainImage'); if (m) m.src = t.dataset.thumb; });
    });
    var zoom = document.getElementById('zoomWrap');
    if (zoom && zoom.querySelector('img')) {
        var zi = zoom.querySelector('img');
        zoom.addEventListener('mousemove', function (e) {
            var r = zoom.getBoundingClientRect();
            zi.style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + '% ' + ((e.clientY - r.top) / r.height * 100) + '%';
            zi.style.transform = 'scale(1.8)';
        });
        zoom.addEventListener('mouseleave', function () { zi.style.transform = 'scale(1)'; });
    }

    // Checkout stepper (all steps live in one form; the backend is unchanged)
    var steps = document.querySelectorAll('.checkout-step');
    if (steps.length) {
        var go = function (n) {
            steps.forEach(function (s) { s.classList.toggle('active', +s.dataset.step === n); });
            document.querySelectorAll('#stepper li').forEach(function (li) {
                var k = +li.dataset.step; li.classList.toggle('active', k === n); li.classList.toggle('done', k < n);
            });
        };
        var cur = 1;
        document.querySelectorAll('.step-next').forEach(function (b) { b.addEventListener('click', function () { cur = Math.min(3, cur + 1); go(cur); }); });
        document.querySelectorAll('.step-prev').forEach(function (b) { b.addEventListener('click', function () { cur = Math.max(1, cur - 1); go(cur); }); });
    }
})();

// Home page: best-seller rail arrows
document.querySelectorAll('[data-rail]').forEach(function (b) {
    b.addEventListener('click', function () {
        var rail = document.getElementById('rail');
        if (rail) rail.scrollBy({ left: rail.clientWidth * 0.8 * parseInt(b.dataset.rail, 10), behavior: 'smooth' });
    });
});
