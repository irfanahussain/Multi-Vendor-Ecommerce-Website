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
